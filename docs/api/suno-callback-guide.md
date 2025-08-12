# Suno AI Callback Mechanism Guide

This guide explains the implementation and usage of the callback mechanism for the Suno AI music generation service.

## Overview

The callback mechanism allows the Suno AI service to notify our application when music generation tasks are completed, instead of using polling to check the status repeatedly. This is more efficient and provides faster response times.

## Architecture Components

### 1. Redis Service (`app/services/redis_service.py`)
- Stores callback results with TTL (Time To Live)
- Manages event flags for callback completion
- Provides methods for waiting on callbacks
- Handles cleanup of callback data

### 2. Callback Endpoints (`app/api/v1/endpoints/callbacks.py`)
- `POST /api/v1/callbacks/suno/{task_id}` - Receives callbacks from Suno AI
- `GET /api/v1/callbacks/suno/{task_id}/status` - Check callback status
- `GET /api/v1/callbacks/suno/{task_id}/result` - Retrieve callback result
- `DELETE /api/v1/callbacks/suno/{task_id}` - Cleanup callback data
- `GET /api/v1/callbacks/health` - Health check for callback system

### 3. Updated Suno Client (`app/agents/tools/ai_services/suno_client.py`)
- Generates dynamic callback URLs
- Waits for callback events instead of polling
- Falls back to polling if callbacks fail
- Cleans up callback data after use

## Configuration

Add these environment variables to your `.env` file:

```bash
# Suno AI Configuration
SUNO_API_KEY=your_suno_api_key_here
SUNO_BASE_URL=https://api.sunoapi.org

# Public API URL for callbacks (must be accessible from Suno AI servers)
PUBLIC_API_URL=https://your-domain.com

# Redis Configuration (required for callbacks)
REDIS_URL=redis://localhost:6379/0
```

## Usage Example

The callback mechanism is automatically used by the SunoClientTool:

```python
from app.agents.tools.ai_services.suno_client import SunoClientTool

# Create Suno client
suno_client = SunoClientTool()

# Generate background music (now uses callbacks automatically)
result = await suno_client.execute({
    "action": "generate_background_music",
    "parameters": {
        "description": "Upbeat travel background music",
        "mood": "happy",
        "style": "acoustic",
        "duration": 60,
        "instrumental": True
    }
})

print(f"Generated audio URL: {result['audio_url']}")
```

## Callback Flow

1. **Request Initiation**:
   - Client calls Suno AI API with callback URL
   - Callback URL format: `{PUBLIC_API_URL}/api/v1/callbacks/suno/{task_id}`

2. **Waiting for Callback**:
   - Client waits for callback event in Redis
   - Efficient event-based waiting (no polling)

3. **Callback Received**:
   - Suno AI posts completion data to callback URL
   - Endpoint stores result in Redis and sets event flag
   - Returns success response to Suno AI

4. **Result Retrieval**:
   - Client detects callback event and retrieves result
   - Result is parsed and returned to caller
   - Callback data is cleaned up automatically

## Fallback Mechanism

If callbacks fail for any reason, the system automatically falls back to polling:

- Callback timeout (default: 5 minutes)
- Redis connection issues
- Callback endpoint unavailable
- Invalid callback data format

## Testing

Run the test script to verify the callback mechanism:

```bash
cd backend
python test_suno_callback.py
```

The test script checks:
- Redis connection and operations
- Callback endpoint functionality
- URL generation
- Complete callback flow simulation

## Monitoring and Debugging

### Health Check
Check callback system health:
```bash
curl http://localhost:8000/api/v1/callbacks/health
```

### Check Callback Status
```bash
curl http://localhost:8000/api/v1/callbacks/suno/{task_id}/status
```

### Retrieve Callback Result
```bash
curl http://localhost:8000/api/v1/callbacks/suno/{task_id}/result
```

### Logs
Monitor application logs for callback-related messages:
- Callback URL generation
- Callback received notifications
- Callback processing errors
- Fallback to polling events

## Production Deployment

### Requirements
1. **Public API URL**: Must be accessible from Suno AI servers
2. **HTTPS**: Recommended for production callbacks
3. **Redis**: Required for callback storage and events
4. **Load Balancer**: Should support sticky sessions if using multiple instances

### Security Considerations
- Validate callback payloads
- Rate limit callback endpoints
- Monitor for malicious callbacks
- Use HTTPS for callback URLs

### Performance Optimization
- Set appropriate Redis TTL values
- Monitor callback response times
- Implement callback queuing for high loads
- Use Redis clustering for high availability

## Troubleshooting

### Common Issues

1. **"Please enter callBackUrl" Error**:
   - Ensure `PUBLIC_API_URL` is set correctly
   - Check that callback URL is properly formatted
   - Verify Suno AI can reach your callback endpoint

2. **Callback Timeout**:
   - Check Redis connection
   - Verify callback endpoint is accessible
   - Monitor network connectivity to Suno AI

3. **Redis Connection Failed**:
   - Ensure Redis server is running
   - Check Redis URL configuration
   - Verify Redis authentication if required

4. **Callback Not Received**:
   - Check firewall settings
   - Verify PUBLIC_API_URL is externally accessible
   - Monitor callback endpoint logs

### Debug Commands

```bash
# Test Redis connection
redis-cli -u redis://localhost:6379/0 ping

# Check callback endpoint
curl -X POST http://localhost:8000/api/v1/callbacks/suno/test \
  -H "Content-Type: application/json" \
  -d '{"status": "test", "code": 200}'

# Monitor Redis keys
redis-cli -u redis://localhost:6379/0 keys "suno_*"
```

## API Reference

### Callback Payload Format

Suno AI sends callbacks with this format:

```json
{
  "task_id": "suno_task_id_here",
  "status": "complete",
  "code": 200,
  "message": "Generation completed successfully",
  "data": {
    "data": [
      {
        "audio_url": "https://suno-ai.s3.amazonaws.com/audio/file.mp3",
        "title": "Generated Music Title",
        "duration": 45.5,
        "id": "suno_song_id"
      }
    ]
  }
}
```

### Response Format

Our callback endpoint responds with:

```json
{
  "status": "success",
  "message": "Callback received successfully",
  "task_id": "task_id_here",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Migration from Polling

If you're migrating from the polling mechanism:

1. Update environment variables (add `PUBLIC_API_URL`)
2. Ensure Redis is running and accessible
3. Deploy updated code
4. Test with `test_suno_callback.py`
5. Monitor logs for successful callback operations

The system will automatically fall back to polling if callbacks fail, ensuring backward compatibility.