"""Discover bounded Skill metadata and load complete instructions on demand."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from coding_kid.capability_config import coding_kid_home
from coding_kid.context import SessionContext, directories_from_root
from coding_kid.context_manager import estimate_tokens
from coding_kid.plugins import Plugin

SKILL_FILENAME = "SKILL.md"
MAX_SKILL_BYTES = 48 * 1024
MAX_SKILL_NAME = 64
MAX_QUALIFIED_NAME = 128
MAX_DESCRIPTION = 1024
MAX_SKILLS_PER_TURN = 8
DEFAULT_METADATA_CHAR_BUDGET = 8_000
METADATA_WINDOW_PERCENT = 2
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MENTION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_$])\$([A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)?)"
)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    root: Path
    source: str
    allow_implicit: bool = True
    plugin_name: str | None = None


@dataclass(frozen=True)
class SkillCatalog:
    skills: tuple[Skill, ...]
    warnings: tuple[str, ...] = ()

    def by_name(self) -> dict[str, Skill]:
        return {skill.name: skill for skill in self.skills}

    def render(self, context_window: int | None) -> str:
        """Render bounded model-visible metadata, never Skill bodies."""
        if not self.skills:
            return ""
        header = (
            "Available Skills (metadata only):\n"
            "Use the skill tool before acting when a matching Skill applies. "
            "A Skill marked explicit-only may be loaded only through a user $mention."
        )
        lines: list[str] = []
        omitted = 0
        token_budget = (
            max(1, context_window * METADATA_WINDOW_PERCENT // 100)
            if context_window
            else None
        )
        for skill in sorted(self.skills, key=lambda item: item.name):
            suffix = " [explicit-only]" if not skill.allow_implicit else ""
            line = f"- {skill.name}: {skill.description} (source: {skill.path}){suffix}"
            candidate = "\n".join([header, *lines, line])
            within_budget = (
                estimate_tokens(candidate) <= token_budget
                if token_budget is not None
                else len(candidate) <= DEFAULT_METADATA_CHAR_BUDGET
            )
            if within_budget:
                lines.append(line)
            else:
                omitted += 1
        if omitted:
            lines.append(
                f"- ... {omitted} additional Skill(s) omitted by the metadata budget."
            )
        return "\n".join([header, *lines])


@dataclass
class SkillTurnState:
    catalog: SkillCatalog
    loaded: set[str] = field(default_factory=set)

    def load(self, name: str, *, explicit: bool = False) -> str:
        """Load one complete Skill body once for this turn."""
        skill = self.catalog.by_name().get(name)
        if skill is None:
            return f"ERROR: Unknown Skill: {name}"
        if not explicit and not skill.allow_implicit:
            return (
                f"ERROR: Skill {name} is explicit-only; the user must mention ${name}"
            )
        if name in self.loaded:
            return f"Skill {name} was already loaded earlier in this turn."
        if len(self.loaded) >= MAX_SKILLS_PER_TURN:
            return f"ERROR: At most {MAX_SKILLS_PER_TURN} different Skills may load per turn"
        try:
            _, body = _read_skill_file(skill.path)
        except (OSError, ValueError) as error:
            return f"ERROR: Could not load Skill {name}: {error}"
        self.loaded.add(name)
        return (
            f"Skill: {skill.name}\n"
            f"Source: {skill.path}\n"
            f"Base directory: {skill.root}\n\n{body}"
        )


def discover_skills(
    context: SessionContext,
    *,
    home: Path | None = None,
    plugins: tuple[Plugin, ...] = (),
) -> SkillCatalog:
    """Discover standalone and Plugin Skills with deterministic precedence."""
    warnings: list[str] = []
    selected: dict[str, Skill] = {}
    user_root = (home or coding_kid_home()) / "skills"
    _load_root(user_root, "user", selected, warnings)
    for directory in directories_from_root(context.project_root, context.cwd):
        _load_root(directory / ".coding-kid" / "skills", "project", selected, warnings)

    for plugin in plugins:
        for root in plugin.skill_roots:
            _load_root(
                root,
                f"plugin:{plugin.name}",
                selected,
                warnings,
                namespace=plugin.name,
                plugin_root=plugin.root,
            )
    return SkillCatalog(
        tuple(sorted(selected.values(), key=lambda item: item.name)),
        tuple(warnings),
    )


def explicit_skill_names(text: str, catalog: SkillCatalog) -> tuple[str, ...]:
    """Return unique, ordered valid Skill mentions from user text."""
    available = catalog.by_name()
    names: list[str] = []
    for match in MENTION_PATTERN.finditer(text):
        name = match.group(1)
        if name in available and name not in names:
            names.append(name)
    return tuple(names)


def _load_root(
    root: Path,
    source: str,
    selected: dict[str, Skill],
    warnings: list[str],
    *,
    namespace: str | None = None,
    plugin_root: Path | None = None,
) -> None:
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except FileNotFoundError:
        return
    except OSError as error:
        warnings.append(f"Could not inspect Skill root {root}: {error}")
        return
    for entry in entries:
        skill_path = entry / SKILL_FILENAME
        try:
            resolved_path = skill_path.resolve(strict=True)
            if not resolved_path.is_file():
                continue
            if plugin_root is not None:
                resolved_path.relative_to(plugin_root)
            metadata, _ = _read_skill_file(resolved_path)
            base_name = metadata["name"]
            name = f"{namespace}:{base_name}" if namespace else base_name
            if len(name) > MAX_QUALIFIED_NAME:
                raise ValueError("qualified Skill name is too long")
            selected[name] = Skill(
                name,
                metadata["description"],
                resolved_path,
                resolved_path.parent,
                source,
                metadata["allow_implicit"],
                namespace,
            )
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            warnings.append(f"Skill {skill_path} was skipped: {error}")


def _read_skill_file(path: Path) -> tuple[dict[str, object], str]:
    data = path.read_bytes()
    if len(data) > MAX_SKILL_BYTES:
        raise ValueError(f"SKILL.md exceeds {MAX_SKILL_BYTES} bytes")
    text = (
        data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    )
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must begin with YAML frontmatter")
    try:
        end = next(
            index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"
        )
    except StopIteration:
        raise ValueError("SKILL.md frontmatter has no closing delimiter")
    try:
        raw = yaml.safe_load("".join(lines[1:end]))
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML frontmatter: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("SKILL.md frontmatter must be an object")
    unknown = sorted(set(raw) - {"name", "description", "allow_implicit"})
    if unknown:
        raise ValueError(f"unknown frontmatter field(s): {', '.join(unknown)}")
    name = raw.get("name", path.parent.name)
    description = raw.get("description")
    allow_implicit = raw.get("allow_implicit", True)
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ValueError("Skill name must match [A-Za-z0-9_-]{1,64}")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Skill description is required")
    description = " ".join(description.split())
    if len(description) > MAX_DESCRIPTION:
        raise ValueError(f"Skill description exceeds {MAX_DESCRIPTION} characters")
    if not isinstance(allow_implicit, bool):
        raise ValueError("allow_implicit must be boolean")
    body = "".join(lines[end + 1 :]).lstrip("\n")
    return {
        "name": name,
        "description": description,
        "allow_implicit": allow_implicit,
    }, body
