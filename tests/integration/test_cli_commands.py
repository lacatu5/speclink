from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from speclink.cli import app

runner = CliRunner()


class TestCLICommands:
    def test_guide_command_succeeds(self):
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0

    def test_analyze_without_config_fails(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code == 1

    def test_sync_without_docmap_fails(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 1

    def test_app_help_shows_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "scope" in result.output
        assert "analyze" in result.output
        assert "sync" in result.output
        assert "guide" in result.output
