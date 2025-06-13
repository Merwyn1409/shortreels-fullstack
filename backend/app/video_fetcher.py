import os
import time
import hashlib
import random
import logging
import requests
import aiofiles
import aiohttp
import nltk
import spacy
from pathlib import Path
from .config import PEXELS_API_KEY, PIXABAY_API_KEY,API_log_FILE, VIDEO_CACHE_DIR 
from .constants import FALLBACK_CATEGORIES
import asyncio
import gc
import shutil
import spacy
from nltk.corpus import wordnet
from keybert import KeyBERT
nlp = spacy.load("en_core_web_sm")
import nltk
import re
from nltk.tokenize import sent_tokenize, word_tokenize
import logging.config
from .logging_config import LOGGING_CONFIG
from pydub import AudioSegment
from pydub.utils import which
import ffmpeg
from string import punctuation
from thefuzz import fuzz
from typing import Set, Dict, List, Optional
from .text_utils import split_into_sentences

# Get a named logger specific to the video fetcher
logger = logging.getLogger("video_fetcher")
logger.info("Video fetcher logging initialized")


os.environ["PATH"] += os.pathsep + "/usr/bin"

AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffmpeg"

print("FFMPEG:", AudioSegment.converter)
print("FFPROBE:", AudioSegment.ffprobe)


def download_nltk_data():
    for pkg in ["punkt", "wordnet", "omw-1.4"]:
        nltk.download(pkg, quiet=True)
download_nltk_data()
# Init
kw_model = KeyBERT()
gc.collect()

