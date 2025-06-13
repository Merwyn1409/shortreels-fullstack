import re
import logging
from typing import List
from nltk import sent_tokenize

# Set up logging
logger = logging.getLogger("text_utils")

def split_into_sentences(text: str) -> List[str]:
    """
    Clean and split text into sentences using NLTK's sent_tokenize.
    Returns a list of cleaned sentences.
    """
    try:
        # Clean the text
        text = text.strip()
        text = ' '.join(text.split())  # Remove extra spaces
        
        # Ensure there's a space after each period that's not part of an abbreviation
        text = re.sub(r'\.(?=[A-Z])', '. ', text)
        
        # Use NLTK's sent_tokenize for accurate sentence splitting
        sentences = sent_tokenize(text)
        
        # Clean up each sentence
        sentences = [s.strip() for s in sentences if s.strip()]
        
        logger.info(f"Split text into {len(sentences)} sentences: {sentences}")
        return sentences
        
    except Exception as e:
        logger.error(f"Error in split_into_sentences: {str(e)}", exc_info=True)
        # Fallback to simple split if NLTK fails
        return [s.strip() for s in text.split('.') if s.strip()] 