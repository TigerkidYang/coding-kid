"""Select and start one completed Coding Kid teaching runtime."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from coding_kid import cli

LATEST_VERSION = "v7"
AVAILABLE_VERSIONS = ("v1", "v2", "v3", "v4", "v5", "v6", LATEST_VERSION)
BUNDLED_RUNTIME_DIRS = {
    "v1": "v01",
    "v2": "v02",
    "v3": "v03",
    "v4": "v04",
    "v5": "v05",
    "v6": "v06",
}
RUNTIME_ENTRYPOINT = "from coding_kid.cli import main; main()"


def normalize_version(value: str) -> str:
    """Return the canonical teaching-version name for one CLI value."""
    normalized = value.strip().casefold()
    if normalized.startswith("v"):
        normalized = normalized[1:]

    if not normalized.isdecimal():
        raise ValueError(value)

    version = f"v{int(normalized)}"
    if version not in AVAILABLE_VERSIONS:
        raise ValueError(value)
    return version


def bundled_runtime_root(version: str) -> Path:
    """Return the directory placed first on PYTHONPATH for a historical version."""
    directory = BUNDLED_RUNTIME_DIRS[version]
    root = Path(__file__).resolve().parent / "_runtimes" / directory
    if not (root / "coding_kid" / "cli.py").is_file():
        raise RuntimeError(
            f"Bundled Coding Kid runtime is missing for {version}: {root}"
        )
    return root


def launch_version(version: str, options: cli.SessionOptions | None = None) -> int:
    """Start a selected runtime while preserving the caller's project directory."""
    if version == LATEST_VERSION:
        cli.main(options)
        return 0

    runtime_root = bundled_runtime_root(version)
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    pythonpath_parts = [str(runtime_root)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    environment["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    completed = subprocess.run(
        [sys.executable, "-c", RUNTIME_ENTRYPOINT],
        cwd=Path.cwd(),
        env=environment,
        check=False,
    )
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    """Create the small public command-line interface."""
    parser = argparse.ArgumentParser(
        prog="coding-kid",
        description="Start a completed Coding Kid teaching runtime.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        help=f"teaching version ({', '.join(AVAILABLE_VERSIONS)}; default: {LATEST_VERSION})",
    )
    sessions = parser.add_mutually_exclusive_group()
    sessions.add_argument(
        "--new", action="store_true", help="start a new Version 07 session"
    )
    sessions.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="resume the most recently active project session",
    )
    sessions.add_argument(
        "--resume", metavar="SESSION", help="resume a session ID or unique prefix"
    )
    sessions.add_argument(
        "--list-sessions",
        action="store_true",
        help="list Version 07 sessions for the current project",
    )
    sessions.add_argument(
        "--delete-session",
        metavar="SESSION",
        help="soft-delete a Version 07 session while retaining evidence",
    )
    parser.add_argument(
        "--list-versions",
        action="store_true",
        help="list installed teaching versions and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the requested version and start its runtime."""
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.list_versions:
        for version in AVAILABLE_VERSIONS:
            suffix = " (latest, default)" if version == LATEST_VERSION else ""
            print(f"{version}{suffix}")
        return 0

    try:
        selected_version = (
            LATEST_VERSION
            if arguments.version is None
            else normalize_version(arguments.version)
        )
    except ValueError:
        parser.error(
            f"unknown teaching version {arguments.version!r}; "
            f"available versions: {', '.join(AVAILABLE_VERSIONS)}"
        )

    uses_session_options = any(
        (
            arguments.new,
            arguments.continue_session,
            arguments.resume,
            arguments.list_sessions,
            arguments.delete_session,
        )
    )
    if selected_version != LATEST_VERSION and uses_session_options:
        parser.error("session options are available only for Version 07")
    options = cli.SessionOptions(
        mode=(
            "continue"
            if arguments.continue_session
            else "resume"
            if arguments.resume
            else "new"
        ),
        session_id=arguments.resume,
        list_only=arguments.list_sessions,
        delete_session=arguments.delete_session,
    )
    return launch_version(selected_version, options)
