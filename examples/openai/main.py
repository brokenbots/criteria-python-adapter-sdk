"""OpenAI example adapter.

A full agent adapter with multi-turn conversations.
"""

import asyncio
import os

from criteria_adapter_sdk import serve


async def main():
    await serve({
        "name": "openai",
        "version": "1.0.0",
        "execute": _run,
    })


async def _run(req, sender):
    model = req.config.get("model", "gpt-4o")
    max_turns = int(req.config.get("max_turns", "10"))
    prompt = req.config.get("prompt", "")

    await sender.log("stdout", f"Starting OpenAI conversation with {model}\n")

    # Placeholder for actual OpenAI integration
    await sender.log("stdout", f"User: {prompt}\n")
    await sender.log("stdout", "Assistant: This is a placeholder response.\n")

    await sender.result("success", {"response": "Placeholder response"})


if __name__ == "__main__":
    asyncio.run(main())
