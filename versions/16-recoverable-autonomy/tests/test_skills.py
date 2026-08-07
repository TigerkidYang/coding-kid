from __future__ import annotations

from pathlib import Path

from coding_kid.context import SessionContext
from coding_kid.plugins import Plugin
from coding_kid.skills import (
    MAX_SKILL_BYTES,
    SkillTurnState,
    discover_skills,
    explicit_skill_names,
)


def make_context(root: Path, cwd: Path) -> SessionContext:
    return SessionContext(
        cwd=cwd,
        operating_system="test",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=root,
        project_instructions=(),
    )


def write_skill(
    root: Path,
    directory: str,
    description: str,
    *,
    name: str | None = None,
    allow_implicit: bool = True,
    body: str = "Follow these instructions.",
) -> Path:
    path = root / directory / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    name_line = "" if name is None else f"name: {name}\n"
    path.write_text(
        "---\n"
        f"{name_line}description: {description}\n"
        f"allow_implicit: {'true' if allow_implicit else 'false'}\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def test_project_skill_precedence_is_nearest_then_user(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    cwd = project / "src"
    cwd.mkdir(parents=True)
    write_skill(home / "skills", "review", "user")
    write_skill(project / ".coding-kid" / "skills", "review", "root")
    nearest = write_skill(cwd / ".coding-kid" / "skills", "review", "nearest")

    catalog = discover_skills(make_context(project, cwd), home=home)

    skill = catalog.by_name()["review"]
    assert skill.description == "nearest"
    assert skill.path == nearest.resolve()


def test_plugin_skills_are_namespaced(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    plugin_root = tmp_path / "plugin"
    skill_root = plugin_root / "skills"
    skill_path = write_skill(skill_root, "review", "plugin review")
    plugin = Plugin("github", "1", "", plugin_root, (skill_root,), None)

    catalog = discover_skills(
        make_context(project, project), home=tmp_path / "home", plugins=(plugin,)
    )

    assert catalog.by_name()["github:review"].path == skill_path.resolve()


def test_explicit_mentions_are_ordered_unique_and_load_full_body(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    write_skill(
        project / ".coding-kid" / "skills",
        "deploy",
        "deploy safely",
        allow_implicit=False,
        body="STEP ONE\nSTEP TWO",
    )
    catalog = discover_skills(make_context(project, project), home=tmp_path / "home")

    assert explicit_skill_names("use $deploy then $deploy", catalog) == ("deploy",)
    turn = SkillTurnState(catalog)
    assert "explicit-only" in turn.load("deploy")
    loaded = turn.load("deploy", explicit=True)
    assert "STEP ONE\nSTEP TWO" in loaded
    assert "Base directory:" in loaded
    assert "already loaded" in turn.load("deploy", explicit=True)


def test_invalid_and_oversized_skills_are_warnings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    skill_root = project / ".coding-kid" / "skills"
    project.mkdir()
    invalid = skill_root / "invalid" / "SKILL.md"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("no frontmatter", encoding="utf-8")
    oversized = skill_root / "large" / "SKILL.md"
    oversized.parent.mkdir(parents=True)
    oversized.write_bytes(b"x" * (MAX_SKILL_BYTES + 1))

    catalog = discover_skills(make_context(project, project), home=tmp_path / "home")

    assert catalog.skills == ()
    assert len(catalog.warnings) == 2


def test_metadata_render_is_bounded(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    root = project / ".coding-kid" / "skills"
    for index in range(20):
        write_skill(root, f"skill-{index}", "x" * 400)
    catalog = discover_skills(make_context(project, project), home=tmp_path / "home")

    rendered = catalog.render(16_384)

    assert "additional Skill(s) omitted" in rendered
    assert len(rendered) < 20 * 500
