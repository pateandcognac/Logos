# src/logos/_llm_helper.py
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
from google.genai import types

# TODO: 

def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        json.dump({"error": f"Failed to read stdin: {e}"}, sys.stdout)
        return

    prompt = payload.get("prompt", "")
    model_name = payload.get("model_name", "gemini-flash-latest")
    temperature = float(payload.get("temperature", 1.0))

    api_key = os.environ.get("FREE_GEMINI_API_KEY") or os.environ.get("PAID_GOOGLE_API_KEY")
    if not api_key:
        json.dump({"error": "LOGOS_API_KEY not set"}, sys.stdout)
        return

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=temperature,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=-1),
                safetySettings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                ],
            ),
        )
        text = getattr(response, "text", None) or ""
        json.dump({"text": text}, sys.stdout)
    except Exception as e:
        json.dump({"error": f"Gemini call failed: {e}"}, sys.stdout)


if __name__ == "__main__":
    main()
