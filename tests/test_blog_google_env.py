"""blog-google builds its venv with uv when present and falls back to pip."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "blog-google" / "scripts" / "setup_environment.py"
spec = importlib.util.spec_from_file_location("blog_google_setup_environment", SCRIPT)
env_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env_mod)


@pytest.fixture(autouse=True)
def _pip_by_default(monkeypatch):
    monkeypatch.setenv("AI_CONTENT_NO_UV", "1")


def _skill(tmp_path, monkeypatch):
    """A SkillEnvironment whose skill dir is a temp folder holding a requirements.txt."""
    skill = tmp_path / "skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "requirements.txt").write_text("requests\n", encoding="utf-8")
    monkeypatch.setattr(env_mod, "__file__", str(skill / "scripts" / "setup_environment.py"))
    return env_mod.SkillEnvironment()


def _fake_uv(tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")
    return uv


def test_find_uv_honours_opt_out_override_and_absence(monkeypatch, tmp_path):
    uv = _fake_uv(tmp_path)
    monkeypatch.setenv("UV", str(uv))
    assert env_mod.find_uv() is None
    monkeypatch.delenv("AI_CONTENT_NO_UV")
    assert env_mod.find_uv() == str(uv)
    monkeypatch.delenv("UV")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(env_mod.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
    assert env_mod.find_uv() is None


def test_uv_creates_the_venv_and_installs(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_CONTENT_NO_UV")
    uv = _fake_uv(tmp_path)
    monkeypatch.setenv("UV", str(uv))
    env = _skill(tmp_path, monkeypatch)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == [str(uv), "venv"]:
            env.venv_python.parent.mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(env_mod.subprocess, "run", fake_run)
    assert env.ensure_venv() is True
    assert calls[0][:3] == [str(uv), "venv", "--quiet"]
    assert calls[1][:5] == [str(uv), "pip", "install", "--quiet", "--python"]
    assert env.dependencies_current()


def test_uv_install_failure_falls_back_to_the_venv_pip(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_CONTENT_NO_UV")
    uv = _fake_uv(tmp_path)
    monkeypatch.setenv("UV", str(uv))
    env = _skill(tmp_path, monkeypatch)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == [str(uv), "venv"]:
            env.venv_python.parent.mkdir(parents=True)
        if cmd[0] == str(uv) and cmd[1] == "pip":
            raise subprocess.CalledProcessError(2, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(env_mod.subprocess, "run", fake_run)
    assert env.ensure_venv() is True
    assert calls[-1][0] == str(env.venv_pip)


def test_without_uv_the_old_venv_and_pip_path_runs(monkeypatch, tmp_path):
    env = _skill(tmp_path, monkeypatch)
    calls = []

    def fake_create(path, with_pip=False):
        assert with_pip is True
        env.venv_python.parent.mkdir(parents=True)

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(env_mod.venv, "create", fake_create)
    monkeypatch.setattr(env_mod.subprocess, "run", fake_run)
    assert env.ensure_venv() is True
    assert calls == [[str(env.venv_pip), "install", "-r", str(env.requirements_file)]]
