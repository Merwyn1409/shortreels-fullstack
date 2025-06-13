import os
import uuid
import asyncio
import logging
import time
import glob
import signal
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, APIRouter, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from .video_processor import sync_audio_video
from .video_fetcher import (
    fetch_media, 
    cleanup_request_tracking
)
from .text_utils import split_into_sentences
from .ai_voice_generator import generate_voice
from .payment_gateway import process_payment, verify_payment, capture_payment, client
import gc
from .config import OUTPUT_DIR_AUDIO, VIDEO_CACHE_DIR, WATERMARKED_VIDEO_DIR, NON_WATERMARKED_VIDEO_DIR
from .config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
import razorpay
import logging.config
from .logging_config import LOGGING_CONFIG
from fastapi import BackgroundTasks
os.environ["TMPDIR"] = "/tmp/moviepy"
import json
import subprocess
import aiofiles
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Set, Optional, List
import re
import multiprocessing
from functools import partial
import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Set up logging
logging.config.dictConfig(LOGGING_CONFIG)

# Now use named loggers
logger = logging.getLogger("app")
logger.info("FastAPI app started and logging configured.")

# Reduce MoviePy logging
logging.getLogger("moviepy").setLevel(logging.WARNING)

# Initialize Razorpay client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

app = FastAPI()
api_router = APIRouter()

# Add timing middleware
@app.middleware("http")
async def add_timing_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log request timing
    logger.info(
        f"Request completed: {request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.2f}s"
    )
    
    return response

# CORS Middleware - Updated with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",  # Frontend
        "http://127.0.0.1:8000",  # Backend
        "https://www.shortreels.app"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Add OPTIONS
    allow_headers=["*"],
    expose_headers=["*"]  # Important for progress tracking
)

#test
# Path normalization middleware
@app.middleware("http")
async def normalize_path(request: Request, call_next):
    path = request.url.path.replace("\\", "/")
    request.scope["path"] = path
    return await call_next(request)

