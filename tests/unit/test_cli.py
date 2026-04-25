from __future__ import annotations

from typer.testing import CliRunner

from unittest.mock import MagicMock, patch

from speclink.cli import app

runner = CliRunner()


def _command_names():
    return [c.callback.__name__ for c in app.registered_commands if c.callback]


def test_app_has_scope_command():
    assert "scope" in _command_names()


def test_app_has_analyze_command():
    assert "analyze" in _command_names()


def test_app_has_sync_command():
    assert "sync" in _command_names()


def test_guide_command_prints_output():
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0
    assert "GitHub Secrets Setup" in result.output


def test_analyze_command_exits_without_config():
    with patch("speclink.cli.config_path") as mock_cp:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_cp.return_value = mock_path
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code != 0


def test_sync_command_exits_without_docmap():
    with patch("speclink.cli.docmap_path") as mock_dp:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_dp.return_value = mock_path
        result = runner.invoke(app, ["sync"])
        assert result.exit_code != 0


def test_scope_command_calls_run_wizard():
    with patch("speclink.cli.run_wizard"):
        result = runner.invoke(app, ["scope"])
        assert result.exit_code == 0


def test_analyze_command_success():
    with (
        patch("speclink.cli.config_path") as mock_cp,
        patch("speclink.cli.analyze_repo"),
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_cp.return_value = mock_path
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code == 0


def test_analyze_command_handles_exception():
    with (
        patch("speclink.cli.config_path") as mock_cp,
        patch("speclink.cli.analyze_repo", side_effect=RuntimeError("boom")),
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_cp.return_value = mock_path
        result = runner.invoke(app, ["analyze"])
        assert result.exit_code == 1


def test_sync_command_success():
    with (
        patch("speclink.cli.docmap_path") as mock_dp,
        patch("speclink.cli.sync_repo") as mock_sync,
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_dp.return_value = mock_path
        mock_report = MagicMock()
        mock_report.total_errors = 0
        mock_sync.return_value = mock_report
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 0


def test_sync_command_reports_errors():
    with (
        patch("speclink.cli.docmap_path") as mock_dp,
        patch("speclink.cli.sync_repo") as mock_sync,
    ):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_dp.return_value = mock_path
        mock_report = MagicMock()
        mock_report.total_errors = 3
        mock_sync.return_value = mock_report
        result = runner.invoke(app, ["sync"])
        assert result.exit_code == 1
