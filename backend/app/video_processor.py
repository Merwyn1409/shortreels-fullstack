import os
import time
import logging
import asyncio
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips, AudioFileClip, TextClip, 
    CompositeVideoClip, vfx, CompositeAudioClip
)
import gc
from PIL import Image
from pydub import AudioSegment
from pydub.utils import which
from .watermark_handler import apply_watermark
from .config import (
    OUTPUT_DIR_AUDIO, WATERMARKED_VIDEO_DIR, 
    NON_WATERMARKED_VIDEO_DIR, THEME_CONFIG, video_process_log_FILE, MODERN_CAPTION_STYLE, WATERMARK_PATH
)
from typing import List, Tuple, Dict, Optional
from moviepy.config import change_settings
import logging.config
from .logging_config import LOGGING_CONFIG
from moviepy.video.fx import resize, crop
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from functools import wraps
import tempfile
import shutil
import subprocess

# Add a function to get the status updater
def get_status_updater():
    """Get the status updater function from main module"""
    from .main import update_request_status
    return update_request_status

try:
    logging.config.dictConfig(LOGGING_CONFIG)
except Exception as e:
    print(f"Couldn't load LOGGING_CONFIG: {e}")
    # Fallback to basic config
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(video_process_log_FILE),
            logging.StreamHandler()
        ]
    )

# 2. Then get your logger
logger = logging.getLogger("video_processor")
logger.info("Video processor module initialized")

MAX_CONCURRENT_RENDERS = min(2, multiprocessing.cpu_count() - 1)  # Reduced to prevent overload
render_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RENDERS)
logger.info(f"Initialized video render pool with {MAX_CONCURRENT_RENDERS} workers")

# Add a semaphore to limit concurrent video processing
video_processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)

# Configure FFmpeg paths
FFMPEG_BINARY = "/usr/bin/ffmpeg"
FFPROBE_BINARY = "/usr/bin/ffprobe"

# Set environment variables
os.environ["FFMPEG_BINARY"] = FFMPEG_BINARY
os.environ["FFPROBE_BINARY"] = FFPROBE_BINARY

# Configure MoviePy
change_settings({
    "FFMPEG_BINARY": FFMPEG_BINARY,
    "FFPROBE_BINARY": FFPROBE_BINARY
})

print("FFMPEG:", AudioSegment.converter)
print("FFPROBE:", AudioSegment.ffprobe)

# Auto-detect OS and set path
if os.name == 'posix':  # Linux/Unix
    change_settings({"IMAGEMAGICK_BINARY": os.getenv('IMAGEMAGICK_BINARY', '/usr/bin/convert')})
elif os.name == 'nt':  # Windows
    change_settings({"IMAGEMAGICK_BINARY": os.getenv('IMAGEMAGICK_BINARY', r'C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe')})

# Verify FFmpeg installation at startup
if not which("ffmpeg"):
    logger.error("FFmpeg not found in PATH. Please install FFmpeg.")
    raise RuntimeError("FFmpeg not found in PATH")

def safe_audio_load(audio_path: str, max_retries: int = 3) -> AudioFileClip:
    """Safely load audio file with retries and error handling"""
    for attempt in range(max_retries):
        try:
            # Load audio directly since it's already in WAV format
            audio_clip = AudioFileClip(audio_path)
            
            # Verify the audio clip is valid
            if audio_clip.duration is None or audio_clip.duration <= 0:
                audio_clip.close()
                raise ValueError(f"Invalid audio duration: {audio_clip.duration}")
            
            return audio_clip
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed to load audio {audio_path}: {e}")
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to load audio after {max_retries} attempts: {e}")
            time.sleep(0.5)  # Brief delay before retry

def safe_video_load(video_path: str, max_retries: int = 3) -> VideoFileClip:
    """Safely load video file with retries and error handling"""
    for attempt in range(max_retries):
        try:
            # Load video with explicit audio codec and fps
            video_clip = VideoFileClip(video_path, audio_fps=44100, verbose=False)
            
            # Verify the video clip is valid
            if video_clip.duration is None or video_clip.duration <= 0:
                video_clip.close()
                raise ValueError(f"Invalid video duration: {video_clip.duration}")
            
            return video_clip
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed to load video {video_path}: {e}")
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to load video after {max_retries} attempts: {e}")
            time.sleep(0.5)  # Brief delay before retry