@app.on_event("startup")
async def startup_event():
    # Create only the required directories
    directories = [
        OUTPUT_DIR_AUDIO,
        VIDEO_CACHE_DIR,
        WATERMARKED_VIDEO_DIR,
        NON_WATERMARKED_VIDEO_DIR
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    
    logger.info("All required directories have been created.")
    asyncio.create_task(cleanup_old_requests())
    asyncio.create_task(cleanup_expired_requests())

# Global semaphore to limit concurrent requests
MAX_CONCURRENT_REQUESTS = 3
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Request tracking with priority queue
active_requests: Dict[str, Dict] = {}
request_queue = asyncio.PriorityQueue()  # Changed to PriorityQueue for better ordering
cleanup_tasks: Dict[str, asyncio.Task] = {}

# Add request processing time estimate
def estimate_processing_time(text: str) -> int:
    """Estimate processing time in seconds based on text length"""
    word_count = len(text.split())
    # Base time + time per word
    return 30 + (word_count * 2)  # 30 seconds base + 2 seconds per word

class GenerateRequest(BaseModel):
    url: str
    watermark: str
    audio: str
    request_id: str

class VideoRequest(BaseModel):
    text: str
    request_id: str

# Add process pool for CPU-intensive tasks
process_pool = ThreadPoolExecutor(max_workers=multiprocessing.cpu_count())

# Add at the top with other constants
PROGRESS_STEPS = {
    'initializing': 5,
    'queued': 5,
    'collecting_assets': 20,
    'optimizing_audio': 40,
    'enhancing_visuals': 60,
    'composing_scene': 80,
    'polishing': 90,
    'completed': 100,
    'failed': 0,
    'cancelled': 0
}

# Add status messages mapping
STATUS_MESSAGES = {
    'initializing': 'Initializing video generation...',
    'queued': 'Waiting in queue...',
    'collecting_assets': 'Gathering content and media...',
    'optimizing_audio': 'Generating and optimizing audio...',
    'enhancing_visuals': 'Processing video assets...',
    'composing_scene': 'Composing your video...',
    'polishing': 'Adding final touches...',
    'completed': 'Video ready!',
    'failed': 'Unable to complete video generation',
    'cancelling': 'Cancelling your video...',
    'cancelled': 'Video generation cancelled'
}

async def process_video_components(request_id: str, text: str) -> Dict:
    """Process video components with improved error handling and logging."""
    try:
        logger.info(f"[{request_id}] Starting video component processing")
        
        # Split text into sentences using the centralized function
        sentences = split_into_sentences(text)
        logger.info(f"[{request_id}] Split text into {len(sentences)} sentences")
        
        # Process each sentence
        media_results = []
        for sentence in sentences:
            # Fetch media for this sentence
            videos = await fetch_media(sentence, request_id)
            if videos:
                media_results.append({
                    "sentence": sentence,
                    "videos": videos[:1]  # Take only the first video
                })
            else:
                logger.warning(f"[{request_id}] No videos found for sentence: {sentence}")
        
        if not media_results:
            raise ValueError(f"No videos found for any sentences in request {request_id}")
        
        logger.info(f"[{request_id}] Successfully processed {len(media_results)} sentences")
        return {"media_results": media_results}

    except Exception as e:
        logger.error(f"[{request_id}] Error in process_video_components: {str(e)}", exc_info=True)
        raise

async def update_request_status(request_id: str, status: str, current_step: str = None, error: str = None):
    """Update request status with progress calculation"""
    if request_id not in active_requests:
        logger.warning(f"Request {request_id} not found in active_requests")
        return False
        
    try:
        # Get progress from step mapping
        progress = PROGRESS_STEPS.get(current_step or status, 0)
        
        # Update request data
        active_requests[request_id].update({
            "status": status,
            "current_step": current_step or status,
            "progress": progress,
            "message": STATUS_MESSAGES.get(current_step or status, ""),
            "error": error,
            "last_updated": datetime.now().isoformat()
        })
        
        logger.info(f"[{request_id}] Status updated: {status}, Step: {current_step or status}, Progress: {progress}%")
        return True
        
    except Exception as e:
        logger.error(f"Error updating request status: {str(e)}")
        return False

# Add at the top with other global variables
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
request_locks: Dict[str, asyncio.Lock] = {}
REQUEST_EXPIRY_TIMEOUT = 1800  # 30 minutes in seconds
request_last_activity = {}  # Track last activity for each request

# Add pricing configuration
PRICING_CONFIG = {
    "IN": 49,  # India - ₹49
    "US": 0.99,  # USA - $0.99
    "GB": 0.79,  # UK - £0.79
    "EU": 0.89,  # Europe - €0.89
    "DEFAULT": 0.99  # Default price in USD
}

CURRENCY_CONFIG = {
    "IN": "INR",
    "US": "USD",
    "GB": "GBP",
    "EU": "EUR",
    "DEFAULT": "USD"
}

async def get_country_from_ip(ip: str) -> str:
    """Get country code from IP address"""
    try:
        # Use ipapi.co for IP geolocation (free tier)
        response = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data.get("country_code", "DEFAULT")
    except Exception as e:
        logger.error(f"Error getting country from IP: {str(e)}")
    return "DEFAULT"

@app.post("/api/generate-video")
async def generate_video(request: VideoRequest):
    """Generate a video from text and return the video URL"""
    try:
        logger.info(f"[{datetime.now().isoformat()}] Starting video generation for request {request.request_id}")
        
        # Basic validation
        if not request.text or len(request.text.strip()) < 5:
            logger.warning(f"[{datetime.now().isoformat()}] Invalid text length for request {request.request_id}")
            raise HTTPException(status_code=422, detail="Text must be at least 5 characters long")
            
        # Calculate queue position and estimated time
        queue_position = len(active_requests) + 1
        estimated_time = estimate_processing_time(request.text)
        
        # Add request to tracking with queued status
        active_requests[request.request_id] = {
            "status": "queued",
            "progress": 0,
            "current_step": "queued",
            "start_time": time.time(),
            "text": request.text,
            "estimated_time": estimated_time,
            "queue_position": queue_position,
            "last_updated": datetime.now().isoformat(),
            "priority": queue_position  # Add priority for queue ordering
        }
        
        # Add to priority queue
        await request_queue.put((queue_position, request.request_id))
        
        # If we're at capacity, return queue position
        if len([r for r in active_requests.values() if r["status"] == "processing"]) >= MAX_CONCURRENT_REQUESTS:
            logger.info(f"[{datetime.now().isoformat()}] Request {request.request_id} queued at position {queue_position}")
            return {
                "status": "queued",
                "request_id": request.request_id,
                "queue_position": queue_position,
                "estimated_time": estimated_time,
                "active_requests": len(active_requests),
                "max_concurrent": MAX_CONCURRENT_REQUESTS
            }

        # Start processing if we have capacity
        asyncio.create_task(process_next_request())
        
        return {
            "status": "processing",
            "request_id": request.request_id,
            "estimated_time": estimated_time
        }

    except Exception as e:
        logger.error(f"[{datetime.now().isoformat()}] Error generating video: {str(e)}", exc_info=True)
        cleanup_files(request.request_id)
        raise HTTPException(status_code=500, detail=str(e))

async def process_next_request():
    """Process the next request in the queue"""
    try:
        while not request_queue.empty():
            # Get next request from queue
            priority, request_id = await request_queue.get()
            
            # Check if request still exists and is queued
            if request_id not in active_requests or active_requests[request_id]["status"] != "queued":
                request_queue.task_done()
                continue
                
            # Update status to processing
            active_requests[request_id].update({
                "status": "processing",
                "current_step": "starting",
                "last_updated": datetime.now().isoformat()
            })
            
            # Start processing
            asyncio.create_task(generate_video_background(request_id, active_requests[request_id]["text"]))
            request_queue.task_done()
            
            # If we're at capacity, stop processing more requests
            if len([r for r in active_requests.values() if r["status"] == "processing"]) >= MAX_CONCURRENT_REQUESTS:
                break
                
    except Exception as e:
        logger.error(f"Error processing next request: {str(e)}", exc_info=True)

# Request Body Schemas (unchanged)
class PaymentDetails(BaseModel):
    amount: int
    currency: str
    request_id: str

class PaymentVerificationRequest(BaseModel):
    payment_id: str
    order_id: str
    razorpay_signature: str
    request_id: str

class PaidVideoRequest(BaseModel):
    request_id: str

class CancelRequest(BaseModel):
    request_id: str


# Updated Utility Functions
def get_latest_video_by_request(directory, request_id, watermarked=False):
    """Get the latest video file for a request_id with proper path handling"""
    try:
        # Use a more specific pattern to match files with timestamps
        pattern = os.path.join(directory, f"output_{request_id}_*{'watermarked' if watermarked else 'non_watermarked'}.mp4")
        files = glob.glob(pattern)
        
        if not files:
            logger.warning(f"No video files found for request {request_id} in {directory}")
            return None
            
        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)
        
        # Log the found files for debugging
        logger.debug(f"Found {len(files)} files for request {request_id}:")
        for f in files:
            logger.debug(f"File: {f}, Modified: {os.path.getmtime(f)}")
            
        latest_file = files[0]
        logger.info(f"Selected latest file for request {request_id}: {latest_file}")
        return latest_file
        
    except Exception as e:
        logger.error(f"Error finding video file: {str(e)}")
        return None

