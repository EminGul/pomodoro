import os
import socket
import threading
from pathlib import Path
from unittest.mock import patch

from pomodoro.player import _ipc_send_pipe, _ipc_send_unix, _parse_ipc_response


def test_parse_ipc_response_extracts_matching_data():
    lines = ['{"event": "start-file"}', '{"request_id": 1, "data": "My Song", "error": "success"}']
    assert _parse_ipc_response(lines, request_id=1) == "My Song"


def test_parse_ipc_response_ignores_other_request_ids():
    lines = ['{"request_id": 2, "data": "Other"}']
    assert _parse_ipc_response(lines, request_id=1) is None


def test_parse_ipc_response_ignores_malformed_lines():
    lines = ["not json", '{"request_id": 1, "data": "My Song"}']
    assert _parse_ipc_response(lines, request_id=1) == "My Song"


def test_parse_ipc_response_returns_none_when_no_lines():
    assert _parse_ipc_response([], request_id=1) is None


def test_parse_ipc_response_returns_none_when_data_missing():
    lines = ['{"request_id": 1, "error": "property unavailable"}']
    assert _parse_ipc_response(lines, request_id=1) is None


def test_parse_ipc_response_returns_none_when_data_is_null():
    lines = ['{"request_id": 1, "data": null}']
    assert _parse_ipc_response(lines, request_id=1) is None


def test_parse_ipc_response_accepts_falsy_but_present_data():
    lines = ['{"request_id": 1, "data": ""}']
    assert _parse_ipc_response(lines, request_id=1) == ""


def test_ipc_send_pipe_script_anchors_request_id_match():
    # Regression guard: the match must not treat "1" as a substring of "10", "19", etc.
    # Capture the generated script instead of invoking powershell.
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["script"] = cmd[-1]
        raise FileNotFoundError

    with patch("pomodoro.player.subprocess.run", side_effect=fake_run):
        _ipc_send_pipe({"command": ["get_property", "media-title"], "request_id": 1}, request_id=1)

    assert '"request_id":1(?!\\d)' in captured["script"]


def test_ipc_send_unix_keeps_reading_past_an_unrelated_line():
    sock_path = Path(f"/tmp/pomodoro-test-ipc-{os.getpid()}.sock")
    sock_path.unlink(missing_ok=True)
    listening = threading.Event()

    def serve():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(sock_path))
            srv.listen(1)
            listening.set()
            conn, _ = srv.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(b'{"event": "start-file"}\n')
                conn.sendall(b'{"request_id": 1, "data": "Real Title", "error": "success"}\n')

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    try:
        listening.wait(timeout=2)
        with patch("pomodoro.player._IPC_SOCK_PATH", sock_path):
            lines = _ipc_send_unix({"command": ["get_property", "media-title"], "request_id": 1}, request_id=1)
        assert _parse_ipc_response(lines, request_id=1) == "Real Title"
    finally:
        server_thread.join(timeout=2)
        sock_path.unlink(missing_ok=True)
