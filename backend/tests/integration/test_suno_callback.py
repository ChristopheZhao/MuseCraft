#!/usr/bin/env python3
"""
Test script for Suno AI callback mechanism
"""
import asyncio
import json
import httpx
import uuid
from pathlib import Path
import sys

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.redis_service import redis_service
from app.agents.tools.ai_services.suno_client import SunoClientTool
from app.core.config import settings


async def test_redis_connection():
    """Test Redis connection and basic operations"""
    print("🔧 Testing Redis connection...")
    
    try:
        # Test storing and retrieving callback result
        test_task_id = f"test_task_{uuid.uuid4()}"
        test_result = {
            "status": "complete",
            "code": 200,
            "data": {
                "data": [{
                    "audio_url": "https://example.com/test.mp3",
                    "title": "Test Song",
                    "duration": 30
                }]
            }
        }
        
        # Store result
        stored = await redis_service.store_callback_result(
            test_task_id, 
            test_result, 
            ttl=60
        )
        print(f"✅ Stored test result: {stored}")
        
        # Retrieve result
        retrieved = await redis_service.get_callback_result(test_task_id)
        print(f"✅ Retrieved test result: {retrieved is not None}")
        
        if retrieved:
            print(f"   Result status: {retrieved.get('status')}")
            print(f"   Result code: {retrieved.get('code')}")
        
        # Test event mechanism
        event_set = await redis_service.set_callback_event(test_task_id)
        print(f"✅ Set callback event: {event_set}")
        
        # Wait for event (should return immediately since we just set it)
        event_received = await redis_service.wait_for_callback_event(
            test_task_id, 
            timeout=5
        )
        print(f"✅ Event received: {event_received}")
        
        # Cleanup
        cleaned = await redis_service.cleanup_callback_data(test_task_id)
        print(f"✅ Cleanup successful: {cleaned}")
        
        return True
        
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
        return False


async def test_callback_endpoint():
    """Test the callback endpoint directly"""
    print("\n🌐 Testing callback endpoint...")
    
    try:
        test_task_id = f"endpoint_test_{uuid.uuid4()}"
        test_payload = {
            "status": "complete",
            "code": 200,
            "message": "Generation completed",
            "data": {
                "data": [{
                    "audio_url": "https://example.com/test_song.mp3",
                    "title": "Test Background Music",
                    "duration": 45
                }]
            }
        }
        
        # Send callback to our endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:8000/api/v1/callbacks/suno/{test_task_id}",
                json=test_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Callback endpoint responded: {result.get('status')}")
                print(f"   Response: {result}")
                
                # Wait a moment for background processing
                await asyncio.sleep(2)
                
                # Check if the result was stored
                stored_result = await redis_service.get_callback_result(test_task_id)
                if stored_result:
                    print(f"✅ Callback result stored successfully")
                    print(f"   Stored status: {stored_result.get('status')}")
                else:
                    print(f"❌ Callback result not found in Redis")
                
                # Cleanup
                await redis_service.cleanup_callback_data(test_task_id)
                return True
            else:
                print(f"❌ Callback endpoint error: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
    except httpx.ConnectError:
        print("❌ Could not connect to FastAPI server. Make sure it's running on port 8000.")
        return False
    except Exception as e:
        print(f"❌ Callback endpoint test failed: {e}")
        return False


async def test_suno_client_callback_url():
    """Test SunoClient callback URL generation"""
    print("\n🎵 Testing Suno client callback URL generation...")
    
    try:
        # Create Suno client instance
        suno_client = SunoClientTool()
        
        # Test callback URL generation
        test_task_id = f"suno_test_{uuid.uuid4()}"
        callback_url = await suno_client._generate_callback_url(test_task_id)
        
        print(f"✅ Generated callback URL: {callback_url}")
        
        # Validate URL format
        expected_base = settings.PUBLIC_API_URL
        expected_path = f"/api/v1/callbacks/suno/{test_task_id}"
        expected_url = f"{expected_base}{expected_path}"
        
        if callback_url == expected_url:
            print(f"✅ URL format is correct")
            return True
        else:
            print(f"❌ URL format mismatch")
            print(f"   Expected: {expected_url}")
            print(f"   Got: {callback_url}")
            return False
            
    except Exception as e:
        print(f"❌ Suno client test failed: {e}")
        return False


async def test_complete_callback_flow():
    """Test the complete callback flow simulation"""
    print("\n🔄 Testing complete callback flow...")
    
    try:
        test_task_id = f"flow_test_{uuid.uuid4()}"
        
        # Step 1: Simulate waiting for callback (in background)
        async def wait_for_callback():
            return await redis_service.wait_for_callback_event(
                test_task_id,
                timeout=10
            )
        
        # Step 2: Simulate callback arrival (after delay)
        async def simulate_callback():
            await asyncio.sleep(2)  # Simulate processing delay
            
            # Send callback
            callback_payload = {
                "status": "complete",
                "code": 200,
                "data": {
                    "data": [{
                        "audio_url": "https://example.com/flow_test.mp3",
                        "title": "Complete Flow Test",
                        "duration": 60
                    }]
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:8000/api/v1/callbacks/suno/{test_task_id}",
                    json=callback_payload,
                    timeout=10
                )
                return response.status_code == 200
        
        # Run both operations concurrently
        wait_task = asyncio.create_task(wait_for_callback())
        callback_task = asyncio.create_task(simulate_callback())
        
        # Wait for both to complete
        event_received, callback_sent = await asyncio.gather(
            wait_task, 
            callback_task,
            return_exceptions=True
        )
        
        if isinstance(event_received, bool) and event_received:
            print(f"✅ Event received successfully")
        else:
            print(f"❌ Event not received: {event_received}")
        
        if isinstance(callback_sent, bool) and callback_sent:
            print(f"✅ Callback sent successfully")
        else:
            print(f"❌ Callback failed: {callback_sent}")
        
        # Check final result
        final_result = await redis_service.get_callback_result(test_task_id)
        if final_result:
            print(f"✅ Complete flow successful")
            print(f"   Final result status: {final_result.get('status')}")
        else:
            print(f"❌ No final result found")
        
        # Cleanup
        await redis_service.cleanup_callback_data(test_task_id)
        
        return event_received and callback_sent and final_result
        
    except Exception as e:
        print(f"❌ Complete flow test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Starting Suno AI callback mechanism tests...\n")
    
    tests = [
        ("Redis Connection", test_redis_connection),
        ("Callback Endpoint", test_callback_endpoint),
        ("Suno Client URL", test_suno_client_callback_url),
        ("Complete Flow", test_complete_callback_flow)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"\n{test_name}: {status}")
        except Exception as e:
            results.append((test_name, False))
            print(f"\n{test_name}: ❌ ERROR - {e}")
    
    # Summary
    print(f"\n{'='*50}")
    print("📊 Test Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The callback mechanism is ready.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    # Close Redis connection
    await redis_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")