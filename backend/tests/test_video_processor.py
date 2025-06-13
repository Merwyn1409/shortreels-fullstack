import os
import pytest
import logging
from app.video_processor import sync_audio_video
from app.ai_voice_generator import generate_voice
from app.config import (
    OUTPUT_DIR_AUDIO,
    VIDEO_CACHE_DIR,
    WATERMARKED_VIDEO_DIR,
    NON_WATERMARKED_VIDEO_DIR
)

# Test settings
TEST_REQUEST_ID = "pytest_real_test"
TEST_VIDEO_FILES = ["difficult_thing_782fd0c7.mp4"]  # Must exist in VIDEO_CACHE_DIR
TEST_TEXT = "Believe you can and you're halfway there."

@pytest.fixture(autouse=True)
def setup_and_cleanup():
    """Setup + cleanup before/after test runs."""
    # Ensure output dirs exist
    os.makedirs(OUTPUT_DIR_AUDIO, exist_ok=True)
    os.makedirs(WATERMARKED_VIDEO_DIR, exist_ok=True)
    os.makedirs(NON_WATERMARKED_VIDEO_DIR, exist_ok=True)

    yield  # Run test

    # Cleanup: Delete generated files after test
    for dir_path in [OUTPUT_DIR_AUDIO, WATERMARKED_VIDEO_DIR, NON_WATERMARKED_VIDEO_DIR]:
        for file in os.listdir(dir_path):
            if TEST_REQUEST_ID in file:
                os.remove(os.path.join(dir_path, file))

@pytest.mark.asyncio
async def test_sync_audio_video_with_real_files():
    """Test video generation with real files (no mocks)."""
    logging.info("Starting real video generation test...")

    # 1. Verify test videos exist
    missing_videos = [
        video for video in TEST_VIDEO_FILES
        if not os.path.exists(os.path.join(VIDEO_CACHE_DIR, video))
    ]
    if missing_videos:
        pytest.skip(f"Missing test videos: {missing_videos}")

    # 2. Generate voice-over
    voice_file = generate_voice(TEST_TEXT, OUTPUT_DIR_AUDIO, TEST_REQUEST_ID)
    assert os.path.exists(voice_file), "Voice file not generated!"

    # 3. Prepare sentence data (matching TEST_TEXT)
    test_sentence_data = [{
        "sentence": TEST_TEXT,
        "videos": [os.path.join(VIDEO_CACHE_DIR, v) for v in TEST_VIDEO_FILES]
    }]

    # 4. Run sync_audio_video()
    result = await sync_audio_video(test_sentence_data, TEST_TEXT, TEST_REQUEST_ID)

    # 5. Assert outputs exist
    assert os.path.exists(result["watermarked"]), "Watermarked video missing!"
    assert os.path.exists(result["non_watermarked"]), "Non-watermarked video missing!"

    # 6. Check file sizes (basic integrity check)
    assert os.path.getsize(result["watermarked"]) > 1024, "Watermarked video too small!"
    assert os.path.getsize(result["non_watermarked"]) > 1024, "Non-watermarked video too small!"

    logging.info("✅ Test passed! Videos generated successfully.")