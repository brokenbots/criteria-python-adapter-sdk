import json
import os
import socket
import ssl
import tempfile
import threading
import time
from concurrent import futures
from dataclasses import dataclass
from typing import Optional

import grpc

from criteria.v2 import adapter_pb2, adapter_pb2_grpc


@dataclass
class RemoteIdentity:
    name: str
    version: str
    digest: str


@dataclass
class ServeRemoteOptions:
    host: str
    identity: RemoteIdentity
    accept_token: Optional[str] = None
    tls: Optional[ssl.SSLContext] = None
    socket_path: Optional[str] = None
    # When True, redial the host with exponential backoff after the connection
    # drops, instead of returning. Matches the TypeScript and Go SDKs' opt-in
    # phone-home reconnect behavior. Default False: serve one connection, return.
    reconnect: bool = False
    # First backoff after a dropped connection when reconnect is True (seconds).
    initial_delay: float = 1.0
    # Cap on the exponential backoff when reconnect is True (seconds).
    max_delay: float = 30.0


class _AdapterServicer(adapter_pb2_grpc.AdapterServiceServicer):
    def __init__(self, handler: "Service"):
        self._handler = handler

    def Info(self, request, context):
        return self._handler.info(request, context)

    def OpenSession(self, request, context):
        return self._handler.open_session(request, context)

    def Execute(self, request_iterator, context):
        return self._handler.execute(request_iterator, context)

    def Log(self, request_iterator, context):
        return self._handler.log(request_iterator, context)

    def Permissions(self, request_iterator, context):
        return self._handler.permissions(request_iterator, context)

    def Pause(self, request, context):
        return self._handler.pause(request, context)

    def Resume(self, request, context):
        return self._handler.resume(request, context)

    def Snapshot(self, request, context):
        return self._handler.snapshot(request, context)

    def Restore(self, request, context):
        return self._handler.restore(request, context)

    def Inspect(self, request, context):
        return self._handler.inspect(request, context)

    def CloseSession(self, request, context):
        return self._handler.close_session(request, context)


class Service:
    def info(self, request, context):
        raise NotImplementedError

    def open_session(self, request, context):
        raise NotImplementedError

    def execute(self, request_iterator, context):
        raise NotImplementedError

    def log(self, request_iterator, context):
        raise NotImplementedError

    def permissions(self, request_iterator, context):
        raise NotImplementedError

    def pause(self, request, context):
        raise NotImplementedError

    def resume(self, request, context):
        raise NotImplementedError

    def snapshot(self, request, context):
        raise NotImplementedError

    def restore(self, request, context):
        raise NotImplementedError

    def inspect(self, request, context):
        raise NotImplementedError

    def close_session(self, request, context):
        raise NotImplementedError


def _dial_remote(host: str, tls: Optional[ssl.SSLContext] = None) -> socket.socket:
    if os.path.isabs(host) or host.startswith("/"):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(host)
        return sock

    # TCP
    if ":" in host:
        hostname, port_str = host.rsplit(":", 1)
        port = int(port_str)
    else:
        hostname = host
        port = 443

    if tls is not None:
        sock = socket.create_connection((hostname, port))
        return tls.wrap_socket(sock, server_hostname=hostname)
    return socket.create_connection((hostname, port))


def _send_handshake(conn: socket.socket, identity: RemoteIdentity, token: Optional[str] = None) -> None:
    msg = {
        "name": identity.name,
        "version": identity.version,
        "digest": identity.digest,
        "token": token,
        "sdk_protocol_version": 2,
    }
    line = json.dumps({k: v for k, v in msg.items() if v is not None}) + "\n"
    conn.sendall(line.encode("utf-8"))


def _bridge_sockets(a: socket.socket, b: socket.socket) -> None:
    def forward(src: socket.socket, dst: socket.socket):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except (OSError, BrokenPipeError):
            pass
        finally:
            try:
                src.shutdown(socket.SHUT_RD)
            except OSError:
                pass
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t1 = threading.Thread(target=forward, args=(a, b), daemon=True)
    t2 = threading.Thread(target=forward, args=(b, a), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def _connect_and_bridge(opts: ServeRemoteOptions, socket_path: str) -> None:
    """Dial the host, send the handshake, and bridge to the local gRPC socket.

    Owns only the per-connection sockets; the caller owns the gRPC server.
    """
    conn = _dial_remote(opts.host, opts.tls)
    try:
        _send_handshake(conn, opts.identity, opts.accept_token)
    except Exception as e:
        conn.close()
        raise RuntimeError(f"serveRemote: handshake failed: {e}") from e

    local = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        local.connect(socket_path)
    except Exception as e:
        conn.close()
        raise RuntimeError(f"serveRemote: connect to internal socket failed: {e}") from e

    try:
        _bridge_sockets(conn, local)
    finally:
        conn.close()
        local.close()


def serve_remote(service: Service, opts: ServeRemoteOptions) -> None:
    if not opts.host:
        raise ValueError("serveRemote: host is required")

    socket_path = opts.socket_path or os.path.join(
        tempfile.gettempdir(),
        f"criteria-py-adapter-{os.getpid()}.sock",
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(_AdapterServicer(service), server)
    server.add_insecure_port(f"unix://{socket_path}")
    server.start()

    try:
        if not opts.reconnect:
            _connect_and_bridge(opts, socket_path)
            return

        delay = opts.initial_delay
        while True:
            try:
                _connect_and_bridge(opts, socket_path)
                delay = opts.initial_delay  # clean disconnect: reset backoff
            except (OSError, RuntimeError):
                pass  # dial/handshake failure: retry after backoff
            time.sleep(delay)
            delay = min(delay * 2, opts.max_delay)
    finally:
        server.stop(0)
