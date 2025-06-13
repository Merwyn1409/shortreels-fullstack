# app/__init__.py
from pathlib import Path
import os
import logging

# Create all required directories on startup
def init_directories():
    """Create all required directories if they don't exist"""
    base_dir = Path(__file__).parent.parent
    dirs = [
        base_dir / "logs",
        base_dir / "data/audio_output",
        base_dir / "data/cached_api_videos",
        base_dir / "data/output/watermarked_videos",
        base_dir / "data/output/non_watermarked_videos",
        base_dir / "public"
    ]
    
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set permissions (adjust as needed)
        os.chmod(dir_path, 0o777)

# Initialize directories when package is imported
init_directories()

# Expose config and main functions
from .config import *
from .video_fetcher import fetch_media, get_cached_videos, download_and_cache_video,cleanup_expired_cache
from .video_processor import (
    sync_audio_video,
    process_landscape_video,
    generate_modern_captions
)
from .ai_voice_generator import generate_voice
from .payment_gateway import (
    process_payment,
    verify_payment,
    capture_payment,
    client
)
from .watermark_handler import apply_watermark

__all__ = [
    'fetch_media',
    'get_cached_videos',
    'download_and_cache_video',
    'sync_audio_video', 
    'process_landscape_video',
    'generate_modern_captions',
    'apply_watermark'
]

