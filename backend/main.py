import os
import uuid
import asyncio
import logging
import time
import glob
import signal
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from video_processor import sync_audio_video
from video_fetcher import fetch_media
from ai_voice_generator import generate_voice
from payment_gateway import process_payment, verify_payment, capture_payment, client
import gc
from config import OUTPUT_DIR_AUDIO, VIDEO_CACHE_DIR, WATERMARKED_VIDEO_DIR, NON_WATERMARKED_VIDEO_DIR, FINAL_VIDEO_DIR
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
import razorpay

# Initialize Razorpay client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

LOG_FILE = "main.log"
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s",
                    handlers=[logging.FileHandler(LOG_FILE, mode='w', encoding="utf-8"), logging.StreamHandler()])

logging.info("🚀 Starting Real-Time Video Processing API...")

app = FastAPI()

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
    os.makedirs(OUTPUT_DIR_AUDIO, exist_ok=True)
    os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
    os.makedirs(WATERMARKED_VIDEO_DIR, exist_ok=True)
    os.makedirs(NON_WATERMARKED_VIDEO_DIR, exist_ok=True)
    os.makedirs(FINAL_VIDEO_DIR, exist_ok=True)
    logging.info("Ensured all required directories exist.")
    asyncio.create_task(cleanup_old_requests())

# Modify the ongoing_requests tracking to be simpler
ongoing_requests = {}  # Just tracks status and request info


# Define a constant for your mount point
DATA_MOUNT = "/data"

# Mount without name parameter
app.mount(DATA_MOUNT, StaticFiles(directory=str(Path("data").resolve())))


# Request Body Schemas (unchanged)
class PaymentDetails(BaseModel):
    amount: int
    currency: str
    request_id: str

class VideoRequest(BaseModel):
    text: str

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
        pattern = os.path.join(directory, f"output_{request_id}_*{'watermarked' if watermarked else 'non_watermarked'}.mp4")
        files = glob.glob(pattern)
        
        if not files:
            return None
            
        # Sort by creation time (newest first)
        files.sort(key=os.path.getctime, reverse=True)
        return files[0]
    except Exception as e:
        logging.error(f"Error finding video file: {str(e)}")
        return None

