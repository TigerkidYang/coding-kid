"""Harbor adapter for evaluating Coding Kid in Terminal-Bench containers."""

from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths


class CodingKidAgent(BaseInstalledAgent):
    """Install a frozen wheel and run one non-interactive Coding Kid turn."""

    _REMOTE_VENV = PurePosixPath("/installed-agent/venv")

    @staticmethod
    def name() -> str:
        return "coding-kid"

    def _wheel_path(self) -> Path:
        configured = self._get_env("CODING_KID_BENCH_WHEEL")
        if not configured:
            raise ValueError("CODING_KID_BENCH_WHEEL is not set")
        wheel = Path(configured).expanduser().resolve()
        if not wheel.is_file() or wheel.suffix != ".whl":
            raise ValueError(f"Coding Kid wheel does not exist: {wheel}")
        return wheel

    def _uv_path(self) -> Path:
        configured = self._get_env("CODING_KID_BENCH_UV")
        if not configured:
            raise ValueError("CODING_KID_BENCH_UV is not set")
        uv = Path(configured).expanduser().resolve()
        if not uv.is_file():
            raise ValueError(f"uv executable does not exist: {uv}")
        return uv

    async def install(self, environment: BaseEnvironment) -> None:
        wheel = self._wheel_path()
        uv = self._uv_path()
        remote_wheel = PurePosixPath("/installed-agent") / wheel.name
        remote_uv = PurePosixPath("/installed-agent/uv")
        await environment.upload_file(wheel, remote_wheel.as_posix())
        await environment.upload_file(uv, remote_uv.as_posix())
        await self.exec_as_root(
            environment,
            command=(
                # Avoid distro package upgrades in large benchmark images. If
                # their Python is too old, uv supplies a portable CPython.
                "python_bin=$(command -v python3 || true); "
                "if [ -z \"$python_bin\" ] || ! \"$python_bin\" -c "
                "'import sys; raise SystemExit(sys.version_info < (3, 11))'; then "
                "mkdir -p /installed-agent/python-bin; "
                f"chmod +x {shlex.quote(remote_uv.as_posix())}; "
                "UV_PYTHON_INSTALL_DIR=/installed-agent/python "
                "UV_PYTHON_BIN_DIR=/installed-agent/python-bin "
                f"{shlex.quote(remote_uv.as_posix())} python install 3.11 "
                "--default --force --no-cache || exit $?; "
                "python_bin=/installed-agent/python-bin/python3.11; fi; "
                f"{shlex.quote(remote_uv.as_posix())} venv --clear "
                f"--python \"$python_bin\" {shlex.quote(self._REMOTE_VENV.as_posix())} "
                "|| exit $?; "
                f"{shlex.quote(remote_uv.as_posix())} pip install "
                f"--python {shlex.quote((self._REMOTE_VENV / 'bin/python').as_posix())} "
                "--no-cache "
                f"--index-url {shlex.quote(self._get_env('PIP_INDEX_URL') or 'https://pypi.org/simple/')} "
                f"{shlex.quote(remote_wheel.as_posix())}"
            ),
        )

    def get_version_command(self) -> str | None:
        return f"{self._REMOTE_VENV / 'bin/coding-kid'} --list-versions | tail -n 1"

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        api_key = self._get_env("CODING_KID_BENCH_API_KEY")
        base_url = self._get_env("CODING_KID_BENCH_BASE_URL")
        if not api_key or not base_url:
            raise ValueError(
                "CODING_KID_BENCH_API_KEY and CODING_KID_BENCH_BASE_URL are required"
            )
        model = (self.model_name or "gpt-5.6-luna").split("/")[-1]
        env = {
            "OPENROUTER_API_KEY": api_key,
            "OPENROUTER_MODEL": model,
            "CODING_KID_PROVIDER_BASE_URL": base_url,
            "CODING_KID_REASONING_EFFORT": "max",
            "CODING_KID_DISABLE_MAX_OUTPUT_TOKENS": "true",
            "CODING_KID_PROVIDER_TIMEOUT_SECONDS": "1800",
            "PYTHONUNBUFFERED": "1",
        }
        output_path = EnvironmentPaths.agent_dir / "coding-kid.txt"
        executable = self._REMOTE_VENV / "bin/coding-kid"
        single_turn_instruction = instruction.replace("\r", " ").replace("\n", " ")
        await self.exec_as_agent(
            environment,
            command=(
                "if command -v git >/dev/null 2>&1 && "
                "! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then "
                "git init -q && git config user.name 'Coding Kid Benchmark' && "
                "git config user.email 'benchmark@localhost' && git add -A && "
                "git commit -qm 'benchmark baseline' --allow-empty; fi && "
                f"printf '%s\\n' {shlex.quote(single_turn_instruction)} | "
                f"{shlex.quote(executable.as_posix())} v14 --new "
                "--sandbox danger-full-access "
                "--mode implementation --approval full-access "
                f"2>&1 | tee {shlex.quote(output_path.as_posix())}"
            ),
            env=env,
            timeout_sec=1800,
        )


class CodingKidPreflightAgent(CodingKidAgent):
    """Exercise the real installation and API path without model inference."""

    @staticmethod
    def name() -> str:
        return "coding-kid-preflight"

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        api_key = self._get_env("CODING_KID_BENCH_API_KEY")
        base_url = self._get_env("CODING_KID_BENCH_BASE_URL")
        if not api_key or not base_url:
            raise ValueError(
                "CODING_KID_BENCH_API_KEY and CODING_KID_BENCH_BASE_URL are required"
            )
        probe = (
            "import json, os, urllib.request; "
            "url=os.environ['CODING_KID_BENCH_BASE_URL'].rstrip('/')+'/models'; "
            "req=urllib.request.Request(url, headers={'Authorization': "
            "'Bearer '+os.environ['CODING_KID_BENCH_API_KEY']}); "
            "payload=json.load(urllib.request.urlopen(req, timeout=30)); "
            "ids=[str(item.get('id', '')) for item in payload.get('data', [])]; "
            "assert any('luna' in model_id.lower() for model_id in ids), ids; "
            "print('api-models-luna-ok')"
        )
        executable = self._REMOTE_VENV / "bin/coding-kid"
        python = self._REMOTE_VENV / "bin/python"
        await self.exec_as_agent(
            environment,
            command=(
                f"{shlex.quote(executable.as_posix())} --list-versions >/dev/null && "
                f"{shlex.quote(python.as_posix())} -c {shlex.quote(probe)}"
            ),
            env={
                "CODING_KID_BENCH_API_KEY": api_key,
                "CODING_KID_BENCH_BASE_URL": base_url,
            },
            timeout_sec=300,
        )
