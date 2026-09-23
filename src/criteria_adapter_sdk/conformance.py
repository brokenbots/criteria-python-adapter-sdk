"""Conformance case: concurrent Execute calls on ONE session (CRI-308).

"parallel_safe" is a self-declared adapter capability.  This module turns
the guarantee the engine's parallel fan-out relies on into an executable
check that adapter authors can run against their own adapter:

    N concurrent Execute calls on ONE open session must deliver each
    result to its own call — every call's stream receives exactly its
    own ExecuteResult, no result is lost, no result lands on a sibling's
    stream, and a long-running call does not corrupt a sibling's
    completion.

The contract is per-call RESULT CORRECTNESS, not simultaneous execution:
an adapter that serializes concurrent Executes satisfies it as long as
each call gets its own result on its own stream.  This case asserts
outcomes per call and never wall-clock overlap.

Correlation convention
----------------------
Each Execute request carries a unique marker pair in ``req.input``:

- ``call_id`` — unique per call; the adapter-under-test must echo it
  back in the result's ``outputs_json`` as ``{"call_id": ...}``
- ``outcome`` — the outcome string expected for that call

The reference handler used by this repository's test suite echoes both;
an adapter-under-test for this case must do the same.

Usage (adapter authors)::

    from criteria_adapter_sdk.conformance import (
        assert_concurrent_execute_on_one_session,
    )

    assert_concurrent_execute_on_one_session(my_serve_config, n_calls=5)
"""

import json
import os
import tempfile
from concurrent import futures
from dataclasses import dataclass, field
from typing import Any, Dict, List, Union

import grpc

from criteria.v2 import adapter_pb2, adapter_pb2_grpc

from .serve import ServeConfig, _AdapterServicer


# Distinct outcome per call keeps outcome correlation observable.  For
# n_calls greater than the list length, outcomes cycle; call_id remains
# the primary correlation signal.
DEFAULT_OUTCOMES = ["success", "retryable", "failed", "skipped", "degraded"]


class ConformanceFailure(AssertionError):
    """Raised when the concurrent-execute result-correctness contract is violated."""


@dataclass
class CallStreamReport:
    """Observation of one Execute call's stream from a conformance run."""

    call_id: str
    expected_outcome: str
    events: List[Any] = field(default_factory=list)
    results: List[adapter_pb2.ExecuteResult] = field(default_factory=list)
    error: str = ""  # non-empty when the RPC failed before yielding a result


@dataclass
class ConformanceReport:
    """Outcome of a conformance run, for adapter-author diagnostics."""

    violations: List[str] = field(default_factory=list)
    streams: Dict[str, CallStreamReport] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations


def _as_serve_config(config: Union[ServeConfig, dict]) -> ServeConfig:
    if isinstance(config, dict):
        return ServeConfig(**config)
    return config


