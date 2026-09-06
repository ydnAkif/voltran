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


def test_worktree_lives_under_the_git_directory_not_the_working_tree(tmp_path: Path) -> None:
    """Worktree çalışma ağacını kirletmemeli ve /tmp temizliğinde kaybolmamalı."""
    repo = _repository(tmp_path)
    workspace = IsolatedGitWorkspace(repo, "run-konum")

    assert ".git" in workspace.worktree.parts
    assert workspace.worktree.is_relative_to(repo / ".git")

    status = subprocess.run(
        ("git", "status", "--porcelain"), cwd=repo, capture_output=True, text=True, check=True
    )
    assert status.stdout == ""  # kullanıcının çalışma ağacı temiz kalır


def test_translate_maps_repository_paths_into_the_worktree(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    workspace = IsolatedGitWorkspace(repo, "run-ceviri")

    translated = workspace.translate(repo / "tracked.txt")

    assert translated is not None
    assert translated == workspace.worktree / "tracked.txt"
    assert translated.read_text(encoding="utf-8") == "original\n"
    # Depo dışındaki yol çevrilemez.
    assert workspace.translate(tmp_path / "disarida.txt") is None


def test_dirty_warning_names_uncommitted_files(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    assert IsolatedGitWorkspace(repo, "run-temiz").dirty_warning() is None

    (repo / "tracked.txt").write_text("commit edilmemiş\n", encoding="utf-8")
    workspace = IsolatedGitWorkspace(repo, "run-kirli")

    warning = workspace.dirty_warning()
    assert warning is not None
    assert "tracked.txt" in warning
    assert "commit veya stash" in warning
    assert workspace.is_dirty is True
    # Model, HEAD sürümünü görür.
    translated = workspace.translate(repo / "tracked.txt")
    assert translated is not None
    assert translated.read_text(encoding="utf-8") == "original\n"


def test_review_worktrees_are_listed_and_pruned(tmp_path: Path) -> None:
    from voltran.workspace import list_review_worktrees, prune_review_worktrees

    repo = _repository(tmp_path)
    assert list_review_worktrees(repo) == []

    workspace = IsolatedGitWorkspace(repo, "run-liste")
    (workspace.worktree / "tracked.txt").write_text("değişti\n", encoding="utf-8")
    outcome = workspace.finish([])
    assert outcome.changed is True

    reviews = list_review_worktrees(repo)
    assert len(reviews) == 1
    assert reviews[0].run_id == "run-liste"
    assert reviews[0].patch_file is not None

    assert prune_review_worktrees(repo) == 1
    assert list_review_worktrees(repo) == []

    listed = subprocess.run(
        ("git", "worktree", "list"), cwd=repo, capture_output=True, text=True, check=True
    )
    assert "run-liste" not in listed.stdout