# Update the cleanup timeout constant at the top of the file
CLEANUP_TIMEOUT = 3600  # 1 hour instead of 10 minutes

# Add cleanup configuration
CLEANUP_DELAYS = {
    'abandoned': 3600,  # 1 hour for abandoned videos
    'watermarked': 86400,  # 24 hours for watermarked videos
    'paid': 604800,  # 7 days for paid videos
    'downloaded': 86400  # 24 hours after download
}

# Add download tracking
download_tracking = {}

async def track_download(request_id: str):
    """Track when a video is downloaded"""
    download_tracking[request_id] = {
        'timestamp': time.time(),
        'status': 'downloaded'
    }
    # Schedule cleanup after download delay
    asyncio.create_task(schedule_cleanup_after_download(request_id))

async def schedule_cleanup_after_download(request_id: str):
    """Schedule cleanup after download delay"""
    try:
        await asyncio.sleep(CLEANUP_DELAYS['downloaded'])
        if request_id in download_tracking:
            await cleanup_files(request_id)
            del download_tracking[request_id]
    except Exception as e:
        logger.error(f"Error in download cleanup scheduler: {str(e)}")

async def cleanup_files(request_id: str):
    """Clean up files for a request"""
    try:
        # Get request data
        request_data = active_requests.get(request_id, {})
        if not request_data:
            logger.warning(f"No request data found for {request_id}")
            return

        # Clean up files
        files_to_clean = [
            request_data.get('video_path'),
            request_data.get('audio_path'),
            request_data.get('watermarked_path')
        ]
        
        for file_path in files_to_clean:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {file_path}: {str(e)}")

        # Remove from active requests
        if request_id in active_requests:
            del active_requests[request_id]
            logger.info(f"Removed request {request_id} from active requests")

    except Exception as e:
        logger.error(f"Error in cleanup_files: {str(e)}")

