import asyncio
import aiohttp
import time
import json
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test texts for different requests
TEST_TEXTS = [
    "The quick brown fox jumps over the lazy dog. This is test video 1.",
    "A beautiful sunset over the mountains. This is test video 2.",
    "The waves crashing on the beach. This is test video 3.",
    "A city skyline at night. This is test video 4.",
    "A forest path in autumn. This is test video 5."
]

async def generate_video(session, text, request_num):
    """Generate a single video and track its progress"""
    start_time = time.time()
    request_id = f"test_{request_num}_{int(time.time())}"
    
    try:
        # Initial request
        logger.info(f"Request {request_num}: Starting video generation")
        async with session.post(
            "http://localhost:8000/api/generate-video",
            json={"text": text, "request_id": request_id}
        ) as response:
            if response.status == 503:
                queue_info = await response.json()
                logger.info(f"Request {request_num}: Queued - {queue_info.get('detail', 'Unknown queue position')}")
            elif response.status != 200:
                error = await response.text()
                logger.error(f"Request {request_num}: Failed to start - {error}")
                return
            
            data = await response.json()
            logger.info(f"Request {request_num}: Generation started - {data}")

        # Poll for status
        while True:
            await asyncio.sleep(2)  # Poll every 2 seconds
            
            async with session.get(f"http://localhost:8000/api/status/{request_id}") as status_response:
                if status_response.status == 404:
                    logger.error(f"Request {request_num}: Not found")
                    break
                    
                status_data = await status_response.json()
                current_step = status_data.get("current_step", "unknown")
                progress = status_data.get("progress", 0)
                
                logger.info(f"Request {request_num}: {current_step} - {progress}%")
                
                if status_data.get("status") in ["completed", "failed"]:
                    end_time = time.time()
                    duration = end_time - start_time
                    logger.info(f"Request {request_num}: Completed in {duration:.2f} seconds")
                    logger.info(f"Request {request_num}: Final status - {status_data}")
                    break
                    
    except Exception as e:
        logger.error(f"Request {request_num}: Error - {str(e)}")

async def main():
    """Run multiple video generation requests in parallel"""
    start_time = time.time()
    logger.info("Starting parallel video generation test")
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all requests
        tasks = [
            generate_video(session, text, i+1)
            for i, text in enumerate(TEST_TEXTS)
        ]
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks)
    
    end_time = time.time()
    total_duration = end_time - start_time
    logger.info(f"All requests completed in {total_duration:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main()) 