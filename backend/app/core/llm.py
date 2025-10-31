import google.generativeai as genai
from typing import Optional
import logging

from .config import settings

logger = logging.getLogger(__name__)


def get_gemini_client():
    """Initialize and return Gemini client."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not set in environment")
    genai.configure(api_key=settings.gemini_api_key)
    
    # Use gemini-2.0-flash (latest generation)
    return genai.GenerativeModel("gemini-2.0-flash")


def generate_text(prompt: str, max_retries: int = 3) -> Optional[str]:
    """Generate text using Gemini with retries."""
    if not settings.gemini_api_key:
        logger.error("GEMINI_API_KEY not set")
        return None
    
    genai.configure(api_key=settings.gemini_api_key)
    
    # Try different model names
    model_names = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro",
    ]
    
    last_error = None
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response.text:
                logger.info(f"Successfully generated text using {model_name}")
                return response.text
        except Exception as e:
            last_error = e
            logger.warning(f"Failed to use model {model_name}: {e}")
            continue
    
    # If all models failed, try to list available models
    try:
        available = list(genai.list_models())
        model_list = [m.name for m in available if 'generateContent' in m.supported_generation_methods]
        logger.error(f"Available models with generateContent: {model_list}")
        if model_list:
            # Try the first available model
            try:
                model = genai.GenerativeModel(model_list[0])
                response = model.generate_content(prompt)
                if response.text:
                    logger.info(f"Successfully generated text using {model_list[0]}")
                    return response.text
            except Exception as e:
                logger.error(f"Failed to use available model {model_list[0]}: {e}")
    except Exception as e:
        logger.error(f"Could not list available models: {e}")
    
    logger.error(f"All Gemini models failed. Last error: {last_error}")
    return None

