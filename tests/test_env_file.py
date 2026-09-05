"""Tests for the .env credential loader.

The loader exists so that keys never have to be typed on a command line, where
they land in shell history and in the process table. These tests pin the two
properties that make that safe: values are parsed literally, and no value is
ever echoed back.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import env_file

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


class TestParse:
    def test_plain_pair(self):
        assert env_file.parse("A=hello world") == {"A": "hello world"}

    def test_hash_is_part_of_the_value_not_a_comment(self):
        """Passwords routinely contain '#'. Inline comment stripping would corrupt them."""
        assert env_file.parse("B=p@ss#w0rd!") == {"B": "p@ss#w0rd!"}

    def test_only_the_first_equals_splits(self):
        assert env_file.parse("C=abc=def") == {"C": "abc=def"}

    def test_export_prefix_is_tolerated(self):
        assert env_file.parse("export D=xyz") == {"D": "xyz"}

    def test_no_shell_expansion(self):
        assert env_file.parse("E=$HOME/x") == {"E": "$HOME/x"}

    def test_double_quotes_are_stripped_and_escapes_decoded(self):
        assert env_file.parse('F="a\\nb"') == {"F": "a\nb"}

    def test_single_quotes_are_literal(self):
        assert env_file.parse("G='a\\nb'") == {"G": "a\\nb"}

    @pytest.mark.parametrize("line", ["# H=nope", "", "   ", "not a pair", "=novalue", "1BAD=x"])
    def test_malformed_lines_are_skipped_without_raising(self, line):
        assert env_file.parse(line) == {}

    def test_byte_order_mark_does_not_swallow_the_first_key(self):
        assert env_file.parse("﻿I=ok") == {"I": "ok"}


class TestLoad:
    def test_existing_environment_variable_wins(self, tmp_path, monkeypatch):
        path = tmp_path / ".env"
        path.write_text("K_ENVFILE=from-file\n", encoding="utf-8")
        monkeypatch.setenv("K_ENVFILE", "from-shell")
        env_file.load(path)
        assert os.environ["K_ENVFILE"] == "from-shell"

    def test_override_flag_replaces_it(self, tmp_path, monkeypatch):
        path = tmp_path / ".env"
        path.write_text("K_ENVFILE=from-file\n", encoding="utf-8")
        monkeypatch.setenv("K_ENVFILE", "from-shell")
        env_file.load(path, override=True)
        assert os.environ["K_ENVFILE"] == "from-file"

    def test_returns_names_never_values(self, tmp_path, monkeypatch):
        path = tmp_path / ".env"
        path.write_text("K_SECRET_ENVFILE=swordfish\n", encoding="utf-8")
        monkeypatch.delenv("K_SECRET_ENVFILE", raising=False)
        applied = env_file.load(path)
        assert applied == ["K_SECRET_ENVFILE"]
        assert "swordfish" not in repr(applied)

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert env_file.load(tmp_path / "absent") == []


class TestDiscovery:
    def test_empty_override_disables_loading(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_ENV_FILE", "")
        assert env_file.candidate_paths() == []
        assert env_file.find_env_file() is None

    def test_override_points_at_one_file(self, tmp_path, monkeypatch):
        path = tmp_path / "custom.env"
        path.write_text("A=1\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_ENV_FILE", str(path))
        assert env_file.find_env_file() == path

    def test_default_search_prefers_the_shared_claude_directory(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
        assert env_file.candidate_paths()[0] == Path.home() / ".claude" / ".env"


class TestNoLeakage:
    def test_check_masks_secret_values(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text(
            "DATAFORSEO_PASSWORD=SENTINEL-PASSWORD\nPEXELS_API_KEY=SENTINEL-KEY\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        env = dict(os.environ)
        env["CLAUDE_ENV_FILE"] = str(path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "env_file.py"), "--check"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert proc.returncode == 0
        combined = proc.stdout + proc.stderr
        assert "SENTINEL-PASSWORD" not in combined
        assert "SENTINEL-KEY" not in combined
        assert "DATAFORSEO_PASSWORD" in combined

    def test_loose_permissions_are_reported(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("A=1\n", encoding="utf-8")
        path.chmod(0o644)
        env = dict(os.environ)
        env["CLAUDE_ENV_FILE"] = str(path)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "env_file.py"), "--check"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert "chmod 600" in proc.stderr


class TestWiring:
    """Every script that reads a credential must load the file first."""

    CREDENTIAL_SCRIPTS = (
        "dataforseo_labs.py",
        "generate_hero.py",
        "blog_preflight.py",
        "sync_flow.py",
    )

    @pytest.mark.parametrize("name", CREDENTIAL_SCRIPTS)
    def test_script_imports_the_loader(self, name):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "import env_file" in text, "{0} reads credentials but never loads .env".format(name)