def _result_call_id(result: adapter_pb2.ExecuteResult) -> Any:
    """Extract the echoed ``call_id`` from a result, accepting both the
    typed ``outputs`` map and the JSON-encoded ``outputs_json`` form."""
    if result.outputs:
        return result.outputs.get("call_id")
    if result.outputs_json:
        try:
            outputs = json.loads(result.outputs_json.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if isinstance(outputs, dict):
            return outputs.get("call_id")
    return None


def assert_concurrent_execute_on_one_session(
    config: Union[ServeConfig, dict],
    n_calls: int = 5,
    session_id: str = "conformance-session",
) -> ConformanceReport:
    """Drive N concurrent Execute calls against ONE open session.

    Starts an in-process gRPC server hosting the adapter-under-test,
    opens a single session, and fires ``n_calls`` concurrent Execute
    RPCs on that session (one stream per call, as the host's parallel
    fan-out does).  Each request carries a unique ``call_id`` and the
    outcome expected for that call; the adapter's execute handler must
    echo ``call_id`` into its result's ``outputs_json``.

    Asserts, per call:

    - the call's stream received exactly one ``ExecuteResult``,
    - that result's outcome and echoed ``call_id`` belong to this call,
    - across all streams the received results match the issued calls
      exactly (nothing lost, duplicated, or rerouted).

    Raises ``ConformanceFailure`` listing every violation; returns a
    ``ConformanceReport`` on success.  Never asserts wall-clock overlap.
    """
    if n_calls < 3:
        raise ValueError("the concurrent-execute case requires n_calls >= 3")

    cfg = _as_serve_config(config)
    if cfg.execute is None:
        raise ValueError("config has no execute handler")

    markers = [f"call-{i}" for i in range(n_calls)]
    outcomes = [DEFAULT_OUTCOMES[i % len(DEFAULT_OUTCOMES)] for i in range(n_calls)]

    socket_dir = tempfile.mkdtemp(prefix="criteria-conformance-")
    socket_path = os.path.join(socket_dir, "adapter.sock")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max(10, n_calls + 2)))
    adapter_pb2_grpc.add_AdapterServiceServicer_to_server(
        _AdapterServicer(cfg), server
    )
    server.add_insecure_port(f"unix://{socket_path}")
    server.start()

    streams: Dict[str, CallStreamReport] = {}
    try:
        channel = grpc.insecure_channel(f"unix://{socket_path}")
        try:
            stub = adapter_pb2_grpc.AdapterServiceStub(channel)

            open_req = adapter_pb2.OpenSessionRequest(session_id=session_id)
            open_req.allowed_outcomes.extend(outcomes)
            stub.OpenSession(open_req)

            def drive_call(marker: str, outcome: str) -> CallStreamReport:
                req = adapter_pb2.ExecuteRequest(
                    session_id=session_id,
                    step_name=f"conformance-{marker}",
                )
                req.input["call_id"] = marker
                req.input["outcome"] = outcome
                req.allowed_outcomes.extend(outcomes)
                report = CallStreamReport(call_id=marker, expected_outcome=outcome)
                try:
                    events = list(stub.Execute(req))
                except grpc.RpcError as exc:
                    code = exc.code().name if hasattr(exc, "code") else "UNKNOWN"
                    details = exc.details() if hasattr(exc, "details") else str(exc)
                    report.error = f"RPC failed with {code}: {details}"
                    return report
                report.events = events
                report.results = [
                    ev.result
                    for ev in events
                    if ev.WhichOneof("event") == "result"
                ]
                return report

            with futures.ThreadPoolExecutor(max_workers=n_calls) as pool:
                pending = {
                    pool.submit(drive_call, marker, outcome): marker
                    for marker, outcome in zip(markers, outcomes)
                }
                for fut in futures.as_completed(pending):
                    rep = fut.result()
                    streams[rep.call_id] = rep
        finally:
            channel.close()
    finally:
        server.stop(0)
        try:
            os.unlink(socket_path)
        except FileNotFoundError:
            pass
        os.rmdir(socket_dir)

    violations: List[str] = []
    received_markers: List[Any] = []
    for marker, outcome in zip(markers, outcomes):
        rep = streams.get(marker)
        if rep is None:
            violations.append(f"{marker}: no stream report recorded")
            continue
        if rep.error:
            violations.append(
                f"{marker}: call failed before yielding a result ({rep.error})"
            )
            continue
        if not rep.results:
            violations.append(f"{marker}: stream received no ExecuteResult (result lost)")
            continue
        if len(rep.results) > 1:
            violations.append(
                f"{marker}: stream received {len(rep.results)} results, expected exactly one"
            )
            continue
        result = rep.results[0]
        if result.outcome != outcome:
            violations.append(
                f"{marker}: received outcome {result.outcome!r}, expected own {outcome!r}"
            )
        got_marker = _result_call_id(result)
        if got_marker != marker:
            violations.append(
                f"{marker}: result carries call_id {got_marker!r} "
                "(a sibling's result landed on this call's stream)"
            )
        received_markers.append(got_marker)

    if sorted(map(str, received_markers)) != sorted(markers):
        missing = sorted(set(markers) - set(received_markers))
        unexpected = sorted(set(received_markers) - set(markers))
        violations.append(
            f"result correlation broken: received markers {sorted(map(str, received_markers))} "
            f"do not match issued markers {sorted(markers)} "
            f"(missing={missing}, unexpected={unexpected})"
        )

    report = ConformanceReport(violations=violations, streams=streams)
    if violations:
        raise ConformanceFailure(
            "concurrent-Execute-on-one-session conformance failed:\n  - "
            + "\n  - ".join(violations)
        )
    return report