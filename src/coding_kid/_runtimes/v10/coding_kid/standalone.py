"""Parse Version 10 session flags without the root cross-version launcher."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from coding_kid import cli


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="coding-kid")
    sessions = parser.add_mutually_exclusive_group()
    sessions.add_argument("--new", action="store_true")
    sessions.add_argument("--continue", dest="continue_session", action="store_true")
    sessions.add_argument("--resume", metavar="SESSION")
    sessions.add_argument("--list-sessions", action="store_true")
    sessions.add_argument("--delete-session", metavar="SESSION")
    arguments = parser.parse_args(argv)
    cli.main(
        cli.SessionOptions(
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
    )