request_timeouts = {}
request_subprocesses = {}
request_video_map = {}

async def cleanup_old_requests():
    """Periodically clean up old requests"""
    while True:
        now = time.time()
        to_delete = [rid for rid, timeout in request_timeouts.items() if timeout < now]
        
        for request_id in to_delete:
            if active_requests.get(request_id, {}).get('status') == 'processing':
                logger.warning(f"Request {request_id} timed out - cancelling")
                await cancel_processing(request_id)
            
            for dict_ref in [active_requests, request_timeouts, request_subprocesses]:
                dict_ref.pop(request_id, None)
            
            cleanup_files(request_id)
        
        await asyncio.sleep(60)

# Add status transition validation
VALID_STATUS_TRANSITIONS = {
    'initializing': ['processing', 'failed', 'cancelled'],
    'processing': ['completed', 'failed', 'cancelled', 'cancelling'],
    'cancelling': ['cancelled', 'failed'],
    'completed': ['cancelled'],
    'failed': ['cancelled'],
    'cancelled': [],
    'queued': ['processing', 'failed', 'cancelled'],
    'error': ['failed', 'cancelled']
}

def validate_status_transition(current_status: str, new_status: str) -> bool:
    """Validate if a status transition is allowed"""
    if current_status not in VALID_STATUS_TRANSITIONS:
        logger.warning(f"Unknown current status: {current_status}")
        return False
        
    if new_status not in VALID_STATUS_TRANSITIONS:
        logger.warning(f"Unknown new status: {new_status}")
        return False
        
    allowed_transitions = VALID_STATUS_TRANSITIONS[current_status]
    is_valid = new_status in allowed_transitions
    
    if not is_valid:
        logger.warning(
            f"Invalid status transition: {current_status} -> {new_status}. "
            f"Allowed transitions: {allowed_transitions}"
        )
    
    return is_valid

async def cancel_processing(request_id: str) -> bool:
    """Cancel an ongoing video generation request."""
    try:
        # Check if request exists
        if request_id not in active_requests:
            logger.warning(f"Cancel failed - unknown request_id: {request_id}")
            return False

        # Skip if already cancelled/completed
        current_status = active_requests[request_id].get("status")
        if current_status in ["cancelled", "completed", "failed"]:
            logger.info(f"Cancel ignored - request {request_id} already in terminal state: {current_status}")
            return False

        # Mark as cancelling
        if not update_request_status(request_id, "cancelling"):
            return False
            
        logger.info(f"Cancellation initiated for {request_id}")

        # Cancel any subprocess if exists
        if request_id in request_subprocesses:
            proc = request_subprocesses[request_id]
            try:
                # First try graceful termination
                proc.terminate()
                await asyncio.sleep(1)
                
                # If still running, force kill
                if proc.returncode is None:
                    proc.kill()
                    await asyncio.sleep(0.5)  # Give it a moment to die
                
                # Double check and force kill if still running
                if proc.returncode is None:
                    os.kill(proc.pid, signal.SIGKILL)
                
                logger.debug(f"Terminated process for {request_id}")
            except Exception as e:
                logger.error(f"Error killing process for {request_id}: {str(e)}")

        # Cleanup files
        try:
            cleanup_files(request_id)
            logger.debug(f"Cleaned up files for {request_id}")
        except Exception as e:
            logger.error(f"File cleanup failed for {request_id}: {str(e)}")

        # Final status update
        update_request_status(request_id, "cancelled",
            error="Request cancelled by user")

        # Cleanup tracking
        request_subprocesses.pop(request_id, None)
        request_timeouts[request_id] = time.time() + 600  # 10 min grace period

        # Force garbage collection
        gc.collect()

        return True

    except Exception as e:
        logger.error(f"Cancel processing failed for {request_id}: {str(e)}", exc_info=True)
        return False

