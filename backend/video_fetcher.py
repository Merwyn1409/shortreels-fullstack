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
from config import PEXELS_API_KEY, PIXABAY_API_KEY, VIDEO_CACHE_DIR
from constants import FALLBACK_CATEGORIES
import asyncio
import gc
import shutil
import spacy
from nltk.corpus import wordnet
from keybert import KeyBERT
nlp = spacy.load("en_core_web_sm")
import nltk

def download_nltk_data():
    """Download necessary NLTK data files only if not already installed."""
    try:
        nltk.data.find("corpora/wordnet.zip")
        nltk.data.find("corpora/omw-1.4.zip")
        nltk.data.find("tokenizers/punkt.zip")
    except LookupError:
        nltk.download("wordnet")
        nltk.download("omw-1.4")
        nltk.download("punkt")

# Call this function once at startup (before keyword extraction)
download_nltk_data()
kw_model = KeyBERT()
# Garbage Collection
gc.collect()

# Logging
logging.basicConfig(filename="api_usage.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# API usage tracking
api_usage = {"pexels": 0, "pixabay": 0}
api_limit = {"pexels": 200, "pixabay": 200}
reset_time = time.time() + 3600
CACHE_EXPIRY = 3600  # 1-hour cache expiry


def log_api_usage(provider):
    """Log API usage."""
    global api_usage, reset_time
    if time.time() > reset_time:
        api_usage = {"pexels": 0, "pixabay": 0}
        reset_time = time.time() + 3600
    api_usage[provider] += 1
    remaining = api_limit[provider] - api_usage[provider]
    logging.info(f"{provider.upper()} API used: {api_usage[provider]}/{api_limit[provider]}. Remaining: {remaining}")


def cleanup_expired_cache():
    """Remove expired videos from cache."""
    now = time.time()
    for filename in os.listdir(VIDEO_CACHE_DIR):
        file_path = os.path.join(VIDEO_CACHE_DIR, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > CACHE_EXPIRY:
            os.remove(file_path)
            logging.info(f"Deleted expired cache: {file_path}")


def split_text_into_sentences(text):
    """Split text into meaningful sentences using NLTK."""
    return nltk.tokenize.sent_tokenize(text)

def get_fallback_category(sentence):
    """
    Dynamically determines a fallback category based on the sentence's meaning.
    """
    doc = nlp(sentence)
    themes = []
    for token in doc:
        if token.pos_ in ("NOUN", "ADJ"):
            themes.append(token.text.lower())
    
    if not themes:
        return "general"
    return themes[0]  # Use the most relevant keyword as fallback



def get_contextual_keywords(sentence):
    """Extracts meaningful keywords using KeyBERT."""
    keywords = kw_model.extract_keywords(sentence, keyphrase_ngram_range=(1, 2), stop_words='english', top_n=1)
    print(f"Extracted keywords: {keywords}")
    return [kw[0] for kw in keywords]



def get_cached_videos(theme):
    """Retrieve cached videos for a theme, ignoring hash differences."""
    cache_path = VIDEO_CACHE_DIR
    if not os.path.exists(cache_path):
        return []

    safe_theme = theme.lower().replace(" ", "_")
    cached_videos = [
        os.path.join(cache_path, filename)
        for filename in os.listdir(cache_path)
        if filename.startswith(safe_theme + "_")  # ✅ Match only the keyword, ignore hash
    ]
    
    return cached_videos  # ✅ Always return a list





async def fetch_from_pexels(query):
    """Fetch high-quality videos from Pexels API."""
    query = f'"{query}"'  # Ensure exact match
    url = f"https://api.pexels.com/videos/search?query={query.replace('_', ' ')}&per_page=10&page={random.randint(1, 5)}"
    headers = {"Authorization": PEXELS_API_KEY}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    videos = [max(video["video_files"], key=lambda v: v.get("width", 0)).get("link", "") for video in data.get("videos", []) if video.get("duration", 0) >= 5]
                    if videos:
                        log_api_usage("pexels")
                        return videos
        except Exception as e:
            logging.error(f"Error fetching from Pexels: {e}")
    return []

async def fetch_from_pixabay(query):
    """Fetch high-quality videos from Pixabay API."""
    query = f'"{query}"'  # Ensure exact match
    url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query.replace('_', ' ')}&per_page=10&page={random.randint(1, 5)}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    videos = [video["videos"].get("fullHD", video["videos"].get("HD", video["videos"].get("medium", {}))).get("url", "") for video in data.get("hits", []) if video.get("duration", 0) >= 5]
                    if videos:
                        log_api_usage("pixabay")
                        return videos
        except Exception as e:
            logging.error(f"Error fetching from Pixabay: {e}")
    return []

def download_and_cache_video(video_url, theme):
    """Download video and save it in the cache only if a cached version does not exist."""
    os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
    safe_theme = theme.lower().replace(" ", "_")

    # ✅ Check if any cached file already exists for this theme
    cached_videos = get_cached_videos(safe_theme)
    if cached_videos:
        logging.info(f"📂 Using cached video: {cached_videos[0]} for theme: {safe_theme}")
        return cached_videos[0]  # ✅ Return first cached video instead of downloading a new one

    # ✅ If no cache exists, generate a new unique filename
    video_hash = hashlib.md5(video_url.encode()).hexdigest()[:8]  # Shortened hash
    video_filename = f"{safe_theme}_{video_hash}.mp4"
    video_path = os.path.join(VIDEO_CACHE_DIR, video_filename)

    try:
        logging.info(f"⬇️ Downloading: {video_url} -> {video_path}")
        response = requests.get(video_url, stream=True)
        with open(video_path, 'wb') as file:
            shutil.copyfileobj(response.raw, file)
        logging.info(f"✅ Cached: {video_path}")
    except Exception as e:
        logging.error(f"❌ Failed to download {video_url}: {e}")

    return video_path




async def fetch_media(text):
    """Fetch videos based on contextual keywords extracted using KeyBERT."""
    sentences = text.split(". ")
    media_per_sentence = []

    for sentence in sentences:
        keywords = get_contextual_keywords(sentence)
        selected_videos = []

        # ✅ Check cache first
        for keyword in keywords:
            cached_videos = get_cached_videos(keyword)
            if cached_videos:
                selected_videos.extend(cached_videos[:1])
                break  # ✅ Stop looking for more if cache is found

        # ✅ Fetch new videos only if no cache found
        if not selected_videos:
            for api in [fetch_from_pexels, fetch_from_pixabay]:
                for keyword in keywords:
                    videos = await api(keyword)
                    for video_url in videos[:1]:
                        cached_path = download_and_cache_video(video_url, keyword)
                        selected_videos.append(cached_path)
                    if selected_videos:
                        break  # ✅ Stop once videos are found
                if selected_videos:
                    break

        # ✅ Fallback to general category if nothing is found
        if not selected_videos:
            fallback_keyword = "general"
            fallback_videos = await fetch_from_pexels(fallback_keyword) or await fetch_from_pixabay(fallback_keyword)
            for video_url in fallback_videos[:1]:
                cached_path = download_and_cache_video(video_url, fallback_keyword)
                selected_videos.append(cached_path)

        media_per_sentence.append({"sentence": sentence, "videos": selected_videos[:1]})

    return media_per_sentence

