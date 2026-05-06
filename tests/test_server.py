"""Tests for the gRPC server implementation."""

import asyncio
import io
import os
import sys
from unittest.mock import patch

import grpc
import pytest

from criteria.v1 import adapter_plugin_pb2 as pb
from criteria.v1 import adapter_plugin_pb2_grpc as pb_grpc
from criteria_adapter_sdk.plugin.server import start_server
from criteria_adapter_sdk.plugin.types import AdapterService, EventSender


class _MockService(AdapterService):
    def __init__(self):
        self.info_response = pb.InfoResponse(name="test", version="1.0.0")
        self.execute_called = False

    async def info(self) -> pb.InfoResponse:
        return self.info_response

    async def open_session(self, req: pb.OpenSessionRequest) -> pb.OpenSessionResponse:
        return pb.OpenSessionResponse()

    async def execute(self, req: pb.ExecuteRequest, sender: EventSender) -> None:
        self.execute_called = True
        await sender.log("stdout", "hello")
        await sender.result("success", {})

    async def permit(self, req: pb.PermitRequest) -> pb.PermitResponse:
        return pb.PermitResponse()

    async def close_session(self, req: pb.CloseSessionRequest) -> pb.CloseSessionResponse:
        return pb.CloseSessionResponse()


@pytest.fixture
def mock_service():
    return _MockService()


@pytest.mark.asyncio
async def test_start_server_prints_handshake(mock_service):
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        server = await start_server(mock_service, address="127.0.0.1:0")
        try:
            handshake = stdout.getvalue().strip()
            assert handshake.startswith("1|1|tcp|127.0.0.1:")
            assert handshake.endswith("|grpc")
        finally:
            await server.stop(grace=None)


@pytest.mark.asyncio
async def test_info_rpc(mock_service):
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        server = await start_server(mock_service, address="127.0.0.1:0")
    try:
        handshake = stdout.getvalue().strip()
        port = int(handshake.split(":")[-1].replace("|grpc", ""))
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        stub = pb_grpc.AdapterPluginServiceStub(channel)
        response = await stub.Info(pb.InfoRequest())
        assert response.name == "test"
        assert response.version == "1.0.0"
    finally:
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_execute_rpc(mock_service):
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        server = await start_server(mock_service, address="127.0.0.1:0")
    try:
        handshake = stdout.getvalue().strip()
        port = int(handshake.split(":")[-1].replace("|grpc", ""))
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        stub = pb_grpc.AdapterPluginServiceStub(channel)
        events = []
        async for event in stub.Execute(pb.ExecuteRequest()):
            events.append(event)
        assert len(events) == 2
        assert events[0].log.stream == "STDOUT"
        assert events[0].log.chunk == b"hello"
        assert events[1].result.outcome == "success"
    finally:
        await server.stop(grace=None)