async def generate_video_background(request_id: str, text: str):
    """Generate video in the background with proper error handling and status updates."""
    try:
        # Initialize request status
        await update_request_status(request_id, "initializing")
        
        # Step 1: Process video components
        await update_request_status(request_id, "collecting_assets")
        media_results = await process_video_components(request_id, text)
        if not media_results or not media_results.get("media_results"):
            raise ValueError("No media results found")
        
        # Step 2: Generate voice
        await update_request_status(request_id, "optimizing_audio")
        voice_result = await generate_voice(text, request_id)
        if not voice_result or not voice_result.get("audio_files"):
            raise ValueError("No audio files generated")
        
        # Step 3: Process and combine videos
        await update_request_status(request_id, "composing_scene")
        video_result = await sync_audio_video(
            media_results["media_results"],
            text,
            request_id,
            voice_result=voice_result
        )
        
        if not video_result:
            raise ValueError("Video processing failed")
        
        # Step 4: Finalize
        await update_request_status(request_id, "completed")
        logger.info(f"[{request_id}] Video generation completed successfully")
        
        # Add a delay before cleanup to ensure UI can get final status
        await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"[{request_id}] Error in video generation: {str(e)}", exc_info=True)
        await update_request_status(request_id, "failed", error=str(e))
        raise
    finally:
        try:
            # Clean up resources
            await cleanup_files(request_id)
            
            # Clean up video tracking
            cleanup_request_tracking(request_id)
            
            # Add another delay before removing request
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"[{request_id}] Error during cleanup: {str(e)}")
        finally:
            # Remove request after all cleanup and delays
            if request_id in active_requests:
                del active_requests[request_id]
                logger.info(f"Removed request {request_id} from active requests")

