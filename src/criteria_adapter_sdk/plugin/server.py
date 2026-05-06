"""gRPC server implementation for Criteria adapter plugins.

This module implements the server-side of the go-plugin protocol,
handling the gRPC communication between the Criteria host and the plugin.
"""

from __future__ import annotations

import asyncio
import os
import sys
from concurrent import futures
from typing import Any

import grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health import HealthServicer

from criteria.v1 import adapter_plugin_pb2 as pb
from criteria.v1 import adapter_plugin_pb2_grpc as pb_grpc

from .types import AdapterService, EventSender


class _EventSenderImpl:
    """Internal implementation of EventSender for streaming events."""

    def __init__(self, queue: asyncio.Queue[pb.ExecuteEvent | None]) -> None:
        self._queue = queue
        self._has_sent_result = False

    async def log(self, stream: str, chunk: str | bytes) -> None:
        buffer = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
        event = pb.ExecuteEvent(
            log=pb.LogEvent(stream=stream.upper(), chunk=buffer)
        )
        await self._queue.put(event)

    async def adapter_event(self, event: Any) -> None:
        await self._queue.put(pb.ExecuteEvent(adapter=event))

    async def permission_request(self, permission: str, details: dict[str, str]) -> str:
        req_id = f"perm-{_now_ns()}-{hash(permission) & 0xFFFFFF:06x}"
        await self._queue.put(
            pb.ExecuteEvent(
                permission=pb.PermissionRequest(
                    id=req_id, permission=permission, details=details
                )
            )
        )
        return req_id

    async def result(self, outcome: str, outputs: dict[str, str]) -> None:
        if self._has_sent_result:
            raise RuntimeError("Result already sent")
        self._has_sent_result = True
        await self._queue.put(
            pb.ExecuteEvent(
                result=pb.ExecuteResult(outcome=outcome, outputs=outputs)
            )
        )

    def has_result(self) -> bool:
        return self._has_sent_result


class _AdapterServicer(pb_grpc.AdapterPluginServiceServicer):
    """gRPC servicer that delegates to an AdapterService implementation."""

    def __init__(self, impl: AdapterService) -> None:
        self._impl = impl

    async def Info(
        self, request: pb.InfoRequest, context: grpc.ServicerContext
    ) -> pb.InfoResponse:
        return await self._impl.info()

    async def OpenSession(
        self, request: pb.OpenSessionRequest, context: grpc.ServicerContext
    ) -> pb.OpenSessionResponse:
        return await self._impl.open_session(request)

    async def Execute(
        self, request: pb.ExecuteRequest, context: grpc.ServicerContext
    ):
        queue: asyncio.Queue[pb.ExecuteEvent | None] = asyncio.Queue()
        sender = _EventSenderImpl(queue)

        async def run_execute() -> None:
            try:
                await self._impl.execute(request, sender)
            except Exception as exc:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(exc))
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_execute())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if not sender.has_result():
            context.abort(
                grpc.StatusCode.INTERNAL,
                "Execute completed without sending result",
            )

    async def Permit(
        self, request: pb.PermitRequest, context: grpc.ServicerContext
    ) -> pb.PermitResponse:
        return await self._impl.permit(request)

    async def CloseSession(
        self, request: pb.CloseSessionRequest, context: grpc.ServicerContext
    ) -> pb.CloseSessionResponse:
        return await self._impl.close_session(request)


def _make_health_servicer() -> HealthServicer:
    servicer = HealthServicer()
    servicer.set("plugin", health_pb2.HealthCheckResponse.SERVING)
    return servicer


async def start_server(
    service: AdapterService,
    *,
    address: str | None = None,
    debug: bool = False,
) -> grpc.Server:
    """Start the gRPC server for an adapter service.

    This function creates and starts a gRPC server implementing the
    AdapterPluginService interface. It reads the connection configuration
    from environment variables set by the go-plugin host.

    Args:
        service: The adapter service implementation.
        address: Optional network address to listen on.
        debug: Enable debug logging.

    Returns:
        The running gRPC server.
    """
    tcp_port = _env_int("PLUGIN_TCP_PORT")
    unix_socket = _env_str("PLUGIN_UNIX_SOCKET")

    if address:
        bind_address = address
    elif unix_socket:
        bind_address = f"unix:{unix_socket}"
    elif tcp_port:
        bind_address = f"127.0.0.1:{tcp_port}"
    else:
        bind_address = "127.0.0.1:0"

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    pb_grpc.add_AdapterPluginServiceServicer_to_server(
        _AdapterServicer(service), server
    )
    health_pb2_grpc.add_HealthServicer_to_server(_make_health_servicer(), server)

    port = server.add_insecure_port(bind_address)
    if debug:
        print(f"gRPC server listening on {bind_address} (port {port})", file=sys.stderr)

    await server.start()

    # go-plugin handshake line
    # Format: CORE_PROTOCOL_VERSION|APP_PROTOCOL_VERSION|NETWORK_TYPE|NETWORK_ADDR|PROTOCOL
    if tcp_port or not unix_socket:
        print(f"1|1|tcp|127.0.0.1:{port}|grpc")
    else:
        print(f"1|1|unix|{unix_socket}|grpc")
    sys.stdout.flush()

    return server


def _env_str(name: str) -> str | None:
    return os.environ.get(name)


def _env_int(name: str) -> int | None:
    val = os.environ.get(name)
    return int(val) if val is not None else None


def _now_ns() -> int:
    import time

    return time.time_ns()
