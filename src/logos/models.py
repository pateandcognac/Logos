# Logos/src/logos/models.py

"""
This module contains wrappers for interacting with various AI models.
For Gemini, this module acts as a thin bridge: it shells out to a
Python 3.11 helper script that actually talks to the Gemini SDK.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict
import os

# Get Path to Python 3.11 interpreter (with Gemini SDK installed) from env var VENV_PY311
PY311 = os.getenv("LOGOS_VENV_PY311", "/home/robot/robot_ws/.venv/bin/python3")


# The helper script will live next to this file as _llm_helper.py
WORKER_PATH = Path(__file__).with_name("_llm_helper.py")

_llm_config: Dict[str, Any] = {}


def _initialize_llm() -> None:
    """
    Loads model alias config from .system/framework_config.json.

    We deliberately do NOT import the Gemini SDK here. The actual LLM
    interaction happens in the 3.11 worker script.
    """
    global _llm_config
    if _llm_config:
        return

    config_path = Path.cwd() / ".system" / "framework_config.json"

    try:
        with config_path.open("r") as f:
            framework_config = json.load(f)

        aliases = framework_config.get("llm_tool_models", {}).get("aliases", {})
        _llm_config["aliases"] = aliases
        # Default to the 'fast' model if it exists, otherwise a sensible fallback.
        _llm_config["default_model"] = aliases.get("fast", "gemini-flash-latest")
    except Exception as e:
        print(f"Error initializing LLM config from {config_path}: {e}")
        _llm_config = {}


def llm(prompt: str, model_alias: str = "fast", temperature: float = 0.7) -> str:
    """
    A simple, general-purpose wrapper to access my core LLM intelligence.

    This function runs a Python 3.11 worker script that calls the SDK,
    passing a small JSON payload over stdin and reading JSON from stdout.

    Args:
        prompt: The text prompt to send to the model.
        model_alias: Alias defined in framework_config.json (e.g. 'fast').
        temperature: Sampling temperature (0.0–1.0).

    Returns:
        The text response from the model, or an empty string on error.
    """
    if not _llm_config:
        _initialize_llm()

    if not _llm_config:
        print("LLM config not available.")
        return ""

    model_name = _llm_config.get("aliases", {}).get(
        model_alias,
        _llm_config.get("default_model", "gemini-flash-latest"),
    )

    if not WORKER_PATH.exists():
        print(f"Gemini worker script not found at {WORKER_PATH}")
        return ""

    payload = {
        "prompt": prompt,
        "model_name": model_name,
        "temperature": float(temperature),
    }

    try:
        proc = subprocess.run(
            [PY311, str(WORKER_PATH)],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
    except Exception as e:
        print(f"Error invoking Gemini worker: {e}")
        return ""

    if proc.returncode != 0:
        print(
            f"Gemini worker failed with code {proc.returncode}. "
            f"Stderr:\n{proc.stderr}"
        )
        return ""

    try:
        data = json.loads(proc.stdout)
    except Exception as e:
        print(f"Failed to parse Gemini worker output: {e}\nRaw output:\n{proc.stdout!r}")
        return ""

    text = data.get("text", "")
    if not isinstance(text, str):
        print(f"Gemini worker returned non-string text: {text!r}")
        return ""

    return text
