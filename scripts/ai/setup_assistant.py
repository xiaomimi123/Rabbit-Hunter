"""One-time setup: creates the OpenAI Assistant + Vector Store and prints the IDs.

Run once, then add the printed IDs to your .env file.

Usage:
    python scripts/ai/setup_assistant.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_ROOT / ".env")

from scripts.ai.trading_assistant import TradingAssistant


async def main() -> None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("ERROR: OPENAI_API_KEY not found in .env")
        sys.exit(1)

    existing_id = os.getenv("OPENAI_ASSISTANT_ID")
    if existing_id:
        print(f"Assistant already exists: {existing_id}")
        print("Delete OPENAI_ASSISTANT_ID from .env to recreate.")
        return

    assistant = TradingAssistant()
    await assistant.initialize()
    print("\nSetup complete. Copy the IDs above into your .env file.")
    print("Then set: OPENAI_AI_ENABLED=true")


if __name__ == "__main__":
    asyncio.run(main())
