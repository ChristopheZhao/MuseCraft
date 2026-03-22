import subprocess
from pathlib import Path

from scripts import start_dev_uv as module


class _DummyProcess:
    def __init__(self, returncode=None):
        self._returncode = returncode
        self.pid = 12345
        self.stdout = iter(())

    def poll(self):
        return self._returncode

    def communicate(self):
        return ("boom", None)


def test_start_long_lived_process_inherits_logs_by_default(monkeypatch, capsys):
    popen_kwargs = {}
    dummy_process = _DummyProcess()

    def _fake_popen(cmd, **kwargs):
        popen_kwargs.update(kwargs)
        return dummy_process

    monkeypatch.delenv("FOLLOW_CELERY_LOGS", raising=False)
    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    process = module._start_long_lived_process(
        ["celery", "worker"],
        cwd=Path("."),
        env={},
        label="Celery worker",
        follow_logs_env_var="FOLLOW_CELERY_LOGS",
    )

    assert process is dummy_process
    assert "stdout" not in popen_kwargs
    assert "stderr" not in popen_kwargs
    assert "universal_newlines" not in popen_kwargs
    assert "bufsize" not in popen_kwargs
    assert "Celery worker logs inherited by parent stdout/stderr" in capsys.readouterr().out


def test_start_long_lived_process_forwards_logs_only_when_enabled(monkeypatch, capsys):
    popen_kwargs = {}
    dummy_process = _DummyProcess()
    thread_events = []

    class _FakeThread:
        def __init__(self, *, target, daemon):
            thread_events.append({"target": target, "daemon": daemon, "started": False})

        def start(self):
            thread_events[-1]["started"] = True

    def _fake_popen(cmd, **kwargs):
        popen_kwargs.update(kwargs)
        return dummy_process

    monkeypatch.setenv("FOLLOW_CELERY_LOGS", "1")
    monkeypatch.setattr(module.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module.threading, "Thread", _FakeThread)

    process = module._start_long_lived_process(
        ["celery", "worker"],
        cwd=Path("."),
        env={},
        label="Celery worker",
        follow_logs_env_var="FOLLOW_CELERY_LOGS",
    )

    assert process is dummy_process
    assert popen_kwargs["stdout"] is subprocess.PIPE
    assert popen_kwargs["stderr"] is subprocess.STDOUT
    assert popen_kwargs["universal_newlines"] is True
    assert popen_kwargs["bufsize"] == 1
    assert len(thread_events) == 1
    assert thread_events[0]["daemon"] is True
    assert thread_events[0]["started"] is True
    assert "Celery worker logs forwarded to parent stdout (FOLLOW_CELERY_LOGS=1)" in capsys.readouterr().out
