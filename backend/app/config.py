# app/config.py
from pathlib import Path

# API Keys (in production, use environment variables)
PEXELS_API_KEY = "ecJ3GPFZp3vt8BiscBxJ6xQQUKyJ7xIXebwu0QXd6zH4Al0sl9IdgOlg"
PIXABAY_API_KEY = "48860221-d1f16e06946f2226732d87b3c"
RAZORPAY_KEY_ID = "rzp_live_erRPPpeEm5is9P"
RAZORPAY_KEY_SECRET = "EGePCCBhykI0vzoZmEWEEAdy"

# Directory paths (relative to backend folder)
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR_AUDIO = BASE_DIR / "data/audio_output"
VIDEO_CACHE_DIR = BASE_DIR / "data/cached_api_videos" 
WATERMARKED_VIDEO_DIR = BASE_DIR / "data/output/watermarked_videos"
NON_WATERMARKED_VIDEO_DIR = BASE_DIR / "data/output/non_watermarked_videos"
WATERMARK_PATH = BASE_DIR / "public/watermark.png"

# Log files
LOG_DIR = BASE_DIR / "logs"
API_log_FILE = LOG_DIR / "api_usage.log"
payment_log_FILE = LOG_DIR / "payment_gateway.log" 
video_process_log_FILE = LOG_DIR / "video_process.log"
main_log_FILE = LOG_DIR / "main.log"

# config.py
THEME_CONFIG = {
    "default": {
        # Modern caption styling (similar to Instagram Reels)
        "font": "Arial-Bold",  # Clean, modern font
        "fontsize": 70,         # Larger text for mobile viewing
        "color": "white",       # Bright text for contrast
        "bg_color": None,       # No background (transparent)
        "stroke_color": "black",# Text outline for readability
        "stroke_width": 3,      # Thicker outline
        "position": ("center", 0.8),  # 80% from top (standard for vertical videos)
        "method": "caption",    # Wraps text automatically
        "align": "center",      # Center alignment
        "size": (900, None),    # Width for vertical videos
        "kerning": 4,           # Slightly increased letter spacing
        "interline": -10,       # Tighter line spacing
        "transparency": 0.7,    # Slightly transparent for overlay
        
        # Animation settings
        "fade_in": 0.3,         # Seconds for fade in
        "fade_out": 0.3,        # Seconds for fade out
        "zoom_factor": 1.05,    # Slight zoom effect
        
        # Video processing defaults
        "target_resolution": (1080, 1920),  # Vertical 9:16
        "fps": 30,              # Smoother frame rate
        "crf": 22,              # Quality level (18-28, lower=better)
    },
    
    # Alternative styles you can choose from
    "dark_mode": {
        "color": "#ffffff",
        "stroke_color": "#121212",
        "bg_color": "#12121280",  # Semi-transparent dark
        "position": ("center", 0.7)
    },
    
    "light_mode": {
        "color": "#000000",
        "stroke_color": "#ffffff",
        "bg_color": "#ffffff80",  # Semi-transparent white
        "position": ("center", 0.85)
    },
    
    "highlight": {
        "color": "#ffffff",
        "stroke_color": "#ff3366",  # Pink accent
        "bg_color": "#00000080",
        "fontsize": 80,
        "position": ("center", 0.75)
    }
}


MODERN_CAPTION_STYLE = {
    "font": "Roboto-Black",            # Extra bold, filled-in font
    "fontsize": 100,                   # Large for bold impact
    "color": "#FFFFFF",               # White fill
    "stroke_color": "#000000",        # Black outline
    "stroke_width": 6,                 # Thick outline
    "bg_color": None,
    "position": ("center", 0.6),
    "method": "caption",
    "align": "center",
    "size": (1080, None),
    "kerning": 4,
    "interline": -10,
    "transparency": 1.0,
    "shadow": False,
    "shadow_color": None,
    "shadow_offset": None,
    "shadow_blur": None
}

