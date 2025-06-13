# app/logging_config.py
import logging.config
from .config import video_process_log_FILE, main_log_FILE, API_log_FILE, payment_log_FILE

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,  # Prevent FastAPI/Uvicorn from overwriting our config
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
        "video_file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": str(video_process_log_FILE),
            "mode": "a",
        },
        "main_file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": str(main_log_FILE),
            "mode": "a",
        },
        "api_file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": str(API_log_FILE),
            "mode": "a",
        },
        "payment_file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filename": str(payment_log_FILE),
            "mode": "a",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console", "main_file"],
            "level": "INFO",
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "app": {
            "handlers": ["console", "main_file"],
            "level": "INFO",
            "propagate": False,
        },
        "voice_generator": {
            "handlers": ["console", "main_file"],
            "level": "INFO",
            "propagate": False,
        },
        "video_processor": {
            "handlers": ["console", "video_file"],
            "level": "INFO",
            "propagate": False,
        },
        "api_usage": {
            "handlers": ["console", "api_file"],
            "level": "INFO",
            "propagate": False,
        },
        "payment_gateway": {
            "handlers": ["console", "payment_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "main_file"],
        "level": "INFO"
    },
}
