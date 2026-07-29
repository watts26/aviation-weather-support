import json
import logging
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import aviation_weather_support as cli
from aviation_weather_support.logging_config import (
    LoggingSetupError,
    configure_logging,
)


FIXTURE = Path(__file__).parent / "fixtures" / "metar-katl-success.json"


@pytest.fixture(autouse=True)
def reset_package_logging():
    configure_logging(verbose=False, log_file=None)
    yield
    configure_logging(verbose=False, log_file=None)


def run_cli(monkeypatch, tmp_path, options):
    response = Mock()
    response.json.return_value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr("aviation_weather_support.api.requests.get", Mock(return_value=response))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["aviation-weather-support", "KATL", *options],
    )

    cli.main()


def test_normal_execution_has_no_verbose_logging(monkeypatch, tmp_path, capsys):
    run_cli(monkeypatch, tmp_path, [])

    captured = capsys.readouterr()
    assert "Saved METAR data for KATL." in captured.out
    assert captured.err == ""


def test_verbose_writes_info_messages_to_console(monkeypatch, tmp_path, capsys):
    run_cli(monkeypatch, tmp_path, ["--verbose"])

    stderr = capsys.readouterr().err
    assert (
        "INFO aviation_weather_support.workflow: Normalized airport identifier: KATL"
        in stderr
    )
    assert "INFO aviation_weather_support.api: Starting METAR API request for KATL" in stderr
    assert "DEBUG" not in stderr


def test_log_file_contains_debug_messages(monkeypatch, tmp_path, capsys):
    log_path = tmp_path / "nested" / "aviation-weather-support.log"

    run_cli(monkeypatch, tmp_path, ["--log-file", str(log_path)])

    assert capsys.readouterr().err == ""
    log_text = log_path.read_text(encoding="utf-8")
    assert "DEBUG aviation_weather_support.api: Requesting METAR endpoint" in log_text
    assert "DEBUG aviation_weather_support: Raw output path:" in log_text


def test_verbose_and_log_file_can_be_used_together(monkeypatch, tmp_path, capsys):
    log_path = tmp_path / "logs" / "combined.log"

    run_cli(
        monkeypatch,
        tmp_path,
        ["--verbose", "--log-file", str(log_path)],
    )

    stderr = capsys.readouterr().err
    log_text = log_path.read_text(encoding="utf-8")
    assert "INFO aviation_weather_support.models: METAR observation validation succeeded" in stderr
    assert "DEBUG aviation_weather_support.api: Requesting METAR endpoint" in log_text


def test_reconfiguration_does_not_duplicate_handlers_or_messages(capsys):
    configure_logging(verbose=True, log_file=None)
    configure_logging(verbose=True, log_file=None)

    logging.getLogger("aviation_weather_support.test").info("one message")

    assert capsys.readouterr().err.count("one message") == 1


def test_unwritable_log_file_has_a_clear_error(tmp_path):
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("content", encoding="utf-8")
    log_path = blocking_file / "application.log"

    with pytest.raises(
        LoggingSetupError,
        match=r"Could not write log file to .*application.log",
    ):
        configure_logging(verbose=False, log_file=log_path)
