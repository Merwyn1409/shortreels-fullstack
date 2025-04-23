import os
import time
import logging
import glob
import random
import asyncio
import re
from collections import defaultdict
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips, AudioFileClip, TextClip, 
    CompositeVideoClip, vfx, ColorClip
)
import gc
from pydub import AudioSegment
from watermark_handler import apply_watermark
from config import (
    OUTPUT_DIR_AUDIO, WATERMARKED_VIDEO_DIR, 
    NON_WATERMARKED_VIDEO_DIR, THEME_CONFIG, FINAL_VIDEO_DIR
)
import itertools
from itertools import cycle
from typing import List, Tuple, Dict, Optional

# Configure ImageMagick path
from moviepy.config import change_settings
#change_settings({"IMAGEMAGICK_BINARY": "C:\\Program Files\\ImageMagick-7.1.1-Q16\\magick.exe"})

# Auto-detect OS and set path
if os.name == 'posix':  # Linux/Unix
    change_settings({"IMAGEMAGICK_BINARY": os.getenv('IMAGEMAGICK_BINARY', '/usr/bin/convert')})
elif os.name == 'nt':  # Windows
    change_settings({"IMAGEMAGICK_BINARY": os.getenv('IMAGEMAGICK_BINARY', r'C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe')})

# --- Modern Caption Style ---
MODERN_CAPTION_STYLE = {
    "font": "Arial-Bold",
    "fontsize": 70,
    "color": "white",
    "bg_color": None,  # No background
    "stroke_color": "black",
    "stroke_width": 3,
    "position": ("center", 0.6),  # 80% from top
    "method": "caption",
    "align": "center",
    "size": (900, None),  # Width for vertical videos
    "kerning": 4,
    "interline": -10,
    "transparency": 0.7
}

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("video_processor.log"),
        logging.StreamHandler()
    ]
)

def find_audio_file(request_id: str) -> Optional[str]:
    """Finds the latest audio file for the given request ID."""
    patterns = [
        os.path.join(OUTPUT_DIR_AUDIO, f"*{request_id}*.mp3"),
        os.path.join(OUTPUT_DIR_AUDIO, f"*{request_id}*.wav")
    ]
    for pattern in patterns:
        audio_files = glob.glob(pattern)
        if audio_files:
            return max(audio_files, key=os.path.getctime)
    return None

def extract_word_timestamps(text: str, audio_file: str) -> List[Tuple[str, float, float]]:
    """Generates precise word-level timestamps from audio."""
    try:
        audio = AudioSegment.from_file(audio_file)
        duration = len(audio) / 1000  # Convert to seconds
        words = re.findall(r"\w+[\w'-]*|\S", text)  # Handle contractions and punctuation
        if not words:
            return []

        word_duration = duration / len(words)
        return [
            (word, i * word_duration, (i + 1) * word_duration)
            for i, word in enumerate(words)
        ]
    except Exception as e:
        logging.error(f"Timestamp extraction failed: {e}")
        return []

