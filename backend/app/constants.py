# constants.py

# ✅ Generalized fallback categories for video fetching
FALLBACK_CATEGORIES = {
    "love": ["couple", "romance", "heart", "embrace", "romantic"],
    "happiness": ["smile", "celebration", "joy", "laughter", "dance"],
    "sadness": ["rain", "tears", "lonely", "melancholy", "sunset"],
    "anger": ["storm", "fire", "lightning", "tension", "breaking"],
    "fear": ["dark", "shadow", "running", "fog", "forest"],
    "surprise": ["confetti", "gift", "shocked", "unexpected", "reveal"],
    "calm": ["ocean", "meditation", "peaceful", "breathing", "nature"],
    "excitement": ["fireworks", "adventure", "jumping", "cheering", "party"],
    
    # Relationship concepts
    "friendship": ["friends", "together", "sharing", "connection", "group"],
    "family": ["home", "children", "parents", "together", "gathering"],
    "romance": ["couple", "date", "kiss", "sunset", "holding hands"],
    "connection": ["hands", "touch", "eye contact", "together", "bond"],
    
    # Abstract concepts
    "time": ["clock", "hourglass", "sunset", "seasons", "waiting"],
    "freedom": ["flying", "birds", "open road", "sky", "running"],
    "success": ["achievement", "celebration", "victory", "trophy", "mountain top"],
    "growth": ["plant", "seedling", "child", "learning", "progress"],
    "change": ["seasons", "transformation", "butterfly", "journey", "road"],
    
    # Action concepts
    "look": ["eyes", "gaze", "watching", "sight", "viewing"],
    "hold": ["hands", "embrace", "grasp", "carry", "touch"],
    "walk": ["path", "journey", "steps", "hiking", "strolling"],
    "run": ["sprint", "race", "exercise", "escape", "chase"],
    "dance": ["movement", "music", "celebration", "rhythm", "couple"],
    "think": ["brain", "thoughtful", "contemplation", "meditation", "study"],
    
    # Nature concepts
    "water": ["ocean", "river", "rain", "waterfall", "swimming"],
    "earth": ["mountain", "forest", "field", "nature", "hiking"],
    "fire": ["flame", "campfire", "fireplace", "spark", "burning"],
    "air": ["wind", "flying", "clouds", "sky", "breathing"],
    
    # Time concepts
    "morning": ["sunrise", "coffee", "breakfast", "dawn", "early"],
    "day": ["sunshine", "blue sky", "outdoors", "bright", "activity"],
    "evening": ["sunset", "dinner", "dusk", "relaxation", "warm light"],
    "night": ["stars", "moon", "dark", "city lights", "sleeping"],
    
    # Life concepts
    "beginning": ["birth", "start", "sunrise", "seedling", "first step"],
    "journey": ["road", "path", "walking", "adventure", "travel"],
    "challenge": ["mountain", "obstacle", "effort", "climbing", "perseverance"],
    "achievement": ["summit", "celebration", "victory", "finish line", "award"],
    
    # Default fallback concepts
    "default": ["nature", "people", "city", "abstract", "technology"]
}


CATEGORY_KEYWORDS = { 
    "Romance": ["love", "heart", "passion", "relationship", "romantic"],
    "Adventure": ["travel", "explore", "journey", "mountain", "roadtrip"],
    "Motivation": ["success", "goal", "dream", "power", "strength"],
    "Sadness": ["tears", "alone", "pain", "loss", "broken"],
    "Happiness": ["joy", "laughter", "smile", "happiness", "celebrate"],
    "Nature": ["forest", "sunset", "ocean", "wildlife", "earth"],
    "Technology": ["innovation", "future", "AI", "robot", "digital"],
    "Sports": ["fitness", "running", "training", "soccer", "basketball"],
    "Fashion": ["style", "trend", "outfit", "designer", "clothing"],
    "Food": ["recipe", "delicious", "cooking", "tasty", "gourmet"],
    "Fitness": ["workout", "gym", "health", "training", "exercise"],
    "Business": ["startup", "entrepreneur", "marketing", "investment", "finance"],
    "Education": ["learning", "study", "knowledge", "school", "teacher"],
    "Music": ["song", "melody", "instrument", "concert", "performance"]
}

