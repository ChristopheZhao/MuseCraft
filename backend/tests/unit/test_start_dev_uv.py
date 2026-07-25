import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import dev as dev_alias
from scripts import start_dev as start_dev_alias
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


def test_legacy_dev_entrypoints_forward_to_canonical_launcher():
    assert dev_alias.main is module.main
    assert start_dev_alias.main is module.main


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
    assert (
        "Celery worker logs forwarded to parent stdout (FOLLOW_CELERY_LOGS=1)"
        in capsys.readouterr().out
    )


def test_collect_repo_managed_process_groups_filters_to_repo_root(monkeypatch):
    repo_root = Path("/repo/backend")
    processes = [
        SimpleNamespace(
            info={
                "pid": 100,
                "cmdline": ["python", "-m", "uvicorn", "app.main:app", "--port", "8005"],
                "cwd": str(repo_root),
            }
        ),
        SimpleNamespace(
            info={
                "pid": 200,
                "cmdline": ["python", "-m", "uvicorn", "app.main:app", "--port", "9000"],
                "cwd": "/other/backend",
            }
        ),
        SimpleNamespace(
            info={
                "pid": 300,
                "cmdline": [
                    "python",
                    "-m",
                    "watchdog.watchmedo",
                    "auto-restart",
                    "--",
                    "python",
                    "-m",
                    "celery",
                    "-A",
                    "app.services.celery_app",
                    "worker",
                ],
                "cwd": str(repo_root),
            }
        ),
        SimpleNamespace(
            info={"pid": 400, "cmdline": ["python", "other.py"], "cwd": str(repo_root)}
        ),
    ]

    monkeypatch.setattr(module.psutil, "process_iter", lambda attrs: processes)
    monkeypatch.setattr(module, "_is_windows", lambda: True)

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

    monkeypatch.setattr(
        module, "_collect_repo_managed_process_groups", lambda repo_root: [residual]
    )
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

    monkeypatch.setattr(
        module, "_collect_repo_managed_process_groups", lambda repo_root: responses.pop(0)
    )
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
    terminate_calls = []
    stop_calls = []
    responses = [[residual], []]

    monkeypatch.setattr(
        module,
        "_terminate_started_process",
        lambda process, *, label, wait_timeout=5.0: terminate_calls.append((process.pid, label))
        or True,
    )
    monkeypatch.setattr(
        module, "_collect_repo_managed_process_groups", lambda current_repo_root: responses.pop(0)
    )
    monkeypatch.setattr(
        module,
        "_stop_managed_process_groups",
        lambda groups, *, context: stop_calls.append((groups, context)) or True,
    )
    module.cleanup_processes({"api_server": dummy_process}, repo_root)

    assert terminate_calls == [(dummy_process.pid, "api_server")]
    assert stop_calls == [([residual], "shutdown residual cleanup")]
    assert "No repo-local managed service residuals remain" in capsys.readouterr().out


def test_main_cleans_up_after_keyboard_interrupt(monkeypatch):
    cleanup_calls = []
    api_process = _DummyProcess(wait_exception=KeyboardInterrupt())
    worker_process = _DummyProcess()
    beat_process = _DummyProcess()

    monkeypatch.setattr(
        module, "_parse_args", lambda argv=None: SimpleNamespace(cleanup_residuals=False)
    )
    monkeypatch.setattr(module, "check_uv_available", lambda: True)
    monkeypatch.setattr(module, "check_virtual_environment", lambda: True)
    monkeypatch.setattr(module, "show_environment_info", lambda: None)
    monkeypatch.setattr(
        module, "_handle_startup_residuals", lambda repo_root, *, cleanup_residuals: True
    )
    monkeypatch.setattr(module, "check_dependencies", lambda: True)
    monkeypatch.setattr(module, "run_migrations", lambda: True)
    monkeypatch.setattr(module, "start_celery_worker", lambda: worker_process)
    monkeypatch.setattr(module, "start_celery_beat", lambda: beat_process)
    monkeypatch.setattr(module, "start_api_server", lambda: api_process)
    monkeypatch.setattr(
        module,
        "cleanup_processes",
        lambda processes, repo_root=None: cleanup_calls.append((processes, repo_root)),
    )

    assert module.main([]) == 0

    assert cleanup_calls
    assert "api_server" in cleanup_calls[0][0]


def test_load_project_environment_uses_root_without_overriding_process_values(monkeypatch):
    calls = []
    monkeypatch.setattr(
        module,
        "load_dotenv",
        lambda path, *, override: calls.append((path, override)) or True,
    )

    assert module._load_project_environment() is True
    assert calls == [(module.PROJECT_ROOT / ".env", False)]


def test_virtual_environment_check_requires_canonical_backend_venv(monkeypatch, capsys):
    monkeypatch.setattr(module.sys, "base_prefix", str(module.BACKEND_ROOT))
    monkeypatch.setattr(module.sys, "prefix", str(module.CANONICAL_VENV))

    assert module.check_virtual_environment() is True
    assert str(module.CANONICAL_VENV.resolve()) in capsys.readouterr().out

    monkeypatch.setattr(module.sys, "prefix", str(module.PROJECT_ROOT / ".venv"))

    assert module.check_virtual_environment() is False
    output = capsys.readouterr().out
    assert "reason_code=noncanonical_backend_virtual_environment" in output
    assert str(module.CANONICAL_VENV.resolve()) in output


