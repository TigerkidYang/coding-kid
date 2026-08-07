"""Parse Version 16 flags without the root cross-version launcher."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from coding_kid import cli


def main(argv: Sequence[str] | None = None) -> int:
    raw_arguments = tuple(sys.argv[1:] if argv is None else argv)
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
    parser.add_argument(
        "--checkpoint",
        choices=("required", "best-effort", "off"),
        default=None,
        help="required for cautious approval; best-effort otherwise",
    )
    parser.add_argument(
        "--dangerously-bypass-approvals-and-sandbox",
        action="store_true",
        help=(
            "skip approvals, the local sandbox, and application checkpoints; "
            "EXTREMELY DANGEROUS and only for existing external isolation"
        ),
    )
    arguments = parser.parse_args(raw_arguments)
    explicitly_selected = {
        name
        for name in (
            "--sandbox",
            "--sandbox-image",
            "--sandbox-network",
            "--approval",
            "--checkpoint",
        )
        if name in raw_arguments
    }
    if arguments.dangerously_bypass_approvals_and_sandbox:
        if explicitly_selected:
            parser.error(
                "--dangerously-bypass-approvals-and-sandbox cannot be combined "
                f"with {', '.join(sorted(explicitly_selected))}"
            )
        sandbox_mode = "danger-full-access"
        approval_policy = "full-access"
        checkpoint_policy = "off"
    else:
        sandbox_mode = arguments.sandbox
        approval_policy = arguments.approval
        checkpoint_policy = arguments.checkpoint or (
            "required" if approval_policy == "cautious" else "best-effort"
        )
        if checkpoint_policy == "off" and not (
            sandbox_mode == "danger-full-access" and approval_policy == "full-access"
        ):
            parser.error(
                "--checkpoint off requires both --approval full-access and "
                "--sandbox danger-full-access"
            )
    return cli.main(
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
            sandbox_mode=sandbox_mode,
            sandbox_image=arguments.sandbox_image,
            sandbox_network=arguments.sandbox_network,
            collaboration_mode=arguments.mode,
            approval_policy=approval_policy,
            checkpoint_policy=checkpoint_policy,
            dangerous_bypass=arguments.dangerously_bypass_approvals_and_sandbox,
        )
    )
