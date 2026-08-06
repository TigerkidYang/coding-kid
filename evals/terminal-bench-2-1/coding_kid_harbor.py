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

    async def install(self, environment: BaseEnvironment) -> None:
        wheel = self._wheel_path()
        remote_wheel = PurePosixPath("/installed-agent") / wheel.name
        await environment.upload_file(wheel, remote_wheel.as_posix())
        await self.exec_as_root(
            environment,
            command=(
                "if ! command -v python3 >/dev/null 2>&1; then "
                "if command -v apt-get >/dev/null 2>&1; then "
                "apt-get update && DEBIAN_FRONTEND=noninteractive "
                "apt-get install -y python3 python3-pip; "
                "else echo 'Python 3 is required' >&2; exit 1; fi; fi; "
                "python3 -m pip install --no-cache-dir "
                f"--index-url {shlex.quote(self._get_env('PIP_INDEX_URL') or 'https://mirrors.aliyun.com/pypi/simple/')} "
                f"{shlex.quote(remote_wheel.as_posix())}"
            ),
        )

    def get_version_command(self) -> str | None:
        return "coding-kid --list-versions | tail -n 1"

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
            "PYTHONUNBUFFERED": "1",
        }
        output_path = EnvironmentPaths.agent_dir / "coding-kid.txt"
        await self.exec_as_agent(
            environment,
            command=(
                f"printf '%s\\n' {shlex.quote(instruction)} | "
                "coding-kid v14 --new "
                "--sandbox danger-full-access "
                "--mode implementation --approval full-access "
                f"2>&1 | tee {shlex.quote(output_path.as_posix())}"
            ),
            env=env,
            timeout_sec=1800,
        )
