from unittest.mock import MagicMock, patch

import pytest

from pomodoro.notify import (
    BellNotifier,
    CompositeNotifier,
    MsgExeNotifier,
    NotifySendNotifier,
    _BACKENDS,
    detect,
)


# --- Protocol conformance ---

# Every backend registered in _BACKENDS must satisfy the Notifier protocol:
# a `available()` classmethod and a `send(title, body)` instance method.
@pytest.mark.parametrize("cls", _BACKENDS)
def test_backend_has_available(cls):
    assert callable(cls.available)


@pytest.mark.parametrize("cls", _BACKENDS)
def test_backend_has_send(cls):
    instance = cls()
    assert callable(instance.send)


# --- availability detection ---

def test_bell_notifier_always_available():
    assert BellNotifier.available() is True


def test_msg_exe_available_when_on_path():
    with patch("pomodoro.notify.shutil.which", return_value="/mnt/c/Windows/System32/msg.exe"):
        assert MsgExeNotifier.available() is True


def test_msg_exe_unavailable_when_not_on_path():
    with patch("pomodoro.notify.shutil.which", return_value=None):
        assert MsgExeNotifier.available() is False


def test_notify_send_available_when_on_path():
    with patch("pomodoro.notify.shutil.which", return_value="/usr/bin/notify-send"):
        assert NotifySendNotifier.available() is True


def test_notify_send_unavailable_when_not_on_path():
    with patch("pomodoro.notify.shutil.which", return_value=None):
        assert NotifySendNotifier.available() is False


# --- CompositeNotifier ---

def test_composite_calls_all_notifiers():
    a, b = MagicMock(), MagicMock()
    composite = CompositeNotifier([a, b])
    composite.send("Title", "Body")
    a.send.assert_called_once_with("Title", "Body")
    b.send.assert_called_once_with("Title", "Body")


def test_composite_with_no_notifiers_does_not_raise():
    CompositeNotifier([]).send("Title", "Body")


# --- detect() ---

def test_detect_always_includes_bell():
    notifier = detect()
    assert any(isinstance(n, BellNotifier) for n in notifier._notifiers)


def test_detect_includes_msg_exe_when_available():
    with patch("pomodoro.notify.shutil.which", return_value="/path/to/msg.exe"):
        notifier = detect()
    assert any(isinstance(n, MsgExeNotifier) for n in notifier._notifiers)


def test_detect_excludes_msg_exe_when_unavailable():
    with patch("pomodoro.notify.shutil.which", return_value=None):
        notifier = detect()
    assert not any(isinstance(n, MsgExeNotifier) for n in notifier._notifiers)


# --- resilience ---

def test_msg_exe_does_not_raise_on_subprocess_failure():
    with patch("pomodoro.notify.subprocess.run", side_effect=FileNotFoundError):
        MsgExeNotifier().send("Title", "Body")  # must not raise


def test_notify_send_does_not_raise_on_subprocess_failure():
    with patch("pomodoro.notify.subprocess.run", side_effect=FileNotFoundError):
        NotifySendNotifier().send("Title", "Body")  # must not raise


def test_bell_does_not_raise_when_no_pts_devices():
    with patch("pomodoro.notify.glob.glob", return_value=[]):
        BellNotifier().send("Title", "Body")  # must not raise
