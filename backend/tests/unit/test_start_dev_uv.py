import subprocess
from types import SimpleNamespace
from pathlib import Path

from scripts import start_dev_uv as module


class _DummyProcess:
    def __init__(self, returncode=None, *, wait_exception=None):
        self._returncode = returncode
        self._wait_exception = wait_exception
        self.pid = 12345
        self.stdout = iter(())
        self.wait_calls = []

    def poll(self):
        return self._returncode

    def communicate(self):
        return ("boom", None)

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self._wait_exception is not None:
            raise self._wait_exception
        return 0 if self._returncode is None else self._returncode


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


def test_collect_repo_managed_process_groups_filters_to_repo_root(monkeypatch):
    repo_root = Path("/repo/backend")
    ps_output = "\n".join(
        [
            "100 100 uv run uvicorn app.main:app --host 0.0.0.0 --port 8005 --log-level info",
            "200 200 uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --log-level info",
            "300 300 uv run watchmedo auto-restart -- celery -A app.services.celery_app worker --loglevel=info",
            "400 400 python some_other_script.py",
        ]
    )

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=ps_output),
    )
    monkeypatch.setattr(
        module,
        "_read_process_cwd",
        lambda pid: {
            100: repo_root,
            200: Path("/other/backend"),
            300: repo_root,
        }.get(pid),
    )

    groups = module._collect_repo_managed_process_groups(repo_root)

    assert [group.pgid for group in groups] == [100, 300]
    assert groups[0].label == "api_server"
    assert groups[0].port == "8005"
    assert groups[1].label == "celery_worker_watchdog"


def test_handle_startup_residuals_fail_fast_without_opt_in(monkeypatch, capsys):
    residual = module.ManagedProcessGroup(
        label="api_server",
        pgid=100,
        pids=(100,),
        commands=("uv run uvicorn app.main:app --port 8005",),
        cwd="/repo/backend",
        port="8005",
    )
    stop_calls = []

    monkeypatch.setattr(module, "_collect_repo_managed_process_groups", lambda repo_root: [residual])
    monkeypatch.setattr(
        module,
        "_stop_managed_process_groups",
        lambda groups, *, context: stop_calls.append((groups, context)) or True,
    )

    ok = module._handle_startup_residuals(Path("/repo/backend"), cleanup_residuals=False)

    assert ok is False
    assert stop_calls == []
    out = capsys.readouterr().out
    assert "Refusing to start a new dev stack" in out
    assert "--cleanup-residuals" in out


def test_handle_startup_residuals_cleans_when_opted_in(monkeypatch, capsys):
    residual = module.ManagedProcessGroup(
        label="api_server",
        pgid=100,
        pids=(100,),
        commands=("uv run uvicorn app.main:app --port 8005",),
        cwd="/repo/backend",
        port="8005",
    )
    stop_calls = []
    responses = [[residual], []]

    monkeypatch.setattr(module, "_collect_repo_managed_process_groups", lambda repo_root: responses.pop(0))
    monkeypatch.setattr(
        module,
        "_stop_managed_process_groups",
        lambda groups, *, context: stop_calls.append((groups, context)) or True,
    )

    ok = module._handle_startup_residuals(Path("/repo/backend"), cleanup_residuals=True)

    assert ok is True
    assert len(stop_calls) == 1
    assert stop_calls[0][1] == "startup preflight"
    assert "Cleared repo-local managed service residuals" in capsys.readouterr().out


def test_cleanup_processes_uses_scoped_residual_cleanup_without_broad_pkill(monkeypatch, capsys):
    repo_root = Path("/repo/backend")
    dummy_process = _DummyProcess()
    residual = module.ManagedProcessGroup(
        label="api_server",
        pgid=200,
        pids=(200,),
        commands=("uv run uvicorn app.main:app --port 8005",),
        cwd=str(repo_root),
        port="8005",
    )
    killpg_calls = []
    stop_calls = []
    responses = [[residual], []]

    monkeypatch.setattr(module.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))
    monkeypatch.setattr(module, "_collect_repo_managed_process_groups", lambda current_repo_root: responses.pop(0))
    monkeypatch.setattr(
        module,
        "_stop_managed_process_groups",
        lambda groups, *, context: stop_calls.append((groups, context)) or True,
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected subprocess.run")),
    )

    module.cleanup_processes({"api_server": dummy_process}, repo_root)

    assert killpg_calls
    assert stop_calls == [([residual], "shutdown residual cleanup")]
    assert "No repo-local managed service residuals remain" in capsys.readouterr().out


def test_main_cleans_up_after_keyboard_interrupt(monkeypatch):
    cleanup_calls = []
    api_process = _DummyProcess(wait_exception=KeyboardInterrupt())

    monkeypatch.setattr(module, "_parse_args", lambda argv=None: SimpleNamespace(cleanup_residuals=False))
    monkeypatch.setattr(module, "check_uv_available", lambda: True)
    monkeypatch.setattr(module, "check_virtual_environment", lambda: True)
    monkeypatch.setattr(module, "show_environment_info", lambda: None)
    monkeypatch.setattr(module, "_handle_startup_residuals", lambda repo_root, *, cleanup_residuals: True)
    monkeypatch.setattr(module, "check_dependencies", lambda: True)
    monkeypatch.setattr(module, "run_migrations", lambda: True)
    monkeypatch.setattr(module, "start_celery_worker", lambda: None)
    monkeypatch.setattr(module, "start_celery_beat", lambda: None)
    monkeypatch.setattr(module, "start_api_server", lambda: api_process)
    monkeypatch.setattr(
        module,
        "cleanup_processes",
        lambda processes, repo_root=None: cleanup_calls.append((processes, repo_root)),
    )

    module.main([])

    assert cleanup_calls
    assert "api_server" in cleanup_calls[0][0]
