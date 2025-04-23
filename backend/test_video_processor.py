import os
import logging
import asyncio
from video_processor import sync_audio_video
from ai_voice_generator import generate_voice  # Import your AI voice generator

# Set test parameters
TEST_REQUEST_ID = "test1234"
TEST_VIDEO_FILES = ["embracing_challenges_90bb17da.mp4","embracing_challenges_865e6dad.mp4","resilience_power_a624babf.mp4","resilience_power_d2f60e99.mp4","strong_women_6d37dc7e.mp4","strong_women_f7f0dc90.mp4"]  # Ensure these exist in VIDEO_CACHE_DIR
TEST_TEXT = "Strong women don’t wait for permission they create inspire and lead. Every reel is a story of resilience power and confidence. Keep pushing boundaries embracing challenges and proving that nothing is impossible."

# Define output directory
OUTPUT_DIR_AUDIO = "C:\\Users\\Maggie\\Desktop\\Shortreels_v2\\backend\\data\\audio_output"
VIDEO_CACHE_DIR = "C:\\Users\\Maggie\\Desktop\\Shortreels_v2\\backend\\data\\cached_api_videos"

async def main():
    logging.basicConfig(level=logging.INFO)

    # Ensure test videos exist in cache directory
    missing_videos = [v for v in TEST_VIDEO_FILES if not os.path.exists(os.path.join(VIDEO_CACHE_DIR, v))]
    
    if missing_videos:
        logging.error(f"Missing test videos: {missing_videos}")
        return
    
    logging.info("All test videos exist. Generating AI voice-over...")

    # Generate AI voice file
    voice_file = generate_voice(TEST_TEXT, output_folder=OUTPUT_DIR_AUDIO, request_id=TEST_REQUEST_ID)

    if not os.path.exists(voice_file):
        logging.error("Voice file generation failed!")
        return
    
    logging.info(f"Voice file generated: {voice_file}")

    # Call async function correctly
    result = await sync_audio_video(TEST_VIDEO_FILES, TEST_TEXT, TEST_REQUEST_ID)

    if result:
        logging.info(f"Test successful! Final video generated: {result['final']}")
    else:
        logging.error("Test failed! Check logs for errors.")

# Run async function properly
if __name__ == "__main__":
    asyncio.run(main())