def generate_modern_captions(sentences: List[str], word_timestamps: List[Tuple[str, float, float]], 
                           video_size: Tuple[int, int]) -> List[TextClip]:
    """Creates modern Instagram-style animated captions."""
    caption_clips = []
    
    for sentence in sentences:
        try:
            # Find words in the sentence
            sentence_words = re.findall(r"\w+[\w'-]*|\S", sentence)
            if not sentence_words:
                continue
                
            # Find first and last word timestamps
            first_word = next((t for t in word_timestamps if t[0] == sentence_words[0]), None)
            last_word = next((t for t in reversed(word_timestamps) if t[0] == sentence_words[-1]), None)
            
            if not first_word or not last_word:
                continue
                
            start_time, end_time = first_word[1], last_word[2]
            duration = end_time - start_time
            
            # Create modern caption with animation
            txt_clip = (TextClip(
                txt=sentence,
                font=MODERN_CAPTION_STYLE["font"],
                fontsize=MODERN_CAPTION_STYLE["fontsize"],
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
            .crossfadein(0.3)  # Smooth fade in
            .crossfadeout(0.3))  # Smooth fade out
            
            caption_clips.append(txt_clip)
            
        except Exception as e:
            logging.warning(f"Failed to create caption for sentence: '{sentence[:30]}...' - {str(e)}")
            continue
    
    return caption_clips

def process_landscape_video(video_path: str, target_duration: float) -> VideoFileClip:
    """Processes landscape video to fit vertical format with zoom effects."""
    try:
        clip = VideoFileClip(video_path)
        
        # Calculate zoom factors for Ken Burns effect
        zoom_start = 1.0
        zoom_end = 1.1  # Slight zoom in
        
        # Apply zoom effect
        clip = (clip.fx(vfx.resize, lambda t: zoom_start + (zoom_end-zoom_start)*t/clip.duration)
                .resize(height=1920)  # Full height
                .crop(x1=0, y1=0, x2=1080, y2=1920))  # Crop to 9:16
                
        # Adjust duration if needed
        if clip.duration > target_duration:
            # Randomly select a segment that fits the duration
            max_start = clip.duration - target_duration
            start_time = random.uniform(0, max(max_start, 0))
            clip = clip.subclip(start_time, start_time + target_duration)
        elif clip.duration < target_duration:
            # Loop the video if it's too short
            clip = clip.loop(duration=target_duration)
            
        return clip
    except Exception as e:
        logging.error(f"Error processing landscape video {video_path}: {e}")
        raise

async def process_sentence_videos(sentence_data: List[Dict], word_timestamps: List[Tuple[str, float, float]], 
                                audio_duration: float) -> List[VideoFileClip]:
    """Processes videos for each sentence with proper timing and transitions."""
    video_clips = []
    current_time = 0
    
    for item in sentence_data:
        sentence = item["sentence"]
        videos = item["videos"]
        
        if not videos or current_time >= audio_duration:
            continue
            
        # Calculate sentence duration from word timestamps
        sentence_words = re.findall(r"\w+[\w'-]*|\S", sentence)
        first_word = next((t for t in word_timestamps if t[0] == sentence_words[0]), None)
        last_word = next((t for t in reversed(word_timestamps) if t[0] == sentence_words[-1]), None)
        
        if not first_word or not last_word:
            continue
            
        sentence_duration = min(last_word[2] - first_word[1], audio_duration - current_time)
        
        # Select and process video
        video_path = random.choice(videos)
        try:
            clip = process_landscape_video(video_path, sentence_duration)
            clip = clip.set_start(current_time)
            video_clips.append(clip)
            
            current_time += sentence_duration
            
        except Exception as e:
            logging.error(f"Error processing {video_path}: {e}")
            continue
    
    return video_clips

async def sync_audio_video(sentence_data: List[Dict], text: str, request_id: str) -> Dict:
    """Main processing function that outputs both watermarked and non-watermarked versions"""
    try:
        # --- Validate Input ---
        if not sentence_data or not text:
            raise ValueError("Missing sentence data or text")
        
        # --- Audio Setup ---
        audio_file = find_audio_file(request_id)
        if not audio_file:
            raise FileNotFoundError(f"Audio file not found for {request_id}")
        
        audio_clip = AudioFileClip(audio_file)
        audio_duration = audio_clip.duration
        
        # --- Timestamp Generation ---
        word_timestamps = extract_word_timestamps(text, audio_file)
        if not word_timestamps:
            raise RuntimeError("Failed to generate word timestamps")
        
        # --- Video Processing ---
        video_clips = await process_sentence_videos(sentence_data, word_timestamps, audio_duration)
        if not video_clips:
            raise RuntimeError("No valid video clips processed")
        
        # --- Create Background for Blank Sections ---
        background = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=audio_duration)
        
        # --- Composition ---
        video_track = CompositeVideoClip([background] + video_clips)
        video_track = video_track.set_duration(audio_duration)
        
        # --- Modern Captions ---
        sentences = [item["sentence"] for item in sentence_data]
        captions = generate_modern_captions(sentences, word_timestamps, video_track.size)
        
        # --- Final Render ---
        final_video = CompositeVideoClip([video_track] + captions)
        final_video = final_video.set_audio(audio_clip)
        
        # --- Ensure Output Directories Exist ---
        os.makedirs(NON_WATERMARKED_VIDEO_DIR, exist_ok=True)
        os.makedirs(WATERMARKED_VIDEO_DIR, exist_ok=True)
        
        # --- Generate Timestamp for Filenames ---
        timestamp = int(time.time())
        
        # --- Save Non-Watermarked Version ---
        non_watermarked_path = os.path.join(NON_WATERMARKED_VIDEO_DIR, f"output_{request_id}_{timestamp}_non_watermarked.mp4")
        await asyncio.to_thread(
            final_video.write_videofile,
            non_watermarked_path,
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="fast",
            ffmpeg_params=["-crf", "22", "-movflags", "+faststart"],
            threads=4
        )
        
        # --- Save Watermarked Version ---
        watermarked_path = os.path.join(WATERMARKED_VIDEO_DIR, f"output_{request_id}_{timestamp}_watermarked.mp4")
        watermarked_clip = apply_watermark(final_video)  # Assuming this returns a watermarked clip
        
        await asyncio.to_thread(
            watermarked_clip.write_videofile,
            watermarked_path,
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="fast",
            ffmpeg_params=["-crf", "22", "-movflags", "+faststart"],
            threads=4
        )
        
        # --- Cleanup ---
        watermarked_clip.close()
        
        return {
            "watermarked": watermarked_path,
            "non_watermarked": non_watermarked_path,
            "sentences": [
                {
                    "text": item["sentence"],
                    "video": item["videos"][0] if item["videos"] else None,
                    "duration": next(
                        (t[2] - t[1] for t in word_timestamps 
                         if t[0] in item["sentence"].split()), 0)
                }
                for item in sentence_data
            ]
        }
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}", exc_info=True)
        raise
    finally:
        # Cleanup
        for clip in locals().get("video_clips", []):
            if hasattr(clip, 'close'):
                clip.close()
        if "final_video" in locals() and hasattr(final_video, 'close'):
            final_video.close()
        if "audio_clip" in locals() and hasattr(audio_clip, 'close'):
            audio_clip.close()
        gc.collect()