# src/logos/models.py

"""
This module contains wrappers for interacting with various AI models.
This includes my own core intelligence (for summarization, etc.) and
specialized models for vision, classification, and more.
"""

import os
import json
from google import genai
from google.genai import types as genai_types
from pathlib import Path

_llm_client = None
_llm_config = {}

def _initialize_llm():
    """Initializes the Gemini client and configuration for the llm() wrapper."""
    global _llm_client, _llm_config
    if _llm_client:
        return

    try:
        # This assumes the CWD is the workspace root
        config_path = Path.cwd() / ".system" / "framework_config.json"
        with open(config_path, 'r') as f:
            framework_config = json.load(f)

        aliases = framework_config.get('llm_tool_models', {}).get('aliases', {})
        _llm_config['aliases'] = aliases
        # Default to the 'fast' model if it exists, otherwise a sensible fallback.
        _llm_config['default_model'] = aliases.get('fast', 'gemini-flash-latest')

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")

        genai.configure(api_key=api_key)
        _llm_client = genai # The top-level module is the client entrypoint now

        print("Logos Models: LLM wrapper initialized.")

    except Exception as e:
        print(f"Error initializing LLM wrapper: {e}")
        _llm_client = None


def llm(prompt: str, model_alias: str = 'fast', temperature: float = 0.7) -> str:
    """
    A simple, general-purpose wrapper to access my own core LLM intelligence out-of-band.

    Args:
        prompt: The text prompt to send to the model.
        model_alias: Choose from a spectrum of intelligence and speed.
                    ('smartest', 'fast', 'fastest') Defaults to 'fast'.
        temperature: The creativity of the response (0.0 to 1.0).

    Returns:
        The text response from the model, or an empty string if an error occurs.

    Note to self:
        This is for simple, one-shot, instruct-type tasks like summarization or classification.
        This LLM call is stateless and does not inherit my identity as Logos or any other context.
        It has minimal error handling and retries.
    """
    if not _llm_client:
        _initialize_llm()
        if not _llm_client:
            print("LLM client is not available.")
            return ""

    model_name = _llm_config.get('aliases', {}).get(model_alias, _llm_config['default_model'])

    for attempt in range(2): # Simple retry logic
        try:
            model = _llm_client.GenerativeModel(model_name)
            response = model.generate_content(
                contents=[prompt],
                generation_config=genai_types.GenerationConfig(temperature=temperature),
                safety_settings = [ # Minimal safety settings for internal tools
                    {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
                    {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
                    {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                    {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
                ]
            )
            return response.text
        except Exception as e:
            print(f"LLM call to '{model_name}' failed on attempt {attempt + 1}: {e}")
            if attempt == 1:
                return "" # Return empty string after last failed attempt