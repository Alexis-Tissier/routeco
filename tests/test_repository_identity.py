from __future__ import annotations

from pathlib import Path


def tracked_text() -> str:
    roots = [
        Path("README.md"),
        Path("docs/development/CHATGPT_CONTEXT.md"),
        Path("site"),
        Path("scripts"),
        Path("docs"),
        Path(".github/workflows"),
    ]
    chunks: list[str] = []
    for root in roots:
        if root.is_file():
            chunks.append(root.read_text(encoding="utf-8", errors="ignore"))
            continue
        for path in root.rglob("*"):
            if path.is_file():
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_public_repository_identity_is_detour() -> None:
    content = tracked_text()
    assert "github.com/Alexis-Tissier/routeco" not in content
    assert "github.com/Alexis-Tissier/detour" in content


def test_workflows_use_main_as_canonical_branch() -> None:
    for relative in (
        ".github/workflows/pages.yml",
        ".github/workflows/tests.yml",
    ):
        content = Path(relative).read_text(encoding="utf-8")
        assert "      - main\n" in content
        assert "audit/v0.3.4-toll-engine-checkpoint" not in content
