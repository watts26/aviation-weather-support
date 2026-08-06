from unittest.mock import Mock

import pytest

from aviation_weather_support.dashboard_launcher import (
    DashboardDependencyError,
    launch_dashboard,
)


def test_dashboard_launcher_explains_missing_optional_extra(monkeypatch):
    monkeypatch.setattr(
        "aviation_weather_support.dashboard_launcher.find_spec", lambda name: None
    )

    with pytest.raises(DashboardDependencyError, match=r"\[dashboard\]"):
        launch_dashboard([])


def test_dashboard_launcher_uses_installed_module_path(monkeypatch):
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(
        "aviation_weather_support.dashboard_launcher.find_spec",
        lambda name: object(),
    )
    monkeypatch.setattr(
        "aviation_weather_support.dashboard_launcher.subprocess.run", run
    )

    assert launch_dashboard(["--port", "8510", "--headless"]) == 0
    command = run.call_args.args[0]
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4].endswith("aviation_weather_support\\dashboard.py") or (
        command[4].endswith("aviation_weather_support/dashboard.py")
    )
    assert command[-4:] == ["--server.port", "8510", "--server.headless", "true"]