def generate_modern_captions(sentences: List[str], sentence_timestamps: List[Tuple[str, float, float]], 
                             video_size: Tuple[int, int]) -> List[TextClip]:
                             
    """Creates modern Instagram-style animated captions at sentence level."""
    caption_clips = []
    
    if not sentences or not sentence_timestamps:
        logger.warning("Empty input to generate_modern_captions")
        return caption_clips

    for sentence, start_time, end_time in sentence_timestamps:
        try:
            if not isinstance(sentence, str):
                logger.warning(f"Skipping non-string sentence: {type(sentence)}")
                continue

            duration = end_time - start_time

            # Enhanced visual style
            txt_clip = (
                TextClip(
                    txt=sentence,
                    font=MODERN_CAPTION_STYLE["font"],
                    fontsize=MODERN_CAPTION_STYLE.get("fontsize", 60) + 10,
                    color=MODERN_CAPTION_STYLE["color"],
                    stroke_color=MODERN_CAPTION_STYLE["stroke_color"],
                    stroke_width=MODERN_CAPTION_STYLE["stroke_width"],
                    size=MODERN_CAPTION_STYLE["size"],
                    method=MODERN_CAPTION_STYLE["method"],
                    align=MODERN_CAPTION_STYLE["align"],
                    kerning=MODERN_CAPTION_STYLE["kerning"],
                    interline=MODERN_CAPTION_STYLE["interline"]
                )
                .set_position(MODERN_CAPTION_STYLE["position"], relative=True)
                .set_start(start_time)
                .set_duration(duration)
                .crossfadein(0.4)
                .crossfadeout(0.4)
            )

            caption_clips.append(txt_clip)

        except Exception as e:
            logger.warning(f"Failed to create caption for sentence: '{sentence[:30]}...' - {str(e)}")
            continue

    return caption_clips


async def process_sentence_videos(sentence_data: List[Dict], audio_files: List[Dict], request_id: str) -> List[VideoFileClip]:
    """Process videos ensuring each clip is synchronized with its corresponding sentence audio."""
    video_clips = []
    caption_clips = []
    last_end_time = 0
    
    logger.info(f"[{request_id}] Starting video processing with {len(sentence_data)} sentences")
    
    # Keep track of clips for cleanup
    clips_to_cleanup = []
    
    try:
        for i, (sentence_item, audio_item) in enumerate(zip(sentence_data, audio_files), 1):
            logger.info(f"[{request_id}] Processing sentence {i}/{len(sentence_data)}")
            
            sentence = sentence_item["sentence"]
            video_path = sentence_item["videos"][0] if sentence_item.get("videos") else None
            
            if not video_path:
                logger.error(f"[{request_id}] No video found for sentence {i}: '{sentence}'")
                raise ValueError(f"No video found for sentence {i}")
            
            audio_file = audio_item["audio_file"]
            
            logger.info(f"[{request_id}] Loading audio: {os.path.basename(audio_file)}")
            audio_clip = safe_audio_load(audio_file)
            clips_to_cleanup.append(audio_clip)
            sentence_duration = audio_clip.duration
            logger.info(f"[{request_id}] Audio loaded successfully - duration: {sentence_duration:.2f}s")
            
            logger.info(f"[{request_id}] Loading video: {video_path}")
            clip = safe_video_load(video_path)
            clips_to_cleanup.append(clip)
            logger.info(f"[{request_id}] Video loaded successfully - size: {clip.size}, duration: {clip.duration:.2f}s")
            
            logger.info(f"[{request_id}] Converting to landscape format")
            clip = process_landscape_video(clip, sentence_duration)
            logger.info(f"[{request_id}] Landscape conversion complete - new size: {clip.size}")
            
            # CRITICAL FIX: Match video duration to audio duration EXACTLY
            logger.info(f"[{request_id}] Matching durations - Video: {clip.duration:.2f}s, Audio: {sentence_duration:.2f}s")
            
            if abs(clip.duration - sentence_duration) > 0.1:  # If difference is more than 0.1s
                if clip.duration > sentence_duration:
                    clip = clip.subclip(0, sentence_duration)
                    logger.info(f"[{request_id}] Trimmed video to {sentence_duration:.2f}s")
                else:
                    clip = clip.loop(duration=sentence_duration)
                    logger.info(f"[{request_id}] Looped video to {sentence_duration:.2f}s")
            
            logger.info(f"[{request_id}] Setting audio and timing")
            clip = clip.set_audio(audio_clip)
            clip = clip.set_start(last_end_time)
            
            # Verify audio is attached
            if hasattr(clip, 'audio') and clip.audio is not None:
                logger.info(f"[{request_id}] Audio attached successfully - duration: {clip.audio.duration:.2f}s")
            else:
                logger.error(f"[{request_id}] Audio attachment failed!")
                raise ValueError("Audio attachment failed")
                
            video_clips.append(clip)
            
            # Generate caption
            logger.info(f"[{request_id}] Generating caption for sentence {i}")
            try:
                txt_clip = (
                    TextClip(
                        txt=sentence,
                        font=MODERN_CAPTION_STYLE["font"],
                        fontsize=MODERN_CAPTION_STYLE.get("fontsize", 60) + 10,
                        color=MODERN_CAPTION_STYLE["color"],
                        stroke_color=MODERN_CAPTION_STYLE["stroke_color"],
                        stroke_width=MODERN_CAPTION_STYLE["stroke_width"],
                        size=MODERN_CAPTION_STYLE["size"],
                        method=MODERN_CAPTION_STYLE["method"],
                        align=MODERN_CAPTION_STYLE["align"],
                        kerning=MODERN_CAPTION_STYLE["kerning"],
                        interline=MODERN_CAPTION_STYLE["interline"]
                    )
                    .set_position(MODERN_CAPTION_STYLE["position"], relative=True)
                    .set_start(last_end_time)
                    .set_duration(sentence_duration)
                    .crossfadein(0.4)
                    .crossfadeout(0.4)
                )
                caption_clips.append(txt_clip)
                logger.info(f"[{request_id}] Caption generated successfully")
            except Exception as e:
                logger.error(f"[{request_id}] Caption generation failed: {str(e)}")
                raise
            
            last_end_time += sentence_duration
            logger.info(f"[{request_id}] Successfully processed sentence {i}")
        
        if not video_clips:
            raise RuntimeError("No valid video clips processed")
            
        logger.info(f"[{request_id}] Combining all clips")
        final_clip = CompositeVideoClip(video_clips + caption_clips)
        
        # Verify final clip has audio
        if hasattr(final_clip, 'audio') and final_clip.audio is not None:
            logger.info(f"[{request_id}] Final composite clip has audio - duration: {final_clip.audio.duration:.2f}s")
        else:
            logger.error(f"[{request_id}] Final composite clip has NO AUDIO!")
            raise ValueError("Final clip has no audio")
        
        logger.info(f"[{request_id}] Successfully processed all sentences and videos. Total clips: {len(video_clips)}")
        for i, clip in enumerate(video_clips):
            logger.info(f"[{request_id}] Clip {i+1} duration: {clip.duration:.2f}s, start time: {clip.start:.2f}s")
        
        return [final_clip]  # Return as a list to maintain compatibility with existing code
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in process_sentence_videos: {str(e)}", exc_info=True)
        # Clean up clips on error
        for clip in clips_to_cleanup:
            try:
                clip.close()
            except:
                pass
        raise