# Logging
logging.basicConfig(filename="api_usage.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# API usage
api_usage = {"pexels": 0, "pixabay": 0}
api_limit = {"pexels": 200, "pixabay": 200}
reset_time = time.time() + 3600
CACHE_EXPIRY = 3600  # 1 hour

# Add after other global variables
used_video_urls: Set[str] = set()  # Track used video URLs
request_video_tracking: Dict[str, Set[str]] = {}  # Track used videos per request

def log_api_usage(provider):
    global api_usage, reset_time
    if time.time() > reset_time:
        api_usage = {"pexels": 0, "pixabay": 0}
        reset_time = time.time() + 3600
    api_usage[provider] += 1
    remaining = api_limit[provider] - api_usage[provider]
    logger.info(f"{provider.upper()} API used: {api_usage[provider]}/{api_limit[provider]}. Remaining: {remaining}")


def cleanup_expired_cache():
    now = time.time()
    for filename in os.listdir(VIDEO_CACHE_DIR):
        file_path = os.path.join(VIDEO_CACHE_DIR, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > CACHE_EXPIRY:
            os.remove(file_path)
            logger.info(f"Deleted expired cache: {file_path}")


def split_text_into_sentences(text):
    return sent_tokenize(text)


def get_fallback_category(sentence):
    """
    Get a fallback category using a combination of NLP and popular categories.
    First tries to extract themes from the sentence, then falls back to popular categories.
    """
    # First try to get themes from the sentence using NLP
    doc = nlp(sentence)
    themes = [token.text.lower() for token in doc if token.pos_ in ("NOUN", "ADJ")]
    
    if themes:
        # Check if any of the extracted themes match our popular categories
        matching_categories = [theme for theme in themes if theme in POPULAR_CATEGORIES]
        if matching_categories:
            return random.choice(matching_categories)
    
    # If no matching themes found, use a random popular category
    fallback = get_random_popular_category()
    logger.info(f"No matching themes found in sentence. Using fallback category: {fallback}")
    return fallback


def get_contextual_keywords(sentence: str, request_id: str) -> str:
    """Generate a single, highly relevant keyword based on sentence context, avoiding used keywords for this request."""
    # Clean the sentence
    sentence = sentence.lower().strip()
    
    # Get used keywords for this request
    used_keywords = set()
    if request_id in request_video_tracking:
        used_keywords = request_video_tracking[request_id]
    
    # Strategy 1: Use KeyBERT with specific context
    keywords = kw_model.extract_keywords(
        sentence,
        keyphrase_ngram_range=(1, 3),  # Allow up to 3 words for better context
        stop_words='english',
        top_n=3,  # Get top 3 keywords to have alternatives
        diversity=0.7
    )
    
    # Try to find a keyword that hasn't been used in this request
    if keywords:
        for keyword, _ in keywords:
            if keyword not in used_keywords:
                logger.info(f"[{request_id}] Selected unique keyword for '{sentence}': {keyword}")
                return keyword
    
    # If all keywords are used, fall back to important words
    doc = nlp(sentence)
    important_words = []
    for token in doc:
        if token.pos_ in ['NOUN', 'VERB'] and not token.is_stop:
            word = token.text.lower()
            if word not in used_keywords:
                important_words.append(word)
                if len(important_words) >= 2:
                    break
    
    if important_words:
        keyword = ' '.join(important_words[:2])
        logger.info(f"[{request_id}] Using fallback keyword for '{sentence}': {keyword}")
        return keyword
    
    # Last resort: use the sentence itself
    logger.info(f"[{request_id}] Using sentence as keyword for '{sentence}'")
    return sentence


def get_cached_videos(theme):
    cache_path = VIDEO_CACHE_DIR
    if not os.path.exists(cache_path):
        return []
    safe_theme = theme.lower().replace(" ", "_")
    return [
        os.path.join(cache_path, filename)
        for filename in os.listdir(cache_path)
        if filename.startswith(safe_theme + "_")
    ]

def caption_matches_query(caption, query, fuzzy_threshold=60):
    """
    Enhanced matching that uses multiple strategies to find relevant videos:
    1. Exact match of full query
    2. Partial match of query words
    3. Fuzzy matching with improved threshold
    4. Word overlap matching
    5. Semantic similarity using word stems and hypernyms
    6. Context-aware matching
    """
    caption_lower = caption.lower()
    query_lower = query.lower()
    
    # Remove punctuation for better matching
    caption_clean = ''.join(c for c in caption_lower if c not in punctuation)
    query_clean = ''.join(c for c in query_lower if c not in punctuation)
    
    # Split into words
    caption_words = set(caption_clean.split())
    query_words = set(query_clean.split())
    
    # Strategy 1: Exact full query match
    if query_lower in caption_lower:
        return True
    
    # Strategy 2: Fuzzy full query match with improved threshold
    if fuzz.ratio(query_lower, caption_lower) >= fuzzy_threshold:
        return True
    
    # Strategy 3: Partial ratio match (good for substrings)
    if fuzz.partial_ratio(query_lower, caption_lower) >= fuzzy_threshold:
        return True
    
    # Strategy 4: Token sort ratio (handles word order differences)
    if fuzz.token_sort_ratio(query_lower, caption_lower) >= fuzzy_threshold:
        return True
    
    # Strategy 5: Word overlap with context awareness
    matching_words = sum(1 for word in query_words if word in caption_words)
    if matching_words >= max(2, len(query_words) // 2):  # Require at least 2 words or half the words to match
        return True
    
    # Strategy 6: Semantic similarity using word stems and hypernyms
    try:
        from nltk.stem import PorterStemmer
        stemmer = PorterStemmer()
        
        # Get stems
        caption_stems = {stemmer.stem(word) for word in caption_words}
        query_stems = {stemmer.stem(word) for word in query_words}
        
        # Get hypernyms
        caption_hypernyms = set()
        query_hypernyms = set()
        
        for word in caption_words:
            for synset in wordnet.synsets(word):
                caption_hypernyms.update([h.name().split('.')[0] for h in synset.hypernyms()])
        
        for word in query_words:
            for synset in wordnet.synsets(word):
                query_hypernyms.update([h.name().split('.')[0] for h in synset.hypernyms()])
        
        # Check for stem matches
        if any(q_stem in caption_stems for q_stem in query_stems):
            return True
            
        # Check for hypernym matches
        if any(q_hyp in caption_hypernyms for q_hyp in query_hypernyms):
            return True
            
    except Exception as e:
        logger.debug(f"Semantic matching failed: {e}")
    
    # Strategy 7: Context-aware matching using spaCy
    try:
        doc_caption = nlp(caption_lower)
        doc_query = nlp(query_lower)
        
        # Check for named entity matches
        caption_entities = {ent.text.lower() for ent in doc_caption.ents}
        query_entities = {ent.text.lower() for ent in doc_query.ents}
        
        if any(q_ent in caption_entities for q_ent in query_entities):
            return True
            
        # Check for noun chunk matches
        caption_chunks = {chunk.text.lower() for chunk in doc_caption.noun_chunks}
        query_chunks = {chunk.text.lower() for chunk in doc_query.noun_chunks}
        
        if any(q_chunk in caption_chunks for q_chunk in query_chunks):
            return True
            
    except Exception as e:
        logger.debug(f"Context matching failed: {e}")
    
    return False


def get_720p_video_link_pexel(video_files):
    """
    Select the 720p or closest higher/lower resolution video link.
    Prioritizes height >= 720 (HD and above).
    """
    # Filter videos with height >= 720 (HD and above)
    hd_videos = [vf for vf in video_files if vf.get("height", 0) >= 720]

    if hd_videos:
        # Return the lowest resolution among HD videos
        return sorted(hd_videos, key=lambda x: x["height"])[0]["link"]

    # Fallback: return lowest available resolution
    return sorted(video_files, key=lambda x: x["height"])[0]["link"]


async def fetch_video_for_sentence(sentence: str, request_id: str) -> Optional[str]:
    """
    Fetch a single unique video for a sentence within a request.
    Returns the URL of the best matching video or None if no match found.
    """
    # Initialize tracking for this request if not exists
    if request_id not in request_video_tracking:
        request_video_tracking[request_id] = set()
    
    # Get single contextual keyword
    keyword = get_contextual_keywords(sentence, request_id)
    logger.info(f"[{request_id}] Fetching video for sentence: '{sentence}' with keyword: '{keyword}'")
    
    # Try Pexels first
    pexels_video = await fetch_from_pexels(sentence, keyword, request_id)
    if pexels_video and pexels_video[0] not in request_video_tracking[request_id]:
        logger.info(f"[{request_id}] Found unique video on Pexels for sentence: '{sentence}'")
        request_video_tracking[request_id].add(pexels_video[0])
        return pexels_video[0]
    
    # If Pexels fails or returns a used video, try Pixabay
    pixabay_video = await fetch_from_pixabay(sentence, keyword, request_id)
    if pixabay_video and pixabay_video[0] not in request_video_tracking[request_id]:
        logger.info(f"[{request_id}] Found unique video on Pixabay for sentence: '{sentence}'")
        request_video_tracking[request_id].add(pixabay_video[0])
        return pixabay_video[0]
    
    logger.warning(f"[{request_id}] No unique video found for sentence: '{sentence}'")
    return None


async def fetch_from_pexels(query: str, keyword: str, request_id: str) -> List[str]:
    """
    Enhanced video fetching from Pexels with single keyword.
    Returns a list with a single video URL if found.
    """
    clean_keyword = keyword.replace('"', '').replace(' ', '+')
    base_url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    
    # Initialize request tracking if not exists
    if request_id not in request_video_tracking:
        request_video_tracking[request_id] = set()

    # Try multiple pages if needed
    for page in range(1, 4):  # Try first three pages
        async with aiohttp.ClientSession() as session:
            try:
                params = {
                    "query": clean_keyword,
                    "orientation": "portrait",
                    "per_page": 200,  # Increased to maximum allowed
                    "sort": "popular",
                    "page": page
                }
                
                async with session.get(base_url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for v in data.get("videos", []):
                            caption = v.get("url", "").split("/")[-2].replace('-', ' ')
                            if caption_matches_query(caption, query) and v.get("duration", 0) >= 5:
                                video_link = get_720p_video_link_pexel(v["video_files"])
                                if video_link and video_link not in request_video_tracking[request_id]:
                                    # Download and cache the video with proper filename format
                                    cached_path = download_and_cache_video(video_link, keyword, request_id)
                                    if cached_path and os.path.exists(cached_path):
                                        request_video_tracking[request_id].add(video_link)
                                        logger.info(f"[{request_id}] Successfully cached video: {cached_path}")
                                        return [cached_path]
            
            except Exception as e:
                logger.error(f"[{request_id}] Error fetching from Pexels: {str(e)}")
                continue

    return []


def get_720p_video_link_pixabay(video_versions):
    """
    Selects the 720p or closest lower resolution video link.
    """
    # Prioritize 'medium' and 'small' versions for 720p
    for quality in ['medium', 'small']:
        video = video_versions.get(quality)
        if video and video.get("url"):
            return video["url"]
    # Fallback to 'tiny' if higher resolutions are unavailable
    return video_versions.get("tiny", {}).get("url")

async def fetch_from_pixabay(query: str, keyword: str, request_id: str) -> List[str]:
    """
    Enhanced video fetching from Pixabay with single keyword.
    Returns a list with a single video URL if found.
    """
    clean_keyword = keyword.replace('"', '').replace(' ', '+')
    base_url = "https://pixabay.com/api/videos/"
    
    # Initialize request tracking if not exists
    if request_id not in request_video_tracking:
        request_video_tracking[request_id] = set()

    # Try multiple pages if needed
    for page in range(1, 4):  # Try first three pages
        async with aiohttp.ClientSession() as session:
            try:
                params = {
                    "key": PIXABAY_API_KEY,
                    "q": clean_keyword,
                    "per_page": 200,  # Increased to maximum allowed
                    "orientation": "vertical",
                    "min_width": 720,
                    "min_height": 1280,
                    "page": page
                }
                
                async with session.get(base_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for v in data.get("hits", []):
                            caption = v.get("tags", "").replace(',', ' ')
                            if caption_matches_query(caption, query) and v.get("duration", 0) >= 5:
                                video_link = get_720p_video_link_pixabay(v["videos"])
                                if video_link and video_link not in request_video_tracking[request_id]:
                                    # Download and cache the video with proper filename format
                                    cached_path = download_and_cache_video(video_link, keyword, request_id)
                                    if cached_path and os.path.exists(cached_path):
                                        request_video_tracking[request_id].add(video_link)
                                        logger.info(f"[{request_id}] Successfully cached video: {cached_path}")
                                        return [cached_path]
            
            except Exception as e:
                logger.error(f"[{request_id}] Error fetching from Pixabay: {str(e)}")
                continue

    return []


def downscale_video_to_720p(input_path):
    """
    Downscales video to max 720p height while preserving aspect ratio
    Adds padding when needed to maintain original proportions
    """
    if not os.path.isfile(input_path):
        logger.error(f"Input file not found: {input_path}")
        return False

    try:
        dir_name = os.path.dirname(input_path)
        base_name = os.path.basename(input_path)
        temp_output = os.path.join(dir_name, f"temp_{base_name}")

        # Get original dimensions
        probe = ffmpeg.probe(input_path)
        video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
        if not video_stream:
            raise ValueError("No video stream found in file")
            
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        
        logger.info(f"Original video dimensions: {width}x{height}")
        
        # Calculate target dimensions with aspect ratio preservation
        if height > 720:
            new_height = 720
            new_width = int((width / height) * new_height)
        else:
            # Video already <=720p, just re-encode without resizing
            new_width = width
            new_height = height

        logger.info(f"Target dimensions: {new_width}x{new_height}")

        # FFmpeg command with padding and aspect ratio preservation
        try:
            (
                ffmpeg
                .input(input_path)
                .filter('scale', new_width, new_height)
                .output(
                    temp_output,
                    vcodec='libx264',
                    preset='faster',
                    crf=22,
                    pix_fmt='yuv420p',
                    movflags='+faststart',
                    **{'b:v': '2500k'}
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)  # Capture output for debugging
            )
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
            raise

        # Verify and replace
        if os.path.exists(temp_output) and os.path.getsize(temp_output) > 1024:
            os.replace(temp_output, input_path)
            logger.info(f"Downscaled {base_name} to 720p (AR preserved)")
            return True
            
        raise RuntimeError("Invalid output file")

    except Exception as e:
        logger.error(f"Downscale failed: {str(e)}", exc_info=True)
        if 'temp_output' in locals() and os.path.exists(temp_output):
            os.unlink(temp_output)
        return False

def download_and_cache_video(video_url, keyword, request_id):
    """
    Download and cache video with filename format: keyword_requestid_hash.mp4
    Example: believe_halfway_28d0d75e.mp4
    """
    os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
    
    # Clean keyword for filename (remove special characters, spaces)
    safe_keyword = re.sub(r'[^a-zA-Z0-9_]', '', keyword.lower().replace(' ', '_'))
    
    # Get first 8 characters of request_id for brevity
    short_request_id = request_id[:8] if len(request_id) > 8 else request_id
    
    # Create hash from video URL for uniqueness
    video_hash = hashlib.md5(video_url.encode()).hexdigest()[:8]
    
    # Create filename: keyword_requestid_hash.mp4
    video_filename = f"{safe_keyword}_{short_request_id}_{video_hash}.mp4"
    video_path = os.path.join(VIDEO_CACHE_DIR, video_filename)

    # Check if video already exists in cache
    if os.path.exists(video_path):
        logger.info(f"📂 Using existing cached video: {video_path}")
        return video_path

    try:
        logger.info(f"⬇️ Downloading: {video_url} -> {video_path}")
        response = requests.get(video_url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(video_path, 'wb') as file:
            shutil.copyfileobj(response.raw, file)
        logger.info(f"✅ Cached: {video_path}")

        # Try to downscale but don't fail if it doesn't work
        try:
            downscale_video_to_720p(video_path)
        except Exception as e:
            logger.warning(f"Downscaling failed but continuing with original video: {str(e)}")
            # Continue with the original video if downscaling fails

        return video_path

    except Exception as e:
        logger.error(f"❌ Failed to download {video_url}: {e}")
        # Clean up partial download
        if os.path.exists(video_path):
            try:
                os.unlink(video_path)
            except:
                pass
        return None


# Add this after the imports, before the logging setup
POPULAR_CATEGORIES = [
    "nature",      # Covers landscapes, wildlife, weather, etc.
    "city",        # Urban scenes, architecture, street life
    "people",      # Lifestyle, activities, culture
    "technology",  # Modern tech, innovation, digital
    "business",    # Work, office, commerce
    "travel",      # Destinations, exploration, adventure
    "food",        # Cooking, dining, cuisine
    "sports",      # Athletics, games, recreation
    "art",         # Creative, design, culture
    "lifestyle",   # Daily life, fashion, trends
    "animals",     # Wildlife, pets, nature
    "space",       # Astronomy, cosmos, science
    "water",       # Ocean, sea, rivers, lakes
    "sky",         # Clouds, weather, aerial
    "abstract",    # Artistic, patterns, textures
    "motivation",  # Inspirational, achievement, success
    "romantic",    # Love, relationships, couples
    "exercise",    # Fitness, workout, health
    "spiritual",   # Meditation, yoga, mindfulness
    "modeling",    # Fashion, beauty, photography
    "beauty"       # Aesthetics, style, glamour
]

def get_random_popular_category():
    """Get a random category from popular categories"""
    return random.choice(POPULAR_CATEGORIES)

async def fetch_media(sentence: str, request_id: str) -> List[str]:
    """
    Fetch media for a sentence with improved error handling and logging.
    Returns a list of video paths.
    """
    try:
        logger.info(f"[{request_id}] Fetching media for sentence: {sentence}")
        
        # Get contextual keyword
        keyword = get_contextual_keywords(sentence, request_id)
        logger.info(f"[{request_id}] Using keyword: {keyword}")
        
        # Try both APIs with the keyword
        for api in [fetch_from_pexels, fetch_from_pixabay]:
            try:
                videos = await api(sentence, keyword, request_id)
                if videos:
                    logger.info(f"[{request_id}] Found {len(videos)} videos using {api.__name__}")
                    return videos
            except Exception as e:
                logger.error(f"[{request_id}] Error with {api.__name__}: {str(e)}")
                continue
        
        # If no videos found, try with fallback category
        fallback_keyword = "social media content"
        logger.info(f"[{request_id}] No videos found, trying fallback keyword: {fallback_keyword}")
            
        # Try both APIs with the fallback category
        fallback_videos = await fetch_from_pexels(sentence, fallback_keyword, request_id) or await fetch_from_pixabay(sentence, fallback_keyword, request_id)
        if fallback_videos:
            logger.info(f"[{request_id}] Found {len(fallback_videos)} fallback videos")
            return fallback_videos
        
        logger.warning(f"[{request_id}] No videos found for sentence: {sentence}")
        return []
        
    except Exception as e:
        logger.error(f"[{request_id}] Error in fetch_media: {str(e)}", exc_info=True)
        return []

def cleanup_request_tracking(request_id: str):
    """Clean up video tracking for a request after videos are generated."""
    if request_id in request_video_tracking:
        logger.info(f"[{request_id}] Cleaning up video tracking")
        del request_video_tracking[request_id]


#Testing  new      