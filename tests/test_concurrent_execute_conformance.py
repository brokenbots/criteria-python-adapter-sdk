"""CRI-308 conformance case: concurrent Execute calls on ONE session.

Drives N (>= 3) concurrent Execute RPCs against a single open session of
an adapter-under-test and asserts per-call result correctness:

- every call's stream receives exactly its own ExecuteResult,
- no result is lost,
- no result lands on a sibling's stream,
- a long-running call does not corrupt a sibling's completion.

The contract is per-call RESULT CORRECTNESS, never wall-clock overlap.
A deliberately-broken adapter (shared result state across calls) is run
against the same case and must fail it, proving the case detects that
defect class.
"""

import asyncio
import json
import threading
import time
from concurrent import futures

import pytest

from criteria.v2 import adapter_pb2

from criteria_adapter_sdk.conformance import (
    ConformanceFailure,
    assert_concurrent_execute_on_one_session,
)
from criteria_adapter_sdk.serve import ServeConfig
from criteria_adapter_sdk.testing import TestHost


# ---------------------------------------------------------------------------
# Reference handler(s)
# ---------------------------------------------------------------------------


def _echo_handler(req, helpers):
    """Reference handler: correlate each call to its own result.

    Echoes the per-call marker back into ``outputs_json`` and returns
    the outcome requested on that call.
    """
    return adapter_pb2.ExecuteResult(
        outcome=req.input["outcome"],
        outputs_json=json.dumps({"call_id": req.input["call_id"]}).encode("utf-8"),
    )


async def _echo_handler_async(req, helpers):
    await asyncio.sleep(0)
    return adapter_pb2.ExecuteResult(
        outcome=req.input["outcome"],
        outputs_json=json.dumps({"call_id": req.input["call_id"]}).encode("utf-8"),
    )


def _slow_echo_handler(slow_marker: str, delay: float):
    """Reference handler whose designated call is long-running."""

    def handler(req, helpers):
        if req.input["call_id"] == slow_marker:
            time.sleep(delay)
        return _echo_handler(req, helpers)

    return handler


def _serve_config(handler) -> ServeConfig:
    return ServeConfig(
        name="conformance-adapter",
        version="1.0.0",
        execute=handler,
    )


# ---------------------------------------------------------------------------
# Green cases: reference handlers satisfy the contract
# ---------------------------------------------------------------------------


def test_concurrent_execute_reference_handler_result_correctness():
    """N concurrent Executes on one session: each stream gets its own result."""
    report = assert_concurrent_execute_on_one_session(
        _serve_config(_echo_handler),
        n_calls=5,
        session_id="conc-sync",
    )
    assert report.ok
    assert set(report.streams) == {f"call-{i}" for i in range(5)}
    for marker, stream in report.streams.items():
        assert len(stream.results) == 1


def test_concurrent_execute_async_handler_result_correctness():
    report = assert_concurrent_execute_on_one_session(
        _serve_config(_echo_handler_async),
        n_calls=4,
        session_id="conc-async",
    )
    assert report.ok


def test_long_running_call_does_not_corrupt_sibling_completion():
    """One call blocks mid-flight while its siblings complete; every call
    still receives exactly its own result on its own stream."""
    slow_marker = "call-2"
    handler = _slow_echo_handler(slow_marker, delay=0.4)
    report = assert_concurrent_execute_on_one_session(
        _serve_config(handler),
        n_calls=5,
        session_id="conc-slow",
    )
    assert report.ok

    slow = report.streams[slow_marker]
    assert len(slow.results) == 1
    assert json.loads(slow.results[0].outputs_json) == {"call_id": slow_marker}
    assert slow.results[0].outcome == slow.expected_outcome

    # Every sibling completed with its own result — the long-running call
    # did not corrupt or absorb any of them.
    for marker, stream in report.streams.items():
        if marker == slow_marker:
            continue
        assert len(stream.results) == 1, f"{marker}: sibling result lost"
        assert json.loads(stream.results[0].outputs_json) == {"call_id": marker}, (
            f"{marker}: sibling received a sibling's result"
        )


# ---------------------------------------------------------------------------
# Testing-harness surface: the same case through AdapterTestHost
# ---------------------------------------------------------------------------


def test_testhost_concurrent_execute_on_one_session():
    host = TestHost(
        {
            "name": "harness-conformance",
            "version": "1.0.0",
            "execute": _echo_handler,
        }
    )
    host.open_session(session_id="conc-harness")

    markers = [f"call-{i}" for i in range(5)]

    def drive(marker: str):
        return host.execute(
            session_id="conc-harness",
            step_name=f"step-{marker}",
            input_data={"call_id": marker, "outcome": "success"},
        )

    with futures.ThreadPoolExecutor(max_workers=len(markers)) as pool:
        pending = {pool.submit(drive, m): m for m in markers}
        results = {pending[fut]: fut.result() for fut in futures.as_completed(pending)}

    # Per-call result correctness on one session: every returned result
    # belongs to its own call; none is lost or cross-assigned.
    for marker in markers:
        assert results[marker].outcome == "success"
        assert results[marker].output == {"call_id": marker}

    host.close_session("conc-harness")


# ---------------------------------------------------------------------------
# Deliberately-broken variant: shared result state across calls
# ---------------------------------------------------------------------------


def test_broken_shared_result_state_fails_conformance():
    """A handler that shares ONE result slot across concurrent calls
    (last writer wins) must fail the conformance case.

    All in-flight calls rendezvous on a barrier and then read the shared
    slot after a sibling may have overwritten it, so a sibling's result
    lands on this call's stream.  If scheduling serializes the calls
    instead, the rendezvous is impossible: the barrier times out and the
    call fails outright — which also violates per-call correctness.
    Either way the case detects the defect.
    """
    n = 5
    shared: dict = {}
    barrier = threading.Barrier(n)

    def broken_handler(req, helpers):
        marker = req.input["call_id"]
        try:
            barrier.wait(timeout=5.0)
        except threading.BrokenBarrierError:
            # Serialized scheduling: the rendezvous cannot gather, so the
            # call fails before yielding its own result.
            raise
        shared["call_id"] = marker
        time.sleep(0.02)
        return adapter_pb2.ExecuteResult(
            outcome=req.input["outcome"],
            outputs_json=json.dumps({"call_id": shared["call_id"]}).encode("utf-8"),
        )

    with pytest.raises(ConformanceFailure) as excinfo:
        assert_concurrent_execute_on_one_session(
            _serve_config(broken_handler),
            n_calls=n,
            session_id="conc-broken",
        )

    # The failure must be a per-call result-correctness violation, not
    # an unrelated error.
    message = str(excinfo.value)
    assert "landed on this call's stream" in message or (
        "failed before yielding a result" in message
    )