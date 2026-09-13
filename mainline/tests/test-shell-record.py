#!/usr/bin/env python3
"""Bounded numeric export, partial evidence and session changes; no device or network."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("control", repo / "mainline/gaming-shell/control.py")
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
base = {"session": str(uuid.uuid4()), "binary_sha256": "a" * 64,
        "capture": {"status": "not_requested"},
        "state": {"device": {"target": False, "controls": False, "secret": "private-fixture"},
                  "telemetry": {"active": True, "processCpu": 12.5, "residentMiB": 42, "uiSubmissions": 58},
                  "text": "private-fixture"}}

with tempfile.TemporaryDirectory(prefix="record-check-", dir=repo / "mainline/out/.cache") as temporary:
    root = Path(temporary)
    for scenario, expected in [("complete", 3), ("disconnect", 1), ("restart", 1)]:
        clock = [0.0]; calls = [0]

        def send(request):
            assert request["op"] == "observe" and request["screenshot"] is False
            calls[0] += 1
            if scenario == "disconnect" and calls[0] > 1:
                raise OSError("private-fixture")
            response = copy.deepcopy(base)
            if scenario == "restart" and calls[0] > 1:
                response["session"] = str(uuid.uuid4())
            return response

        with patch.object(control.time, "monotonic", lambda: clock[0]), \
                patch.object(control.time, "sleep", lambda n: clock.__setitem__(0, clock[0] + n)):
            result = control.record_samples(send, root / scenario, 6, 2, "a" * 64)
        assert result["samples"] == expected
        assert result["status"] == ("complete" if scenario == "complete" else "partial")
        trace = Path(result["json"]); table = Path(result["csv"])
        assert "private-fixture" not in trace.read_text() + table.read_text()
        assert trace.stat().st_mode & 0o777 == 0o600 and table.stat().st_mode & 0o777 == 0o600
        assert len(json.loads(trace.read_text())["samples"]) == expected
        assert calls[0] == (3 if scenario == "complete" else 2)  # No retry after a failed observation.

    for bad in [float("nan"), True, "58", -2]:
        response = copy.deepcopy(base); response["state"]["telemetry"]["processCpu"] = bad
        try:
            control.record_values(response)
        except control.ControlError:
            pass
        else:
            raise AssertionError("invalid metric accepted")
    for seconds, interval in [(1, 1), (301, 2), (2, 3), (30, 0)]:
        try:
            control.record_samples(lambda _: (_ for _ in ()).throw(AssertionError("unexpected request")), root, seconds, interval)
        except control.ControlError:
            pass
        else:
            raise AssertionError("unbounded recording accepted")
    response = copy.deepcopy(base)
    response["state"]["device"] = {**{key: 0 for key in control.DEVICE_METRICS},
                                   "target": True, "controls": True, "lowVoltage": False, "hot": False}
    assert "socTemperatureC" not in control.record_values(response)  # Older device endpoints remain readable.
    response["state"]["device"].update(socTemperatureC=65.5, cpuCoolingState=1, gpuCoolingState=0)
    assert control.record_values(response)["socTemperatureC"] == 65.5
    response = copy.deepcopy(base)
    response['state']['telemetry']['game'] = {'active': True, 'submissions': 59.5, 'intervalMedianMs': 16.7, 'intervalP95Ms': 18.2,
                                             'intervalMaxMs': 25, 'lastFrameAgeMs': 4, 'outputRefreshHz': 60}
    assert control.record_values(response)['gameSubmissions'] == 59.5
    response['state']['telemetry']['game']['submissions'] = '59.5'
    try:
        control.record_values(response)
    except control.ControlError:
        pass
    else:
        raise AssertionError('invalid game frame value accepted')
    waiting = copy.deepcopy(base)
    waiting['state'].update(externalSession=True, sharedReady=True)
    waiting['state']['telemetry']['game'] = {}
    clock = [0.0]; calls = [0]
    def send_frame(request):
        assert request['op'] == 'observe' and request['screenshot'] is False
        calls[0] += 1
        response = copy.deepcopy(waiting)
        if calls[0] > 1: response['state']['telemetry']['game'] = {'active': True, 'submissions': -1, 'lastFrameAgeMs': -1}
        if calls[0] == 3: response['state']['telemetry']['game'].update(submissions=55, lastFrameAgeMs=4)
        return response
    with patch.object(control.time, 'monotonic', lambda: clock[0]), \
            patch.object(control.time, 'sleep', lambda n: clock.__setitem__(0, clock[0] + n)):
        assert control.wait_game_frame(send_frame, 2, 'a' * 64)['state']['telemetry']['game']['submissions'] == 55
    assert calls[0] == 3
    response = copy.deepcopy(base)
    response['state']['telemetry']['stream'] = {'active': True, 'available': True, 'renderedFps': 59.5, 'audioNetworkQueueMs': 5}
    values = control.record_values(response)
    assert values['streamRenderedFps'] == 59.5 and values['streamAudioNetworkQueueMs'] == 5
    assert values['streamDecodeMs'] == -1
    response['state']['telemetry']['stream']['renderedFps'] = 'private-fixture'
    try:
        control.record_values(response)
    except control.ControlError:
        pass
    else:
        raise AssertionError('invalid stream metric accepted')
print("SHELL_RECORD_CHECK PASS: numeric-only CSV/JSON, bounded game-frame wait, partial evidence and no retry after session loss")
