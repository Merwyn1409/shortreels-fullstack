from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, TextClip
from PIL import Image
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import logging.config
from .logging_config import LOGGING_CONFIG
from .config import WATERMARK_PATH
from functools import lru_cache

# Set up logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("watermark_handler")
logger.info("Watermark handler module initialized.")

class WatermarkConfig:
    """Simplified configuration for watermark settings"""
    def __init__(self):
        self.logo_opacity = 0.25
        self.logo_size = 0.15  # 15% of video height
        self.text_opacity = 0.50
        self.text_color = 'white'
        self.text_font = 'Arial-Bold'

class WatermarkHandler:
    """Optimized watermark handler"""
    
    def __init__(self, watermark_path: Path = WATERMARK_PATH):
        self.config = WatermarkConfig()
        self.watermark_path = watermark_path
        self._cached_watermark: Optional[np.ndarray] = None
        self._cached_text_clip: Optional[TextClip] = None
        
    @lru_cache(maxsize=1)
    def _load_watermark(self) -> np.ndarray:
        """Load and cache watermark image"""
        if self._cached_watermark is not None:
            return self._cached_watermark
            
        try:
            watermark_str = str(self.watermark_path)
            if not self.watermark_path.exists():
                raise FileNotFoundError(f"Watermark image missing: {watermark_str}")

            with Image.open(watermark_str) as img:
                # Pre-resize the watermark image to common video dimensions
                target_height = 288  # 15% of 1920
                aspect_ratio = img.width / img.height
                target_width = int(target_height * aspect_ratio)
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                self._cached_watermark = np.array(img)
            return self._cached_watermark
            
        except Exception as e:
            logger.error(f"Failed to load watermark: {str(e)}")
            raise

    def _create_watermark_clip(self, video_clip: VideoFileClip) -> ImageClip:
        """Create a single watermark clip with optimized settings"""
        watermark_array = self._load_watermark()
        
        # Create clip with optimized settings
        return (ImageClip(watermark_array)
                .set_duration(video_clip.duration)
                .set_opacity(self.config.logo_opacity)
                .set_position(('center', 'center')))
                
    @lru_cache(maxsize=32)
    def _create_text_overlay(self, video_clip: VideoFileClip) -> TextClip:
        """Create cached text overlay with simplified settings"""
        if self._cached_text_clip is not None:
            return self._cached_text_clip.set_duration(video_clip.duration)
            
        # Create text clip with optimized settings
        text_clip = (TextClip(
            "PREVIEW ONLY",
            fontsize=int(video_clip.h // 15),
            color=self.config.text_color,
            font=self.config.text_font,
            method='label'  # Use label method for faster rendering
        )
            .set_duration(video_clip.duration)
            .set_opacity(self.config.text_opacity)
            .set_position(('center', 0.45)))  # Position above the logo
            
        self._cached_text_clip = text_clip
        return text_clip
        
    def apply_watermark(self, video_clip: VideoFileClip) -> VideoFileClip:
        """Apply simplified watermark to video"""
        try:
            if not hasattr(video_clip, 'duration'):
                raise ValueError("Input video must have duration set")
                
            # Store original audio
            original_audio = video_clip.audio
            
            # Create watermark and text overlay
            watermark_clip = self._create_watermark_clip(video_clip)
            text_clip = self._create_text_overlay(video_clip)
            
            # Create final composite with just 3 elements
            watermarked_clip = CompositeVideoClip([
                video_clip,
                watermark_clip,
                text_clip
            ], use_bgclip=True)  # Use background clip for faster compositing

            # Always restore audio from original clip
            if original_audio is not None:
                watermarked_clip = watermarked_clip.set_audio(original_audio)
                logger.info(f"Restored audio to watermarked clip - duration: {original_audio.duration:.2f}s")
            else:
                logger.warning("No audio found in original clip to restore")

            return watermarked_clip

        except Exception as e:
            logger.error(f"Watermarking failed: {str(e)}", exc_info=True)
            raise

# Create singleton instance
watermark_handler = WatermarkHandler()

def apply_watermark(video_clip: VideoFileClip) -> VideoFileClip:
    """Public function to apply watermark using the singleton handler"""
    return watermark_handler.apply_watermark(video_clip) 