@api_router.post("/cancel-generation")
async def cancel_generation(request: Request):
    try:
        data = await request.json()
        request_id = data.get("request_id")
        
        if not request_id:
            raise HTTPException(status_code=400, detail="Request ID is required")
            
        # Check if request exists
        if request_id not in active_requests:
            raise HTTPException(status_code=404, detail="Request not found")
            
        # Update status to cancelling
        update_request_status(request_id, "cancelling")
        
        # Start cleanup process
        asyncio.create_task(cleanup_request(request_id))
        
        return {
            "status": "cancelling",
            "message": "Request cancellation initiated",
            "request_id": request_id
        }
    except Exception as e:
        logger.error(f"Error cancelling request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# API Endpoints
@app.get("/")
def home():
    return {"message": "Real-Time Video Processing API is running"}

# New debug endpoint
@api_router.get("/verify-file/{request_id}")
async def verify_file(request_id: str):
    """Verify if video file exists and get correct URL"""
    video_path = get_latest_video_by_request(WATERMARKED_VIDEO_DIR, request_id, watermarked=True)
    
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return {
        "exists": True,
        "path": video_path,
        "url": f"/data/output/watermarked_videos/{os.path.basename(video_path)}",
        "size": os.path.getsize(video_path),
        "modified": os.path.getmtime(video_path)
    }

def get_video_duration(filepath):
    """Get video duration in seconds using ffprobe"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 
             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
             str(filepath)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Couldn't get duration for {filepath}: {str(e)}")
        return 0

@api_router.get("/get-pricing")
async def get_pricing(request: Request):
    """Get pricing information based on client IP"""
    try:
        # Get client IP
        client_ip = request.client.host
        
        # Get country code
        country_code = await get_country_from_ip(client_ip)
        
        # Get price and currency for the country
        price = PRICING_CONFIG.get(country_code, PRICING_CONFIG["DEFAULT"])
        currency = CURRENCY_CONFIG.get(country_code, CURRENCY_CONFIG["DEFAULT"])
        
        # Format price based on currency
        formatted_price = format_price(price, currency)
        
        return {
            "price": price,
            "currency": currency,
            "formatted_price": formatted_price,
            "country_code": country_code
        }
    except Exception as e:
        logger.error(f"Error getting pricing: {str(e)}")
        # Return default pricing on error
        return {
            "price": PRICING_CONFIG["DEFAULT"],
            "currency": CURRENCY_CONFIG["DEFAULT"],
            "formatted_price": format_price(PRICING_CONFIG["DEFAULT"], CURRENCY_CONFIG["DEFAULT"]),
            "country_code": "DEFAULT"
        }

def format_price(price: float, currency: str) -> str:
    """Format price based on currency"""
    currency_symbols = {
        "INR": "₹",
        "USD": "$",
        "GBP": "£",
        "EUR": "€"
    }
    symbol = currency_symbols.get(currency, "$")
    
    if currency == "INR":
        return f"{symbol}{int(price)}"
    else:
        return f"{symbol}{price:.2f}"

@api_router.post("/create-order")
async def create_order(payment_details: PaymentDetails, request: Request):
    try:
        # Get pricing based on IP
        pricing = await get_pricing(request)
        
        # Convert amount to smallest currency unit (paise/cents)
        if pricing["currency"] == "INR":
            amount = int(pricing["price"] * 100)  # Convert to paise
        else:
            amount = int(pricing["price"] * 100)  # Convert to cents
        
        order_data = {
            'amount': amount,
            'currency': pricing["currency"],
            'receipt': payment_details.request_id,
            'payment_capture': 1
        }
        
        order = client.order.create(data=order_data)
        return {
            "order_id": order["id"],
            "razorpay_key": RAZORPAY_KEY_ID,
            "currency": pricing["currency"],
            "amount": amount,
            "formatted_price": pricing["formatted_price"],
            "request_id": payment_details.request_id
        }
    except Exception as e:
        logger.error(f"Order creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/verify-payment")
async def verify_payment(request: Request):
    try:
        data = await request.json()
        
        # Required fields
        required_fields = ['razorpay_payment_id', 'razorpay_order_id', 'razorpay_signature', 'request_id']
        for field in required_fields:
            if field not in data:
                raise HTTPException(status_code=422, detail=f"Missing field: {field}")
        
        # Verification
        params = {
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        }
        client.utility.verify_payment_signature(params)
        
        # Get non-watermarked video
        video_path = get_latest_video_by_request(
            NON_WATERMARKED_VIDEO_DIR,
            data['request_id']
        )
        
        if not video_path:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {
            "success": True,
            "paid_video_url": f"/api/serve-video/{data['request_id']}?watermarked=false",
            "payment_id": data['razorpay_payment_id'],
            "order_id": data['razorpay_order_id'],
            "request_id": data['request_id']
        }
        
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error(f"Payment verification failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/get-paid-video")
async def get_paid_video(request: PaidVideoRequest):
    video_path = get_latest_video_by_request(NON_WATERMARKED_VIDEO_DIR, request.request_id)
    
    if not video_path:
        raise HTTPException(status_code=404, detail="Paid video not found.")
    
    return {
        "paid_video_url": f"/data/output/non_watermarked_videos/{os.path.basename(video_path)}",
        "request_id": request.request_id
    }
# Add temporary debug endpoint
@api_router.get("/debug-video-files/{request_id}")
async def debug_video_files(request_id: str):
    """Debug endpoint to check video files"""
    files = {
        "watermarked": get_latest_video_by_request(WATERMARKED_VIDEO_DIR, request_id, True),
        "non_watermarked": get_latest_video_by_request(NON_WATERMARKED_VIDEO_DIR, request_id, False)
    }
    
    results = {}
    for name, path in files.items():
        if path:
            results[name] = {
                "path": path,
                "exists": os.path.exists(path),
                "size": os.path.getsize(path),
                "modified": os.path.getmtime(path)
            }
        else:
            results[name] = None
            
    return results

BASE_URL = "http://localhost:8000"
@api_router.get("/request-status/{request_id}")
async def get_request_status(request_id: str):
    """Get the current status of a video generation request"""
    if request_id not in active_requests:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Update last activity timestamp
    request_last_activity[request_id] = time.time()
    
    request_data = active_requests[request_id]
    current_status = request_data.get("status", "unknown")
    current_step = request_data.get("current_step", "")
    
    # Calculate queue metrics
    total_requests = len(active_requests)
    processing_requests = len([r for r in active_requests.values() if r["status"] == "processing"])
    queued_requests = total_requests - processing_requests
    
    # Get status information
    status_info = {
        "status": current_status,
        "current_step": current_step,
        "progress": request_data.get("progress", 0),
        "message": request_data.get("message", STATUS_MESSAGES.get(current_step, "")),
        "error": request_data.get("error", None),
        "estimated_time": request_data.get("estimated_time", 0),
        "queue_position": request_data.get("queue_position"),
        "active_requests": total_requests,
        "processing_requests": processing_requests,
        "queued_requests": queued_requests,
        "max_concurrent": MAX_CONCURRENT_REQUESTS
    }
    
    # Add video URLs if completed
    if current_status == "completed":
        watermarked_path = get_latest_video_by_request(WATERMARKED_VIDEO_DIR, request_id, True)
        if watermarked_path and os.path.exists(watermarked_path):
            status_info["watermarked_url"] = f"/api/serve-video/{request_id}?watermarked=true"
        non_watermarked_path = get_latest_video_by_request(NON_WATERMARKED_VIDEO_DIR, request_id, False)
        if non_watermarked_path and os.path.exists(non_watermarked_path):
            status_info["non_watermarked_url"] = f"/api/serve-video/{request_id}?watermarked=false"
    
    return status_info

# Add new endpoint to get all active requests
@api_router.get("/active-requests")
async def get_active_requests():
    """Get status of all active requests"""
    try:
        active_statuses = []
        for request_id, data in active_requests.items():
            status = {
                "request_id": request_id,
                "status": data.get("status", "unknown"),
                "progress": data.get("progress", 0),
                "current_step": data.get("current_step", "preparing"),
                "start_time": data.get("start_time", 0),
                "duration": data.get("duration", 0),
                "text": data.get("text", "")
            }
            if status["status"] == "queued":
                status["queue_position"] = len(active_requests)
            active_statuses.append(status)
        
        return {
            "active_requests": active_statuses,
            "total_processing": len(active_requests),
            "max_concurrent": MAX_CONCURRENT_REQUESTS
        }
    except Exception as e:
        logger.error(f"Error getting active requests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add new endpoint to get server status
@api_router.get("/server-status")
async def get_server_status():
    """Get current server status including queue information"""
    return {
        "active_requests": len(active_requests),
        "max_concurrent": MAX_CONCURRENT_REQUESTS,
        "queue_size": len(active_requests),
        "available_slots": MAX_CONCURRENT_REQUESTS - len(active_requests),
        "status": "busy" if len(active_requests) >= MAX_CONCURRENT_REQUESTS else "available"
    }

# Add new endpoint to check video availability
@api_router.get("/video-status/{request_id}")
async def get_video_status(request_id: str):
    """Get the status and availability of a video"""
    try:
        if request_id not in active_requests:
            return {
                "status": "not_found",
                "message": "Video not found"
            }
            
        request_data = active_requests[request_id]
        is_paid = request_id in download_tracking
        
        # Check if files exist
        watermarked_path = get_latest_video_by_request(WATERMARKED_VIDEO_DIR, request_id, True)
        non_watermarked_path = get_latest_video_by_request(NON_WATERMARKED_VIDEO_DIR, request_id, False)
        
        return {
            "status": request_data.get("status"),
            "is_paid": is_paid,
            "watermarked_available": bool(watermarked_path),
            "non_watermarked_available": bool(non_watermarked_path),
            "download_tracking": download_tracking.get(request_id),
            "message": "Video is available for download" if (watermarked_path or non_watermarked_path) else "Video is no longer available"
        }
        
    except Exception as e:
        logger.error(f"Error getting video status: {str(e)}")
        raise HTTPException(status_code=500, detail="Error checking video status")

# Mount static directories
# app.mount("/data", StaticFiles(directory=str(Path("data").resolve())), name="data")

# Add serve-video endpoint
@app.get("/api/serve-video/{request_id}")
async def serve_video(request_id: str, watermarked: bool = True):
    """Serve video files with proper error handling and streaming"""
    try:
        # Get the appropriate directory based on watermarked flag
        directory = WATERMARKED_VIDEO_DIR if watermarked else NON_WATERMARKED_VIDEO_DIR
        
        # Get the latest video file for this request
        video_path = get_latest_video_by_request(directory, request_id, watermarked)
        
        if not video_path or not os.path.exists(video_path):
            logger.error(f"Video file not found for request {request_id} in {directory}")
            raise HTTPException(status_code=404, detail="Video file not found")
            
        # Track download if this is a paid video
        if not watermarked:
            await track_download(request_id)
            
        # Return the video file with proper headers for streaming and caching
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename=f"video_{request_id}.mp4",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'attachment; filename="video_{request_id}.mp4"',
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY"
            }
        )
        
    except Exception as e:
        logger.error(f"Error serving video for request {request_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(api_router, prefix="/api")

async def cleanup_request(request_id: str):
    """Clean up resources for a completed request"""
    try:
        # Get request data
        request_data = active_requests.get(request_id)
        if not request_data:
            logger.warning(f"No request data found for {request_id}")
            return

        # Only remove from active_requests if in terminal state
        if request_data.get("status") in ["completed", "failed", "cancelled"]:
            # Clean up files
            files_to_clean = [
                request_data.get('video_path'),
                request_data.get('audio_path'),
                request_data.get('watermarked_path')
            ]
            
            for file_path in files_to_clean:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Cleaned up file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error cleaning up file {file_path}: {str(e)}")

            # Remove from active requests
            del active_requests[request_id]
            logger.info(f"Removed request {request_id} from active requests")
        else:
            logger.info(f"Request {request_id} not in terminal state, skipping cleanup")

    except Exception as e:
        logger.error(f"Error in cleanup_request: {str(e)}")

async def cleanup_expired_requests():
    """Clean up expired requests and their associated files."""
    try:
        # Get all requests
        async with AsyncSession() as session:
            result = await session.execute(select(Request))
            requests = result.scalars().all()
            
            current_time = datetime.utcnow()
            for request in requests:
                # Check if request is older than 24 hours
                if (current_time - request.created_at).total_seconds() > 86400:  # 24 hours
                    try:
                        # Update request status to expired
                        await update_request_status(request.id, "expired")
                        
                        # Delete associated files
                        if request.audio_file:
                            try:
                                os.remove(request.audio_file)
                            except:
                                pass
                        if request.video_file:
                            try:
                                os.remove(request.video_file)
                            except:
                                pass
                            
                        # Delete the request from database
                        await session.delete(request)
                        await session.commit()
                        
                    except Exception as e:
                        logger.error(f"Error cleaning up request {request.id}: {str(e)}")
                        continue
            
    except Exception as e:
        logger.error(f"Error in cleanup_expired_requests: {str(e)}")

class ShareRequest(BaseModel):
    request_id: str
    platform: str
    is_watermarked: bool = True

@app.post("/api/share")
async def share_video(request: ShareRequest):
    """Generate a shareable URL for the video."""
    try:
        # Get the video path based on watermarked status
        video_dir = WATERMARKED_VIDEO_DIR if request.is_watermarked else NON_WATERMARKED_VIDEO_DIR
        video_files = [f for f in os.listdir(video_dir) if f.startswith(f"output_{request.request_id}_")]
        
        if not video_files:
            raise HTTPException(status_code=404, detail="Video not found")
            
        # Get the most recent video file
        video_file = sorted(video_files)[-1]
        video_path = os.path.join(video_dir, video_file)
        
        # Generate a public URL for the video
        # In production, this should be your CDN or storage service URL
        video_url = f"/videos/{video_file}"
        
        # Track share event
        logger.info(f"[{request.request_id}] Video shared on {request.platform}")
        
        return {
            "success": True,
            "video_url": video_url,
            "platform": request.platform
        }
        
    except Exception as e:
        logger.error(f"Error sharing video: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))