def test_environment_check_rejects_process_cleanup(capsys):
    with pytest.raises(SystemExit) as exc_info:
        module._parse_args(["--environment-check", "--cleanup-residuals"])

    assert exc_info.value.code == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_main_environment_check_does_not_touch_external_services(monkeypatch, capsys):
    external_calls = []

    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda argv=None: SimpleNamespace(
            cleanup_residuals=False,
            check=False,
            environment_check=True,
        ),
    )
    monkeypatch.setattr(module, "check_uv_available", lambda: True)
    monkeypatch.setattr(module, "check_virtual_environment", lambda: True)
    monkeypatch.setattr(module, "show_environment_info", lambda: None)
    monkeypatch.setattr(
        module,
        "_handle_startup_residuals",
        lambda *args, **kwargs: external_calls.append("processes"),
    )
    monkeypatch.setattr(module, "check_dependencies", lambda: external_calls.append("dependencies"))
    monkeypatch.setattr(module, "run_migrations", lambda: external_calls.append("migrations"))

    assert module.main([]) == 0
    assert external_calls == []
    assert "external services were not checked" in capsys.readouterr().out


def test_mysql_dependency_check_fails_before_connection(capsys):
    assert (
        module._check_database_dependency(
            profile="local",
            database_url="mysql://user:password@localhost/db",
        )
        is False
    )
    output = capsys.readouterr().out
    assert "reason_code=unsupported_database_backend" in output
    assert "backend=mysql" in output


def test_process_group_creation_is_platform_specific(monkeypatch):
    monkeypatch.setattr(module, "_is_windows", lambda: False)
    assert module._new_process_group_kwargs() == {"start_new_session": True}

    monkeypatch.setattr(module, "_is_windows", lambda: True)
    kwargs = module._new_process_group_kwargs()
    assert kwargs["creationflags"]
    assert "start_new_session" not in kwargs


def test_terminate_started_posix_process_reaps_before_residual_check(monkeypatch):
    process = _DummyProcess()
    kill_calls = []

    monkeypatch.setattr(module, "_is_windows", lambda: False)
    monkeypatch.setattr(
        module.os,
        "killpg",
        lambda pgid, requested_signal: kill_calls.append((pgid, requested_signal)),
        raising=False,
    )
    monkeypatch.setattr(module, "_process_group_alive", lambda pgid: False)

    assert module._terminate_started_process(process, label="worker") is True
    assert kill_calls == [(process.pid, module.signal.SIGTERM)]
    assert process.wait_calls == [5.0]


def test_main_fails_closed_when_worker_does_not_start(monkeypatch, capsys):
    cleanup_calls = []
    beat_calls = []
    api_calls = []

    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda argv=None: SimpleNamespace(cleanup_residuals=False, check=False),
    )
    monkeypatch.setattr(module, "check_uv_available", lambda: True)
    monkeypatch.setattr(module, "check_virtual_environment", lambda: True)
    monkeypatch.setattr(module, "show_environment_info", lambda: None)
    monkeypatch.setattr(
        module, "_handle_startup_residuals", lambda repo_root, *, cleanup_residuals: True
    )
    monkeypatch.setattr(module, "check_dependencies", lambda: True)
    monkeypatch.setattr(module, "run_migrations", lambda: True)
    monkeypatch.setattr(module, "start_celery_worker", lambda: None)
    monkeypatch.setattr(module, "start_celery_beat", lambda: beat_calls.append(True))
    monkeypatch.setattr(module, "start_api_server", lambda: api_calls.append(True))
    monkeypatch.setattr(
        module,
        "cleanup_processes",
        lambda processes, repo_root=None: cleanup_calls.append(dict(processes)),
    )

    assert module.main([]) == 1
    assert beat_calls == []
    assert api_calls == []
    assert cleanup_calls == [{"celery_worker": None}]
    assert "startup aborted because the Celery worker did not start" in capsys.readouterr().out


def test_main_check_mode_stops_before_long_lived_services(monkeypatch):
    cleanup_calls = []
    start_calls = []

    monkeypatch.setattr(
        module,
        "_parse_args",
        lambda argv=None: SimpleNamespace(cleanup_residuals=False, check=True),
    )
    monkeypatch.setattr(module, "check_uv_available", lambda: True)
    monkeypatch.setattr(module, "check_virtual_environment", lambda: True)
    monkeypatch.setattr(module, "show_environment_info", lambda: None)
    monkeypatch.setattr(
        module, "_handle_startup_residuals", lambda repo_root, *, cleanup_residuals: True
    )
    monkeypatch.setattr(module, "check_dependencies", lambda: True)
    monkeypatch.setattr(module, "run_migrations", lambda: True)
    monkeypatch.setattr(module, "start_celery_worker", lambda: start_calls.append("worker"))
    monkeypatch.setattr(
        module,
        "cleanup_processes",
        lambda processes, repo_root=None: cleanup_calls.append(dict(processes)),
    )

    assert module.main([]) == 0
    assert start_calls == []
    assert cleanup_calls == [{}]
