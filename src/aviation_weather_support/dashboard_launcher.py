"""Launch the packaged Streamlit dashboard from an installed command."""

import argparse
from importlib.util import find_spec
from pathlib import Path
import subprocess
import sys
from typing import Sequence


class DashboardDependencyError(RuntimeError):
    """Raised when the optional dashboard dependency is unavailable."""


def launch_dashboard(argv: Sequence[str] | None = None) -> int:
    """Run Streamlit against the installed dashboard module."""

    if find_spec("streamlit") is None:
        raise DashboardDependencyError(
            "Dashboard support is not installed. Install "
            "'aviation-weather-support[dashboard]' and try again."
        )

    parser = argparse.ArgumentParser(
        prog="aviation-weather-support dashboard",
        description="Launch the Aviation Weather Support Streamlit dashboard.",
    )
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--address", default=None)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).with_name("dashboard.py")),
    ]
    if args.port is not None:
        command.extend(["--server.port", str(args.port)])
    if args.address is not None:
        command.extend(["--server.address", args.address])
    if args.headless:
        command.extend(["--server.headless", "true"])
    return subprocess.run(command, check=False).returncode
