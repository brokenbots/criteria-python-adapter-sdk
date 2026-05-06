"""Criteria Adapter SDK for Python.

This SDK enables you to write out-of-process adapter plugins for the Criteria
workflow engine using Python, with Nuitka compilation for native binary
distribution via OCI.

## Quick Start

```python
import asyncio
from criteria_adapter_sdk import serve

async def main():
    await serve({
        "name": "my-adapter",
        "version": "1.0.0",
        "execute": lambda req, sender: sender.result("success", {}),
    })

if __name__ == "__main__":
    asyncio.run(main())
```
"""

from __future__ import annotations

from criteria.v1 import adapter_plugin_pb2 as _pb

from .plugin import (
    AdapterService,
    EventSender,
    MAGIC_COOKIE_KEY,
    MAGIC_COOKIE_VALUE,
    PROTOCOL_VERSION,
    SimpleAdapterConfig,
    is_plugin_invocation,
    serve,
    serve_adapter,
    start_server,
    validate_and_exit_on_failure,
    validate_handshake,
)

SDK_VERSION = "0.1.0"

__all__ = [
    "AdapterService",
    "EventSender",
    "MAGIC_COOKIE_KEY",
    "MAGIC_COOKIE_VALUE",
    "PROTOCOL_VERSION",
    "SDK_VERSION",
    "SimpleAdapterConfig",
    "is_plugin_invocation",
    "serve",
    "serve_adapter",
    "start_server",
    "validate_and_exit_on_failure",
    "validate_handshake",
]
