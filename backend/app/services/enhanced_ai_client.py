"""
Enhanced AI Client with advanced features:
- Circuit breakers for fault tolerance
- Rate limiting and quota management
- Cost optimization and provider selection
- Intelligent fallback mechanisms
- Performance monitoring and analytics
"""
import asyncio
import aiohttp
import openai
import logging
import time
import hashlib
from typing import Dict, Any, Optional, List, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import redis.asyncio as redis
from ..core.config import settings


class AIServiceProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    STABILITY_AI = "stability_ai"
    RUNWAY_ML = "runway_ml"
    PIKA_LABS = "pika_labs"


class TaskType(str, Enum):
    TEXT_GENERATION = "text_generation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    PROMPT_ENHANCEMENT = "prompt_enhancement"


@dataclass
class ServiceConfig:
    """Configuration for AI service providers"""
    provider: AIServiceProvider
    api_key: Optional[str]
    base_url: str
    rate_limit_per_minute: int
    cost_per_token: float
    cost_per_image: float
    cost_per_second_video: float
    timeout_seconds: int = 120
    max_retries: int = 3
    priority: int = 1  # Lower number = higher priority
    capabilities: List[TaskType] = field(default_factory=list)


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault tolerance"""
    provider: AIServiceProvider
    config: CircuitBreakerConfig
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    half_open_calls: int = 0
    
    def should_allow_request(self) -> bool:
        """Check if request should be allowed"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if (self.last_failure_time and 
                datetime.now() - self.last_failure_time > timedelta(seconds=self.config.recovery_timeout)):
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        else:  # HALF_OPEN
            return self.half_open_calls < self.config.half_open_max_calls
    
    def record_success(self):
        """Record successful request"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed request"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
        elif (self.state == CircuitBreakerState.CLOSED and 
              self.failure_count >= self.config.failure_threshold):
            self.state = CircuitBreakerState.OPEN


@dataclass
class RateLimiter:
    """Rate limiter for API calls"""
    provider: AIServiceProvider
    max_calls_per_minute: int
    calls_made: List[datetime] = field(default_factory=list)
    
    def can_make_request(self) -> bool:
        """Check if request can be made within rate limits"""
        now = datetime.now()
        # Remove calls older than 1 minute
        self.calls_made = [call_time for call_time in self.calls_made 
                          if now - call_time < timedelta(minutes=1)]
        
        return len(self.calls_made) < self.max_calls_per_minute
    
    def record_request(self):
        """Record a new request"""
        self.calls_made.append(datetime.now())
    
    def time_until_next_request(self) -> float:
        """Get time to wait until next request (in seconds)"""
        if self.can_make_request():
            return 0.0
        
        # Find the oldest call and calculate wait time
        if self.calls_made:
            oldest_call = min(self.calls_made)
            wait_time = 60 - (datetime.now() - oldest_call).total_seconds()
            return max(0.0, wait_time)
        
        return 0.0


@dataclass
class CacheEntry:
    """Cache entry for API responses"""
    data: Any
    timestamp: datetime
    ttl_seconds: int
    cost: float = 0.0
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return datetime.now() - self.timestamp > timedelta(seconds=self.ttl_seconds)


class EnhancedAIClient:
    """Enhanced AI client with advanced coordination and optimization features"""
    
    def __init__(self):
        self.logger = logging.getLogger("enhanced_ai_client")
        
        # Initialize Redis for caching and coordination
        self.redis_client = None
        # Safely initialize async Redis from a sync context
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(self._init_redis())
            else:
                # No running loop yet; run a short init synchronously
                asyncio.run(self._init_redis())
        except Exception as _e:
            # Defer initialization gracefully; client will be None until first use
            self.logger.warning(f"Redis async init deferred: {_e}")
            try:
                # Provide a lazy client without ping to avoid loud warnings
                self.redis_client = redis.from_url(settings.REDIS_URL)
            except Exception:
                self.redis_client = None
        
        # Service configurations
        self.service_configs = self._initialize_service_configs()
        
        # Circuit breakers for each provider
        self.circuit_breakers = {
            provider: CircuitBreaker(
                provider=provider,
                config=CircuitBreakerConfig()
            ) for provider in AIServiceProvider
        }
        
        # Rate limiters for each provider
        self.rate_limiters = {
            provider: RateLimiter(
                provider=provider,
                max_calls_per_minute=config.rate_limit_per_minute
            ) for provider, config in self.service_configs.items()
        }
        
        # In-memory cache for responses
        self.response_cache: Dict[str, CacheEntry] = {}
        
        # Performance metrics
        self.performance_metrics = {
            provider: {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_cost": 0.0,
                "average_response_time": 0.0,
                "last_request_time": None
            } for provider in AIServiceProvider
        }
        
        # Initialize AI service clients
        self.ai_clients = {}
        self._initialize_ai_clients()
    
    async def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            self.logger.info("Redis connection established")
        except Exception as e:
            self.logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
    
    def _initialize_service_configs(self) -> Dict[AIServiceProvider, ServiceConfig]:
        """Initialize AI service configurations"""
        configs = {
            AIServiceProvider.OPENAI: ServiceConfig(
                provider=AIServiceProvider.OPENAI,
                api_key=settings.OPENAI_API_KEY,
                base_url="https://api.openai.com/v1",
                rate_limit_per_minute=60,
                cost_per_token=0.002,
                cost_per_image=0.02,
                cost_per_second_video=0.0,
                timeout_seconds=120,
                priority=1,
                capabilities=[TaskType.TEXT_GENERATION, TaskType.IMAGE_GENERATION, TaskType.PROMPT_ENHANCEMENT]
            ),
            AIServiceProvider.ANTHROPIC: ServiceConfig(
                provider=AIServiceProvider.ANTHROPIC,
                api_key=settings.ANTHROPIC_API_KEY,
                base_url="https://api.anthropic.com",
                rate_limit_per_minute=50,
                cost_per_token=0.0015,
                cost_per_image=0.0,
                cost_per_second_video=0.0,
                timeout_seconds=90,
                priority=2,
                capabilities=[TaskType.TEXT_GENERATION, TaskType.PROMPT_ENHANCEMENT]
            ),
            AIServiceProvider.STABILITY_AI: ServiceConfig(
                provider=AIServiceProvider.STABILITY_AI,
                api_key=settings.STABILITY_API_KEY,
                base_url="https://api.stability.ai",
                rate_limit_per_minute=40,
                cost_per_token=0.0,
                cost_per_image=0.04,
                cost_per_second_video=0.0,
                timeout_seconds=180,
                priority=2,
                capabilities=[TaskType.IMAGE_GENERATION]
            ),
            AIServiceProvider.RUNWAY_ML: ServiceConfig(
                provider=AIServiceProvider.RUNWAY_ML,
                api_key=settings.RUNWAY_API_KEY,
                base_url="https://api.runwayml.com/v1",
                rate_limit_per_minute=20,
                cost_per_token=0.0,
                cost_per_image=0.0,
                cost_per_second_video=0.125,
                timeout_seconds=300,
                priority=1,
                capabilities=[TaskType.VIDEO_GENERATION]
            )
        }
        
        # Filter out configs without API keys
        return {
            provider: config for provider, config in configs.items()
            if config.api_key
        }
    
    def _initialize_ai_clients(self):
        """Initialize specific AI service clients"""
        if AIServiceProvider.OPENAI in self.service_configs:
            self.ai_clients[AIServiceProvider.OPENAI] = openai.AsyncOpenAI(
                api_key=self.service_configs[AIServiceProvider.OPENAI].api_key
            )
    
    async def generate_text(
        self,
        prompt: str,
        task_type: TaskType = TaskType.TEXT_GENERATION,
        preferred_provider: Optional[AIServiceProvider] = None,
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        cache_ttl: int = 3600,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text with intelligent provider selection and fallback"""
        
        # Generate cache key
        cache_key = self._generate_cache_key("text", prompt, model, max_tokens, temperature, **kwargs)
        
        # Check cache first
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            self.logger.info("Returning cached text generation response")
            return cached_response
        
        # Select optimal provider
        providers = self._select_providers_for_task(task_type, preferred_provider)
        
        last_error = None
        for provider in providers:
            try:
                # Check circuit breaker and rate limits
                if not await self._can_make_request(provider):
                    continue
                
                # Make request
                start_time = time.time()
                result = await self._generate_text_with_provider(
                    provider, prompt, model, max_tokens, temperature, **kwargs
                )
                response_time = time.time() - start_time
                
                # Record success metrics
                await self._record_success(provider, response_time, result.get("usage", {}).get("total_tokens", 0))
                
                # Cache response
                await self._cache_response(cache_key, result, cache_ttl, result.get("cost", 0.0))
                
                # Add provider info to result
                result["provider"] = provider.value
                result["response_time"] = response_time
                
                return result
                
            except Exception as e:
                last_error = e
                await self._record_failure(provider, str(e))
                self.logger.warning(f"Text generation failed with {provider.value}: {str(e)}")
                continue
        
        # All providers failed
        raise Exception(f"All text generation providers failed. Last error: {str(last_error)}")
    
    async def generate_image(
        self,
        prompt: str,
        preferred_provider: Optional[AIServiceProvider] = None,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
        cache_ttl: int = 7200,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image with intelligent provider selection and fallback"""
        
        # Generate cache key
        cache_key = self._generate_cache_key("image", prompt, model, size, quality, **kwargs)
        
        # Check cache first
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            self.logger.info("Returning cached image generation response")
            return cached_response
        
        # Select optimal provider
        providers = self._select_providers_for_task(TaskType.IMAGE_GENERATION, preferred_provider)
        
        last_error = None
        for provider in providers:
            try:
                # Check circuit breaker and rate limits
                if not await self._can_make_request(provider):
                    continue
                
                # Make request
                start_time = time.time()
                result = await self._generate_image_with_provider(
                    provider, prompt, model, size, quality, **kwargs
                )
                response_time = time.time() - start_time
                
                # Record success metrics
                await self._record_success(provider, response_time, 0)  # Images don't use tokens
                
                # Cache response
                cost = self.service_configs[provider].cost_per_image
                await self._cache_response(cache_key, result, cache_ttl, cost)
                
                # Add provider info to result
                result["provider"] = provider.value
                result["response_time"] = response_time
                result["cost"] = cost
                
                return result
                
            except Exception as e:
                last_error = e
                await self._record_failure(provider, str(e))
                self.logger.warning(f"Image generation failed with {provider.value}: {str(e)}")
                continue
        
        # All providers failed
        raise Exception(f"All image generation providers failed. Last error: {str(last_error)}")
    
    async def generate_video(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        duration: int = 4,
        preferred_provider: Optional[AIServiceProvider] = None,
        cache_ttl: int = 1800,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video with intelligent provider selection and fallback"""
        
        # Generate cache key
        cache_key = self._generate_cache_key("video", prompt, image_url, duration, **kwargs)
        
        # Check cache first (videos are expensive, so caching is important)
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            self.logger.info("Returning cached video generation response")
            return cached_response
        
        # Select optimal provider
        providers = self._select_providers_for_task(TaskType.VIDEO_GENERATION, preferred_provider)
        
        last_error = None
        for provider in providers:
            try:
                # Check circuit breaker and rate limits
                if not await self._can_make_request(provider):
                    continue
                
                # Make request
                start_time = time.time()
                result = await self._generate_video_with_provider(
                    provider, prompt, image_url, duration, **kwargs
                )
                response_time = time.time() - start_time
                
                # Record success metrics
                await self._record_success(provider, response_time, 0)
                
                # Cache response
                cost = self.service_configs[provider].cost_per_second_video * duration
                await self._cache_response(cache_key, result, cache_ttl, cost)
                
                # Add provider info to result
                result["provider"] = provider.value
                result["response_time"] = response_time
                result["cost"] = cost
                
                return result
                
            except Exception as e:
                last_error = e
                await self._record_failure(provider, str(e))
                self.logger.warning(f"Video generation failed with {provider.value}: {str(e)}")
                continue
        
        # All providers failed
        raise Exception(f"All video generation providers failed. Last error: {str(last_error)}")
    
    def _select_providers_for_task(
        self,
        task_type: TaskType,
        preferred_provider: Optional[AIServiceProvider] = None
    ) -> List[AIServiceProvider]:
        """Select optimal providers for a task based on capabilities, cost, and performance"""
        
        # Get providers that support this task type
        capable_providers = [
            provider for provider, config in self.service_configs.items()
            if task_type in config.capabilities
        ]
        
        # Filter out providers with open circuit breakers
        available_providers = [
            provider for provider in capable_providers
            if self.circuit_breakers[provider].should_allow_request()
        ]
        
        if not available_providers:
            # If no providers available, try all capable providers (emergency fallback)
            available_providers = capable_providers
        
        # If preferred provider is available, prioritize it
        if preferred_provider and preferred_provider in available_providers:
            result = [preferred_provider]
            result.extend([p for p in available_providers if p != preferred_provider])
            return result
        
        # Sort by priority and performance
        def provider_score(provider: AIServiceProvider) -> float:
            config = self.service_configs[provider]
            metrics = self.performance_metrics[provider]
            
            # Base score from priority (lower is better)
            score = config.priority
            
            # Adjust for success rate
            if metrics["total_requests"] > 0:
                success_rate = metrics["successful_requests"] / metrics["total_requests"]
                score *= (2.0 - success_rate)  # Penalty for low success rate
            
            # Adjust for response time
            if metrics["average_response_time"] > 0:
                score *= (1.0 + metrics["average_response_time"] / 60.0)  # Penalty for slow response
            
            return score
        
        return sorted(available_providers, key=provider_score)
    
    async def _can_make_request(self, provider: AIServiceProvider) -> bool:
        """Check if request can be made to provider (circuit breaker + rate limits)"""
        
        # Check circuit breaker
        if not self.circuit_breakers[provider].should_allow_request():
            self.logger.warning(f"Circuit breaker open for {provider.value}")
            return False
        
        # Check rate limits
        rate_limiter = self.rate_limiters[provider]
        if not rate_limiter.can_make_request():
            wait_time = rate_limiter.time_until_next_request()
            if wait_time > 30:  # Don't wait more than 30 seconds
                self.logger.warning(f"Rate limit exceeded for {provider.value}, wait time: {wait_time}s")
                return False
            else:
                self.logger.info(f"Rate limit reached for {provider.value}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
        
        return True
    
    async def _generate_text_with_provider(
        self,
        provider: AIServiceProvider,
        prompt: str,
        model: Optional[str],
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text with specific provider"""
        
        if provider == AIServiceProvider.OPENAI:
            return await self._generate_text_openai(prompt, model, max_tokens, temperature, **kwargs)
        elif provider == AIServiceProvider.ANTHROPIC:
            return await self._generate_text_anthropic(prompt, model, max_tokens, temperature, **kwargs)
        else:
            raise ValueError(f"Text generation not supported for {provider.value}")
    
    async def _generate_image_with_provider(
        self,
        provider: AIServiceProvider,
        prompt: str,
        model: Optional[str],
        size: str,
        quality: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image with specific provider"""
        
        if provider == AIServiceProvider.OPENAI:
            return await self._generate_image_openai(prompt, model, size, quality, **kwargs)
        elif provider == AIServiceProvider.STABILITY_AI:
            return await self._generate_image_stability(prompt, size, **kwargs)
        else:
            raise ValueError(f"Image generation not supported for {provider.value}")
    
    async def _generate_video_with_provider(
        self,
        provider: AIServiceProvider,
        prompt: str,
        image_url: Optional[str],
        duration: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video with specific provider"""
        
        if provider == AIServiceProvider.RUNWAY_ML:
            return await self._generate_video_runway(prompt, image_url, duration, **kwargs)
        else:
            raise ValueError(f"Video generation not supported for {provider.value}")
    
    async def _generate_text_openai(
        self,
        prompt: str,
        model: Optional[str],
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text using OpenAI"""
        
        client = self.ai_clients[AIServiceProvider.OPENAI]
        model = model or "gpt-4o-mini"
        
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
        
        usage = response.usage
        cost = (usage.total_tokens / 1000) * self.service_configs[AIServiceProvider.OPENAI].cost_per_token
        
        return {
            "content": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            },
            "model": response.model,
            "cost": cost
        }
    
    async def _generate_text_anthropic(
        self,
        prompt: str,
        model: Optional[str],
        max_tokens: int,
        temperature: float,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate text using Anthropic (placeholder implementation)"""
        
        # This would require the Anthropic SDK
        # For now, returning a placeholder
        raise NotImplementedError("Anthropic integration not yet implemented")
    
    async def _generate_image_openai(
        self,
        prompt: str,
        model: Optional[str],
        size: str,
        quality: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image using OpenAI DALL-E"""
        
        client = self.ai_clients[AIServiceProvider.OPENAI]
        model = model or "dall-e-3"
        
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
            **kwargs
        )
        
        return {
            "image_url": response.data[0].url,
            "revised_prompt": getattr(response.data[0], 'revised_prompt', prompt),
            "model": model,
            "size": size,
            "quality": quality
        }
    
    async def _generate_image_stability(
        self,
        prompt: str,
        size: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate image using Stability AI"""
        
        # Parse size
        width, height = map(int, size.split('x'))
        
        headers = {
            "Authorization": f"Bearer {self.service_configs[AIServiceProvider.STABILITY_AI].api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "width": width,
            "height": height,
            "cfg_scale": kwargs.get("cfg_scale", 7.0),
            "steps": kwargs.get("steps", 20),
            "samples": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Stability AI error: {error_text}")
                
                result = await response.json()
                
                return {
                    "image_base64": result["artifacts"][0]["base64"],
                    "seed": result["artifacts"][0]["seed"],
                    "finish_reason": result["artifacts"][0]["finishReason"],
                    "model": "stable-diffusion-xl-1024-v1-0"
                }
    
    async def _generate_video_runway(
        self,
        prompt: str,
        image_url: Optional[str],
        duration: int,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate video using Runway ML"""
        
        headers = {
            "Authorization": f"Bearer {self.service_configs[AIServiceProvider.RUNWAY_ML].api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "textPrompt": prompt,
            "duration": duration,
            **kwargs
        }
        
        if image_url:
            payload["imageUrl"] = image_url
        
        async with aiohttp.ClientSession() as session:
            # Start generation
            async with session.post(
                "https://api.runwayml.com/v1/video/generate",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Runway API error: {error_text}")
                
                generation_data = await response.json()
                task_id = generation_data["id"]
            
            # Poll for completion
            return await self._poll_runway_generation(session, headers, task_id)
    
    async def _poll_runway_generation(
        self,
        session: aiohttp.ClientSession,
        headers: Dict[str, str],
        task_id: str,
        max_wait: int = 300
    ) -> Dict[str, Any]:
        """Poll Runway API for generation completion"""
        
        start_time = time.time()
        
        while True:
            async with session.get(
                f"https://api.runwayml.com/v1/video/generate/{task_id}",
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Runway polling error: {error_text}")
                
                result = await response.json()
                status = result.get("status")
                
                if status == "COMPLETED":
                    return {
                        "video_url": result["output"][0],
                        "task_id": task_id,
                        "duration": result.get("duration"),
                        "status": status
                    }
                elif status == "FAILED":
                    error_msg = result.get("error", "Unknown error")
                    raise Exception(f"Runway generation failed: {error_msg}")
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > max_wait:
                    raise Exception("Runway generation timed out")
                
                # Wait before next poll
                await asyncio.sleep(5)
    
    async def _record_success(self, provider: AIServiceProvider, response_time: float, tokens_used: int):
        """Record successful request metrics"""
        
        metrics = self.performance_metrics[provider]
        metrics["total_requests"] += 1
        metrics["successful_requests"] += 1
        metrics["last_request_time"] = datetime.now()
        
        # Update average response time
        current_avg = metrics["average_response_time"]
        total_successful = metrics["successful_requests"]
        metrics["average_response_time"] = ((current_avg * (total_successful - 1)) + response_time) / total_successful
        
        # Update cost tracking
        if tokens_used > 0:
            token_cost = (tokens_used / 1000) * self.service_configs[provider].cost_per_token
            metrics["total_cost"] += token_cost
        
        # Record success in circuit breaker
        self.circuit_breakers[provider].record_success()
        
        # Record request in rate limiter
        self.rate_limiters[provider].record_request()
    
    async def _record_failure(self, provider: AIServiceProvider, error_message: str):
        """Record failed request metrics"""
        
        metrics = self.performance_metrics[provider]
        metrics["total_requests"] += 1
        metrics["failed_requests"] += 1
        metrics["last_request_time"] = datetime.now()
        
        # Record failure in circuit breaker
        self.circuit_breakers[provider].record_failure()
        
        # Log failure
        self.logger.error(f"Request failed for {provider.value}: {error_message}")
    
    def _generate_cache_key(self, operation: str, *args, **kwargs) -> str:
        """Generate cache key for request"""
        
        # Create deterministic hash from parameters
        params_str = f"{operation}:{':'.join(map(str, args))}:{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"
        return hashlib.md5(params_str.encode()).hexdigest()
    
    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response"""
        
        # Try Redis first
        if self.redis_client:
            try:
                cached_data = await self.redis_client.get(f"ai_cache:{cache_key}")
                if cached_data:
                    entry_data = json.loads(cached_data)
                    entry = CacheEntry(**entry_data)
                    if not entry.is_expired():
                        self.logger.info(f"Cache hit for key: {cache_key}")
                        return entry.data
                    else:
                        # Remove expired entry
                        await self.redis_client.delete(f"ai_cache:{cache_key}")
            except Exception as e:
                self.logger.warning(f"Redis cache read failed: {e}")
        
        # Try in-memory cache
        if cache_key in self.response_cache:
            entry = self.response_cache[cache_key]
            if not entry.is_expired():
                self.logger.info(f"Memory cache hit for key: {cache_key}")
                return entry.data
            else:
                # Remove expired entry
                del self.response_cache[cache_key]
        
        return None
    
    async def _cache_response(self, cache_key: str, data: Dict[str, Any], ttl_seconds: int, cost: float):
        """Cache response"""
        
        entry = CacheEntry(
            data=data,
            timestamp=datetime.now(),
            ttl_seconds=ttl_seconds,
            cost=cost
        )
        
        # Cache in Redis
        if self.redis_client:
            try:
                entry_data = {
                    "data": entry.data,
                    "timestamp": entry.timestamp.isoformat(),
                    "ttl_seconds": entry.ttl_seconds,
                    "cost": entry.cost
                }
                await self.redis_client.setex(
                    f"ai_cache:{cache_key}",
                    ttl_seconds,
                    json.dumps(entry_data, default=str)
                )
            except Exception as e:
                self.logger.warning(f"Redis cache write failed: {e}")
        
        # Cache in memory (with size limit)
        if len(self.response_cache) > 1000:  # Limit memory cache size
            # Remove oldest entries
            oldest_keys = sorted(
                self.response_cache.keys(),
                key=lambda k: self.response_cache[k].timestamp
            )[:100]
            for old_key in oldest_keys:
                del self.response_cache[old_key]
        
        self.response_cache[cache_key] = entry
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for all providers"""
        
        return {
            "providers": {
                provider.value: {
                    **metrics,
                    "circuit_breaker_state": self.circuit_breakers[provider].state.value,
                    "rate_limit_remaining": (
                        self.rate_limiters[provider].max_calls_per_minute - 
                        len(self.rate_limiters[provider].calls_made)
                    ),
                    "last_request_time": metrics["last_request_time"].isoformat() if metrics["last_request_time"] else None
                }
                for provider, metrics in self.performance_metrics.items()
                if provider in self.service_configs
            },
            "cache_stats": {
                "memory_cache_size": len(self.response_cache),
                "total_cache_cost_saved": sum(entry.cost for entry in self.response_cache.values())
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all providers"""
        
        health_status = {}
        
        for provider in self.service_configs:
            try:
                # Simple test request based on provider capabilities
                config = self.service_configs[provider]
                
                if TaskType.TEXT_GENERATION in config.capabilities:
                    # Test with simple text generation
                    start_time = time.time()
                    await self.generate_text(
                        "Hello",
                        preferred_provider=provider,
                        max_tokens=10,
                        cache_ttl=60
                    )
                    response_time = time.time() - start_time
                    
                    health_status[provider.value] = {
                        "status": "healthy",
                        "response_time": response_time,
                        "circuit_breaker": self.circuit_breakers[provider].state.value
                    }
                else:
                    health_status[provider.value] = {
                        "status": "healthy",
                        "response_time": 0,
                        "circuit_breaker": self.circuit_breakers[provider].state.value,
                        "note": "No text generation capability for health check"
                    }
                    
            except Exception as e:
                health_status[provider.value] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "circuit_breaker": self.circuit_breakers[provider].state.value
                }
        
        return {
            "overall_status": "healthy" if all(
                status.get("status") == "healthy" 
                for status in health_status.values()
            ) else "degraded",
            "providers": health_status,
            "timestamp": datetime.now().isoformat()
        }


# Global instance
enhanced_ai_client = EnhancedAIClient()
