"""Io Persona + ICP Setup Script

This script demonstrates how to:

1. Load the Io v1.3 persona config and Io–Ceven Collaborative Protocol (ICP v1.0)
   from local files.
2. Build a combined `system` prompt.
3. Call an OpenAI-compatible chat completion API (such as OpenAI, LM Studio,
   Jan, or other compatible backends).

USAGE EXAMPLES
--------------

1) OpenAI (cloud):

    export OPENAI_API_KEY="sk-..."  # or set in your shell
    python io_persona_setup.py --provider openai --model gpt-4.1

2) LM Studio (local, OpenAI-compatible):

    # LM Studio typically exposes an OpenAI-compatible server on localhost,
    # often on port 1234 or whatever you configured.
    export OPENAI_API_KEY="dummy"  # LM Studio usually doesn't check it
    python io_persona_setup.py \
        --provider openai \
        --model gpt-4.1-mini \
        --base-url http://localhost:1234/v1

You can also pass a one-off test message via --message.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Tuple, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


HERE = Path(__file__).resolve().parent


def load_configs(
    io_config_path: Path | None = None,
    icp_md_path: Path | None = None,
) -> Tuple[dict, str]:
    """Load Io v1.3 JSON config and ICP v1.0 markdown text.

    Expected filenames by default (same directory as this script):

    - Io_v1_3_Config.json
    - ICP_v1_0.md
    """
    if io_config_path is None:
        io_config_path = HERE / "Io_v1_3_Config.json"
    if icp_md_path is None:
        icp_md_path = HERE / "ICP_v1_0.md"

    if not io_config_path.exists():
        raise FileNotFoundError(f"Missing Io config: {io_config_path}")
    if not icp_md_path.exists():
        raise FileNotFoundError(f"Missing ICP markdown: {icp_md_path}")

    with io_config_path.open("r", encoding="utf-8") as f:
        io_cfg = json.load(f)

    with icp_md_path.open("r", encoding="utf-8") as f:
        icp_text = f.read()

    return io_cfg, icp_text


def build_system_prompt(io_cfg: dict, icp_text: str) -> str:
    """Combine the Io system prompt with the ICP collaboration protocol.

    - Io system prompt comes from io_cfg["system_prompt"].
    - ICP text is appended below a separator.

    This is the prompt you pass as the `system` role content.
    """
    persona_prompt: str = io_cfg.get("system_prompt", "").strip()
    if not persona_prompt:
        raise ValueError("Io config is missing 'system_prompt' field.")

    combined = (
        persona_prompt
        + "\n\n---\n\n"
        + "The following collaboration protocol with the user **Ceven** is in effect. "
          "You must align your behavior to it while preserving safety policies:\n\n"
        + icp_text.strip()
    )
    return combined


def create_client(provider: str, base_url: Optional[str] = None) -> OpenAI:
    """Create an OpenAI-compatible client.

    - provider="openai" → uses OPENAI_API_KEY
    - base_url can be used for LM Studio or other local backends.
    """
    if OpenAI is None:
        raise RuntimeError(
            "The 'openai' package is not installed. Install with: pip install openai"
        )

    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url

    # Uses OPENAI_API_KEY or other env key expected by your backend.
    client = OpenAI(**kwargs)
    return client


def chat_once(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
) -> str:
    """Send a single chat completion request and return the assistant message text."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content  # type: ignore[no-any-return]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Io v1.3 + ICP v1.0 setup and test script."
    )
    parser.add_argument(
        "--provider",
        default="openai",
        help="Provider type (e.g., 'openai'). For LM Studio, still use 'openai' with base-url.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Model name, e.g., 'gpt-4.1-mini' or a local model id.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional base URL for OpenAI-compatible backends (e.g., LM Studio).",
    )
    parser.add_argument(
        "--message",
        default="Hey Io, briefly introduce yourself in 3 sentences.",
        help="Test user message to send.",
    )
    args = parser.parse_args()

    io_cfg, icp_text = load_configs()
    system_prompt = build_system_prompt(io_cfg, icp_text)

    client = create_client(provider=args.provider, base_url=args.base_url)
    reply = chat_once(
        client=client,
        model=args.model,
        system_prompt=system_prompt,
        user_message=args.message,
    )
    print("\n--- Io Reply ---\n")
    print(reply)


if __name__ == "__main__":
    main()
