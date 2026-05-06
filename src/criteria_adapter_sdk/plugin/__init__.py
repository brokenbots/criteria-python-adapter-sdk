"""Public API for the Criteria adapter plugin SDK.

This module provides the main entry points for building adapter plugins:
- ``serve()`` - Start from a simplified configuration object
- ``serve_adapter()`` - Start a full AdapterService implementation
- ``validate_handshake()`` - Manual handshake validation
"""

from __future__ import annotations

import asyncio
from typing import Any

from criteria.v1 import adapter_plugin_pb2 as pb

from .handshake import (
    MAGIC_COOKIE_KEY,
    MAGIC_COOKIE_VALUE,
    PROTOCOL_VERSION,
    is_plugin_invocation,
    validate_and_exit_on_failure,
    validate_handshake,
)
from .server import start_server
from .types import (
    AdapterService,
    EventSender,
    SimpleAdapterConfig,
)

__all__ = [
    "AdapterService",
    "EventSender",
    "MAGIC_COOKIE_KEY",
    "MAGIC_COOKIE_VALUE",
    "PROTOCOL_VERSION",
    "SimpleAdapterConfig",
    "is_plugin_invocation",
    "serve",
    "serve_adapter",
    "start_server",
    "validate_and_exit_on_failure",
    "validate_handshake",
]


def _to_adapter_service(config: SimpleAdapterConfig) -> AdapterService:
    """Convert a SimpleAdapterConfig to a full AdapterService implementation."""

    class _Service:
        async def info(self) -> pb.InfoResponse:
            return pb.InfoResponse(
                name=config.name,
                version=config.version,
                capabilities=config.capabilities,
                config_schema=config.config_schema,
                input_schema=config.input_schema,
            )

        async def open_session(self, req: pb.OpenSessionRequest) -> pb.OpenSessionResponse:
            if config.on_open_session:
                result = config.on_open_session(req)
                if asyncio.iscoroutine(result):
                    await result
            return pb.OpenSessionResponse()

        async def execute(self, req: pb.ExecuteRequest, sender: EventSender) -> None:
            if config.execute is None:
                raise RuntimeError("SimpleAdapterConfig.execute is required")
            result = config.execute(req, sender)
            if asyncio.iscoroutine(result):
                await result

        async def permit(self, req: pb.PermitRequest) -> pb.PermitResponse:
            if config.on_permit:
                result = config.on_permit(req)
                if asyncio.iscoroutine(result):
                    await result
            return pb.PermitResponse()

        async def close_session(self, req: pb.CloseSessionRequest) -> pb.CloseSessionResponse:
            if config.on_close_session:
                result = config.on_close_session(req)
                if asyncio.iscoroutine(result):
                    await result
            return pb.CloseSessionResponse()

    return _Service()


async def serve(config: SimpleAdapterConfig) -> None:
    """Serve a simplified adapter configuration.

    This is the easiest way to create an adapter plugin. It validates the
    handshake, converts the config to a full service, and starts the gRPC server.

    Args:
        config: The adapter configuration.
    """
    validate_and_exit_on_failure()
    service = _to_adapter_service(config)
    server = await start_server(service)
    await server.wait_for_termination()


async def serve_adapter(service: AdapterService) -> None:
    """Serve a full AdapterService implementation.

    Use this when you need more control over the service lifecycle or want
    to implement custom session management.

    Args:
        service: The full adapter service implementation.
    """
    validate_and_exit_on_failure()
    server = await start_server(service)
    await server.wait_for_termination()
