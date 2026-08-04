import os
import signal

from core.executors.pytest_executor import PytestExecutor


class _Process:
    pid = 4321

    def __init__(self):
        self.running = True
        self.waited = False

    def poll(self):
        return None if self.running else -signal.SIGTERM

    def wait(self, timeout=None):
        self.waited = True
        self.running = False
        return -signal.SIGTERM


def test_terminate_process_tree_uses_posix_process_group(monkeypatch):
    if os.name == "nt":
        return
    process = _Process()
    calls = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    PytestExecutor._terminate_process_tree(process)

    assert calls == [(4321, signal.SIGTERM)]
    assert process.waited is True
