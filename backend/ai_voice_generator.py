import os
from gtts import gTTS
import uuid
import time
from config import OUTPUT_DIR_AUDIO  # Import the OUTPUT_DIR_AUDIO from your config

def generate_voice(text, output_folder=OUTPUT_DIR_AUDIO, request_id=None):
    """Generate voice-over for the given text dynamically."""
    os.makedirs(output_folder, exist_ok=True)
    
    timestamp = int(time.time())
    unique_id = uuid.uuid4().hex[:8]
    request_id = request_id or unique_id
    voice_file = os.path.join(output_folder, f"voice_{request_id}_{timestamp}.mp3")
    
    tts = gTTS(text=text, lang="en")
    tts.save(voice_file)
    
    return voice_file
