"""Greeter example adapter.

The simplest possible adapter — echoes a greeting back.
"""

import asyncio

from criteria_adapter_sdk import serve


async def main():
    await serve({
        "name": "greeter",
        "version": "1.0.0",
        "execute": lambda req, sender: _run(req, sender),
    })


async def _run(req, sender):
    name = req.config.get("name", "world")
    await sender.log("stdout", f"Hello, {name}!\n")
    await sender.result("success", {"greeting": f"Hello, {name}!"})


if __name__ == "__main__":
    asyncio.run(main())