@app.get("/serve-video/{request_id}")
async def serve_video(request_id: str, watermarked: bool = False):
    try:
        directory = WATERMARKED_VIDEO_DIR if watermarked else NON_WATERMARKED_VIDEO_DIR
        video_path = get_latest_video_by_request(directory, request_id, watermarked)
        
        if not video_path:
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Verify file exists and is readable
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="File not found")
            
        # Add CORS headers explicitly
        headers = {
            "Access-Control-Allow-Origin": "http://localhost:8080",
            "Access-Control-Expose-Headers": "*",
            "Content-Disposition": f'inline; filename="output_{request_id}.mp4"'
        }
        
        return FileResponse(
            video_path,
            media_type='video/mp4',
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Error serving video: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving video")

def cleanup_files(request_id):
    """Clean up all files associated with a request"""
    try:
        patterns = [
            os.path.join(OUTPUT_DIR_AUDIO, f"*{request_id}*"),
            *[os.path.join(d, f"*{request_id}*") 
              for d in [VIDEO_CACHE_DIR, 
              #WATERMARKED_VIDEO_DIR, 
              #NON_WATERMARKED_VIDEO_DIR,
              FINAL_VIDEO_DIR]]
        ]
        
        for pattern in patterns:
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                    logging.debug(f"Removed {f}")
                except Exception as e:
                    logging.error(f"Error removing {f}: {e}")
        
        logging.info(f"Cleaned up files for request_id {request_id}")
    except Exception as e:
        logging.error(f"Error in cleanup_files: {str(e)}")

request_timeouts = {}
request_subprocesses = {}
request_video_map = {}

async def cleanup_old_requests():
    """Periodically clean up old requests"""
    while True:
        now = time.time()
        to_delete = [rid for rid, timeout in request_timeouts.items() if timeout < now]
        
        for request_id in to_delete:
            if ongoing_requests.get(request_id, {}).get('status') == 'processing':
                logging.warning(f"Request {request_id} timed out - cancelling")
                await cancel_processing(request_id)
            
            for dict_ref in [ongoing_requests, request_timeouts, request_subprocesses]:
                dict_ref.pop(request_id, None)
            
            cleanup_files(request_id)
        
        await asyncio.sleep(60)

async def cancel_processing(request_id):
    """Cancel an ongoing processing request"""
    if request_id not in ongoing_requests:
        return False
    
    ongoing_requests[request_id].update({
        'status': 'cancelled',
        'end_time': time.time()
    })
    
    if request_id in request_subprocesses:
        proc = request_subprocesses[request_id]
        try:
            proc.terminate()
            await asyncio.sleep(1)
            if proc.returncode is None:
                proc.kill()
        except Exception as e:
            logging.error(f"Error killing process: {str(e)}")
        finally:
            del request_subprocesses[request_id]
    
    cleanup_files(request_id)
    return True

# API Endpoints
@app.get("/")
def home():
    return {"message": "Real-Time Video Processing API is running"}

@app.post("/cancel-generation")
async def cancel_generation(request: Request):
    try:
        data = await request.json()
        request_id = data.get("request_id")
        if not request_id:
            raise HTTPException(status_code=400, detail="request_id required")
        
        success = await cancel_processing(request_id)
        if not success:
            raise HTTPException(status_code=404, detail="Request not found or already completed")
            
        return {"status": "cancellation_initiated", "request_id": request_id}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

# New debug endpoint
@app.get("/verify-file/{request_id}")
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


@app.post("/generate-video")
async def generate_video(request: VideoRequest):
    video_url = ""  # Initialize first
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")
    
    word_count = len(request.text.split())
    if word_count < 5 or word_count > 50:
        raise HTTPException(status_code=400, detail="Text must be between 5 and 50 words.")

    request_id = uuid.uuid4().hex[:8]
    start_time = time.time()
    
    # Simplified request tracking
    ongoing_requests[request_id] = {
        "status": "processing",
        "start_time": start_time,
        "text": request.text
    }
    request_timeouts[request_id] = time.time() + 3600  # 1 hour timeout

    try:
        # Step 1: Fetch media
        media_data = await fetch_media(request.text)
        
        if any(item.get("source") == "cache" for item in media_data):
            logging.info(f"Using cached videos for request_id {request_id}")
        else:
            logging.info(f"Downloaded new videos for request_id {request_id}")

        request_video_map[request_id] = media_data

        # Step 2: Generate voiceover
        voice_file = generate_voice(request.text, OUTPUT_DIR_AUDIO, request_id)
        if not voice_file or not os.path.exists(voice_file):
            raise HTTPException(status_code=500, detail="Failed to generate voice-over")
        
        # Step 3: Process video
        result = await sync_audio_video(media_data, request.text, request_id)
        
        if not result or not os.path.exists(result["watermarked"]):
            raise HTTPException(status_code=500, detail="Video processing failed")

        final_video_path = result["watermarked"]
        video_filename = os.path.basename(final_video_path)
        #video_url = f"/data/output/watermarked_videos/{video_filename}"
        video_url = f"/serve-video/{request_id}?watermarked=true" # Use the serve-video endpoint


        # Final step: Verify file
        file_ready = False
        for _ in range(30):
            if ongoing_requests[request_id]["status"] == "cancelled":
                raise HTTPException(status_code=499, detail="Request cancelled by user")
            
            try:
                if os.path.exists(final_video_path) and os.path.getsize(final_video_path) > 1024:
                    with open(final_video_path, 'rb') as f:
                        if f.read(1):
                            file_ready = True
                            break
            except:
                pass
            
            await asyncio.sleep(4)
        
        if not file_ready:
            raise HTTPException(status_code=500, detail="Video file could not be accessed")

        # Complete the process
        ongoing_requests[request_id].update({
            "status": "completed",
            "end_time": time.time(),
            "video_url": video_url,
            "filename": video_filename
        })

        return {
            "message": "Processing complete",
            "request_id": request_id,
            "video_url": video_url,
            "filename": video_filename,
            "metadata": {
                "sentences": [
                    {
                        "text": item["sentence"],
                        "video": item["videos"][0] if item["videos"] else None
                    }
                    for item in media_data
                ]
            }
        }

    except HTTPException as he:
        if he.status_code != 499:
            logging.error(f"Error processing request {request_id}: {str(he)}", exc_info=True)
        
        ongoing_requests[request_id].update({
            "status": "failed",
            "end_time": time.time(),
            "error": str(he.detail)
        })
        raise
    except Exception as e:
        logging.error(f"Error processing request {request_id}: {str(e)}", exc_info=True)
        ongoing_requests[request_id].update({
            "status": "failed",
            "end_time": time.time(),
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")
    finally:
        if request_id in request_video_map:
            del request_video_map[request_id]
        
        if request_id in ongoing_requests and ongoing_requests[request_id]["status"] in ["completed", "failed"]:
            request_timeouts[request_id] = time.time() + 600  # Keep for 10 minutes after completion
        
        gc.collect()

@app.post("/create-order")
async def create_order(payment_details: PaymentDetails):
    try:
        # For testing, use INR instead of USD
        currency = payment_details.currency  
        amount = payment_details.amount * 100  # Convert to paise
        
        order_data = {
            'amount': amount,
            'currency': currency,
            'receipt': payment_details.request_id,
            'payment_capture': 1
        }
        
        order = client.order.create(data=order_data)
        return {
            "order_id": order["id"],
            "razorpay_key": RAZORPAY_KEY_ID,
            "currency": currency,
            "amount": amount,
            "request_id": payment_details.request_id
        }
    except Exception as e:
        logging.error(f"Order creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify-payment")
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
            "paid_video_url": f"/serve-video/{data['request_id']}?watermarked=false",
            "payment_id": data['razorpay_payment_id'],
            "order_id": data['razorpay_order_id'],
            "request_id": data['request_id']
        }
        
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/get-paid-video")
async def get_paid_video(request: PaidVideoRequest):
    video_path = get_latest_video_by_request(NON_WATERMARKED_VIDEO_DIR, request.request_id)
    
    if not video_path:
        raise HTTPException(status_code=404, detail="Paid video not found.")
    
    return {
        "paid_video_url": f"/data/output/non_watermarked_videos/{os.path.basename(video_path)}",
        "request_id": request.request_id
    }
# Add temporary debug endpoint
@app.get("/debug-video-files/{request_id}")
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

# Add a simple status endpoint
@app.get("/request-status/{request_id}")
async def get_request_status(request_id: str):
    if request_id not in ongoing_requests:
        raise HTTPException(status_code=404, detail="Request not found")
    return {
        "status": ongoing_requests[request_id]["status"],
        "request_id": request_id
    }