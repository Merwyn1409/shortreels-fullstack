import os
import logging
from gtts import gTTS
import uuid
import time
from .config import OUTPUT_DIR_AUDIO  # Import the OUTPUT_DIR_AUDIO from your config
import logging.config
from .logging_config import LOGGING_CONFIG
from typing import List, Dict
import re
from nltk import sent_tokenize
import subprocess
from .text_utils import split_into_sentences

# Set up logging
try:
    logging.config.dictConfig(LOGGING_CONFIG)
except Exception as e:
    print(f"Couldn't load LOGGING_CONFIG: {e}")
    # Fallback to basic config
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("voice_generator.log"),
            logging.StreamHandler()
        ]
    )

# Now use named loggers
logger = logging.getLogger("voice_generator")
logger.info("Voice generator module initialized.")

def generate_voice_for_sentence(sentence: str, output_folder: str, request_id: str, sentence_index: int) -> str:
    """Generate voice for a single sentence."""
    try:
        # Ensure output directory exists
        os.makedirs(output_folder, exist_ok=True)
        
        # Generate filename with sentence index
        timestamp = int(time.time())
        voice_file = os.path.join(output_folder, f"voice_{request_id}_{sentence_index:03d}_{timestamp}.wav")
        
        # Generate and save voice
        tts = gTTS(text=sentence, lang="en", slow=False)
        
        # Save as temporary MP3 first (gTTS only supports MP3)
        temp_mp3 = os.path.join(output_folder, f"temp_{request_id}_{sentence_index:03d}_{timestamp}.mp3")
        tts.save(temp_mp3)
        
        # Convert MP3 to WAV with proper settings
        try:
            subprocess.run([
                'ffmpeg', '-y',
                '-i', temp_mp3,
                '-acodec', 'pcm_s16le',
                '-ar', '44100',
                '-ac', '2',
                voice_file
            ], check=True, capture_output=True)
            
            # Clean up temporary MP3 file
            os.unlink(temp_mp3)
            
        except Exception as e:
            logger.error(f"[{request_id}] Error converting audio to WAV: {str(e)}")
            if os.path.exists(temp_mp3):
                os.unlink(temp_mp3)
            raise
        
        logger.info(f"[{request_id}] Generated voice for sentence {sentence_index}: {voice_file}")
        return voice_file
        
    except Exception as e:
        logger.error(f"[{request_id}] Voice generation failed for sentence {sentence_index}: {str(e)}", exc_info=True)
        return None

async def generate_voice(text: str, request_id: str) -> Dict:
    """
    Generate voice for the given text using gTTS.
    Returns a dictionary with audio file paths.
    """
    try:
        logger.info(f"[{request_id}] Starting voice generation for text: {text}")
        
        # Split text into sentences
        sentences = split_into_sentences(text)
        logger.info(f"[{request_id}] Split text into {len(sentences)} sentences")
        
        # Process each sentence
        audio_files = []
        for i, sentence in enumerate(sentences):
            try:
                # Generate audio for this sentence
                audio_path = generate_voice_for_sentence(sentence, OUTPUT_DIR_AUDIO, request_id, i)
                if audio_path:
                    audio_files.append({"audio_file": audio_path})
                    logger.info(f"[{request_id}] Generated audio for sentence {i+1}/{len(sentences)}")
                else:
                    logger.warning(f"[{request_id}] Failed to generate audio for sentence {i+1}")
            except Exception as e:
                logger.error(f"[{request_id}] Error processing sentence {i+1}: {str(e)}")
                continue
        
        if not audio_files:
            raise ValueError(f"No audio files generated for request {request_id}")
        
        logger.info(f"[{request_id}] Successfully generated {len(audio_files)} audio files")
        return {"audio_files": audio_files}
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in generate_voice: {str(e)}", exc_info=True)
        raise