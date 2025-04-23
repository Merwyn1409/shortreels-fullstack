PEXELS_API_KEY = "ecJ3GPFZp3vt8BiscBxJ6xQQUKyJ7xIXebwu0QXd6zH4Al0sl9IdgOlg"
PIXABAY_API_KEY = "48860221-d1f16e06946f2226732d87b3c"
RAZORPAY_KEY_ID = "rzp_test_dMOX57nk18T2ab"
RAZORPAY_KEY_SECRET = "P6v1X4xqu58D5T2eHxZOh8Wg"
# Directory paths
OUTPUT_DIR_AUDIO = "C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/audio_output"  # Path for storing audio files
VIDEO_CACHE_DIR = "C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/cached_api_videos"
FINAL_VIDEO_DIR = "C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/output/final_videos"
WATERMARKED_VIDEO_DIR = "C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/output/watermarked_videos"
NON_WATERMARKED_VIDEO_DIR = "C:/Users/Maggie/Desktop/Shortreels_v2/backend/data/output/non_watermarked_videos"
WATERMARK_PATH="public/watermark.png"
# Define paths for watermarked and non-watermarked videos


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


