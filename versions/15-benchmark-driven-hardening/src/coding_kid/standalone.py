"""Parse Version 15 flags without the root cross-version launcher."""

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
    parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="workspace-write",
    )
    parser.add_argument("--sandbox-image", default=cli.DEFAULT_SANDBOX_IMAGE)
    parser.add_argument("--sandbox-network", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("plan", "implementation", "review"),
        default="implementation",
    )
    parser.add_argument(
        "--approval",
        choices=("cautious", "auto", "full-access"),
        default="cautious",
    )
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
            sandbox_mode=arguments.sandbox,
            sandbox_image=arguments.sandbox_image,
            sandbox_network=arguments.sandbox_network,
            collaboration_mode=arguments.mode,
            approval_policy=arguments.approval,
        )
    )
