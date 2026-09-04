from __future__ import annotations

import subprocess
from pathlib import Path

from voltran.workspace import IsolatedGitWorkspace


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True, text=True)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@voltran.invalid")
    _git(repo, "config", "user.name", "VOLTRAN Tests")
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_dirty_workspace_preserves_review_patch_without_touching_source(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    workspace = IsolatedGitWorkspace(repo, "test-run")

    (workspace.working_directory / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (workspace.working_directory / "new.txt").write_text("new\n", encoding="utf-8")
    outcome = workspace.finish(["pytest: passed"])

    assert outcome.changed is True
    assert outcome.worktree.exists()
    assert outcome.patch_file is not None
    patch = outcome.patch_file.read_text(encoding="utf-8")
    assert "changed" in patch
    assert "new.txt" in patch
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "original\n"
    assert not (repo / "new.txt").exists()
    assert (outcome.patch_file.parent / "verification.txt").read_text() == "pytest: passed"


def test_clean_workspace_is_removed(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    workspace = IsolatedGitWorkspace(repo, "clean-run")

    outcome = workspace.finish([])

    assert outcome.changed is False
    assert outcome.cleanup_error is None
    assert not outcome.worktree.exists()
