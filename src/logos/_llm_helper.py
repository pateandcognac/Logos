# Logos/src/logos/_llm_helper.py
"""
Helper script that talks to the LLM SDK.

This script is intended to be run under Python 3.11 with the LLM SDK
installed. It reads a JSON payload from stdin and writes a JSON response
to stdout:

Input:
    {
      "prompt": "...",
      "model_name": "gemini-...-latest",
      "temperature": 0.7
    }

Output on success:
    { "text": "model response here" }

Output on error:
    { "error": "some error message" }
"""

import sys
import os
import json

from google import genai
from google.genai import types as genai_types


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        json.dump({"error": f"Failed to read stdin: {e}"}, sys.stdout)
        return

    prompt = payload.get("prompt", "")
    model_name = payload.get("model_name", "gemini-flash-latest")
    temperature = float(payload.get("temperature", 0.7))

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        json.dump({"error": "GEMINI_API_KEY not set"}, sys.stdout)
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            contents=[prompt],
            generation_config=genai_types.GenerationConfig(
                temperature=temperature
            ),
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE",
                },
            ],
        )
        json.dump({"text": response.text}, sys.stdout)
    except Exception as e:
        json.dump({"error": f"Gemini call failed: {e}"}, sys.stdout)


if __name__ == "__main__":
    main()