def process_landscape_video(clip: VideoFileClip, target_duration: float) -> VideoFileClip:
    try:
        # Pre-calculate dimensions
        target_ratio = 1080 / 1920
        current_ratio = clip.size[0] / clip.size[1]
        
        # Optimize resize operations
        if current_ratio > target_ratio:
            # Scale by height first (more efficient)
            clip = clip.resize(height=1920)
            excess_width = clip.size[0] - 1080
            x1 = excess_width // 2
            x2 = clip.size[0] - (excess_width // 2)
            clip = clip.crop(x1=x1, x2=x2, y1=0, y2=1920)
        else:
            # Scale by width first (more efficient)
            clip = clip.resize(width=1080)
            excess_height = clip.size[1] - 1920
            y1 = excess_height // 2
            y2 = clip.size[1] - (excess_height // 2)
            clip = clip.crop(x1=0, x2=1080, y1=y1, y2=y2)
        
        # Optimize duration adjustment
        if clip.duration > target_duration:
            # Use fixed start time instead of random for better caching
            start_time = 0
            clip = clip.subclip(start_time, start_time + target_duration)
        elif clip.duration < target_duration:
            # Use simpler loop method
            clip = clip.loop(duration=target_duration)
        
        return clip
    except Exception as e:
        logger.error(f"Error processing landscape video: {e}")
        raise

def rate_limited(max_per_minute):
    min_interval = 60.0 / max_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait = min_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            last_called[0] = time.time()
            return await func(*args, **kwargs)
        return wrapped
    return decorator

@rate_limited(10)
async def sync_audio_video(sentence_data: List[Dict], text: str, request_id: str, voice_result: Dict = None, render_settings: Dict = None) -> Dict:
    """Synchronize audio and video, ensuring proper timing and transitions."""
    video_clips = []
    clips_to_cleanup = []
    final_clip = None
    
    try:
        # Process videos for each sentence
        video_clips = await process_sentence_videos(sentence_data, voice_result["audio_files"], request_id)
        
        if not video_clips:
            raise ValueError("No video clips generated")
            
        logger.info(f"[{request_id}] Received {len(video_clips)} video clips from process_sentence_videos")
        
        # Get the final composite clip
        final_clip = video_clips[0]  # process_sentence_videos returns a list with one composite clip
        
        # Log clip details for debugging
        logger.info(f"[{request_id}] Original Clip 1 duration: {final_clip.duration:.2f}s, start: {final_clip.start:.2f}s")
        
        # Ensure final clip has audio
        if not hasattr(final_clip, 'audio') or final_clip.audio is None:
            raise ValueError("Final clip has no audio")
        
        logger.info(f"[{request_id}] Final clip duration: {final_clip.duration:.2f}s")
        
        # Generate output filenames
        timestamp = int(time.time())
        watermarked_path = os.path.join(WATERMARKED_VIDEO_DIR, f"output_{request_id}_{timestamp}_watermarked.mp4")
        non_watermarked_path = os.path.join(NON_WATERMARKED_VIDEO_DIR, f"output_{request_id}_{timestamp}_non_watermarked.mp4")
        
        # Write videos sequentially to avoid resource conflicts
        logger.info(f"[{request_id}] Writing watermarked video...")
        watermarked_result = write_video(final_clip, watermarked_path, watermark_path=WATERMARK_PATH, request_id=request_id)
        
        logger.info(f"[{request_id}] Writing non-watermarked video...")
        non_watermarked_result = write_video(final_clip, non_watermarked_path, request_id=request_id)
        
        result = {
            "watermarked": watermarked_result,
            "non_watermarked": non_watermarked_result
        }
        
        return result
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in sync_audio_video: {str(e)}", exc_info=True)
        raise

    finally:
        # Clean up resources AFTER both videos are written
        logger.info(f"[{request_id}] Cleaning up resources...")
        
        # Clean up final clip
        if final_clip:
            try:
                final_clip.close()
            except:
                pass
        
        # Clean up individual clips
        for clip in video_clips:
            try:
                clip.close()
            except:
                pass
            
        # Clean up any other clips
        for clip in clips_to_cleanup:
            try:
                clip.close()
            except:
                pass
            
        # Force garbage collection
        gc.collect()
        
        # Note: We don't clean up video tracking here anymore
        # That's handled by the main process
        logger.info(f"[{request_id}] Resource cleanup completed")

def write_audio_separately(audio_clip, output_path, request_id):
    """Write audio to a file separately"""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
            
        # Write audio to temporary file
        audio_clip.write_audiofile(
            temp_path,
            fps=44100,
            nbytes=2,
            ffmpeg_params=['-ac', '2']
        )
        
        # Convert to final format
        cmd = [
            FFMPEG_BINARY, '-y',
            '-i', temp_path,
            '-acodec', 'aac',
            '-b:a', '192k',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
            
        return True
        
    except Exception as e:
        logger.error(f"[{request_id}] Error writing audio: {str(e)}", exc_info=True)
        return False
    finally:
        # Clean up temporary file
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass

def write_video(clip, output_path, audio_clip=None, watermark_path=None, request_id=None):
    """Write video to file with proper audio handling"""
    try:
        if not clip or not clip.duration:
            logger.error(f"[{request_id}] Invalid clip duration")
            return False

        # Ensure audio is present
        if not hasattr(clip, 'audio') or clip.audio is None:
            logger.error(f"[{request_id}] No audio found in clip")
            return False

        # Apply watermark if needed
        if watermark_path:
            logger.info(f"[{request_id}] Applying watermark")
            try:
                clip = apply_watermark(clip)
                logger.info(f"[{request_id}] Watermark applied successfully")
                if not hasattr(clip, 'audio') or clip.audio is None:
                    logger.error(f"[{request_id}] Audio lost after watermarking")
                    return False
            except Exception as e:
                logger.error(f"[{request_id}] Error applying watermark: {str(e)}", exc_info=True)
                return False

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Write video using MoviePy's write_videofile
        clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=None,
            remove_temp=True,
            fps=24,
            preset='medium',
            threads=4,
            ffmpeg_params=[
                '-movflags', '+faststart',
                '-pix_fmt', 'yuv420p',
                '-b:v', '2M',
                '-b:a', '192k'
            ],
            logger=None
        )
        logger.info(f"[{request_id}] Successfully wrote video to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"[{request_id}] Error writing video: {str(e)}", exc_info=True)
        return False
    finally:
        try:
            if clip:
                clip.close()
        except:
            pass