"""Core types for Criteria adapter plugins.

This module defines the protocol interfaces for adapter authors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from criteria.v1 import adapter_plugin_pb2 as pb


class EventSender(Protocol):
    """Event sender interface for streaming events back to the host."""

    async def log(self, stream: str, chunk: str | bytes) -> None: ...

    async def adapter_event(self, event: Any) -> None: ...

    async def permission_request(self, permission: str, details: dict[str, str]) -> str: ...

    async def result(self, outcome: str, outputs: dict[str, str]) -> None: ...


class AdapterService(Protocol):
    """The main service interface that adapter plugins must implement."""

    async def info(self) -> pb.InfoResponse: ...

    async def open_session(self, req: pb.OpenSessionRequest) -> pb.OpenSessionResponse: ...

    async def execute(self, req: pb.ExecuteRequest, sender: EventSender) -> None: ...

    async def permit(self, req: pb.PermitRequest) -> pb.PermitResponse: ...

    async def close_session(self, req: pb.CloseSessionRequest) -> pb.CloseSessionResponse: ...


# Type alias for a callback that may be sync or async
_Callback = Callable[..., Any] | None


@dataclass
class SimpleAdapterConfig:
    """Simplified adapter configuration for the serve function."""

    name: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    config_schema: pb.AdapterSchemaProto | None = None
    input_schema: pb.AdapterSchemaProto | None = None

    on_open_session: _Callback = None
    execute: _Callback = None
    on_permit: _Callback = None
    on_close_session: _Callback = None
