"""SEC-07 için görev bazlı, incelemeli Git worktree izolasyonu."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class WorkspaceIsolationError(RuntimeError):
    """Güvenli çalışma alanı kurulamadığında yükseltilir."""


@dataclass(frozen=True)
class WorkspaceOutcome:
    worktree: Path
    base_revision: str
    changed: bool
    patch_file: Path | None
    status: str
    cleanup_error: str | None = None


class IsolatedGitWorkspace:
    """Yazma görevini detached worktree'de yürütür ve değişiklikleri uygulamaz."""

    def __init__(self, source: Path, run_id: str) -> None:
        self.source = source.expanduser().resolve()
        self.run_id = run_id
        self.repository = self._git("rev-parse", "--show-toplevel", cwd=self.source).strip()
        self.repo_path = Path(self.repository).resolve()
        try:
            self.relative_source = self.source.relative_to(self.repo_path)
        except ValueError as exc:
            raise WorkspaceIsolationError("Görev yolu Git deposunun dışında.") from exc
        self.base_revision = self._git("rev-parse", "HEAD", cwd=self.repo_path).strip()
        self.root = Path(tempfile.mkdtemp(prefix=f"voltran-{run_id}-"))
        self.worktree = self.root / "worktree"
        self.artifact_dir = self.root / "review"
        self.artifact_dir.mkdir()
        try:
            self._git(
                "worktree",
                "add",
                "--detach",
                str(self.worktree),
                self.base_revision,
                cwd=self.repo_path,
            )
        except Exception:
            shutil.rmtree(self.root, ignore_errors=True)
            raise

    @property
    def working_directory(self) -> Path:
        return self.worktree / self.relative_source

    def finish(self, test_evidence: list[str]) -> WorkspaceOutcome:
        """Diff'i kaydet; değişiklik varsa inceleme için worktree'yi koru."""

        status = self._git("status", "--porcelain", cwd=self.worktree)
        changed = bool(status.strip())
        patch_file: Path | None = None
        if changed:
            # Intent-to-add yalnızca izole index'i etkiler ve yeni dosyaları diff'e dahil eder.
            self._git("add", "-N", "--", ".", cwd=self.worktree, check=False)
            patch = self._git("diff", "--binary", "HEAD", cwd=self.worktree)
            patch_file = self.artifact_dir / "changes.patch"
            patch_file.write_text(patch, encoding="utf-8")
            (self.artifact_dir / "verification.txt").write_text(
                (
                    "\n".join(test_evidence)
                    if test_evidence
                    else "Sağlayıcı test kanıtı bildirmedi.\n"
                ),
                encoding="utf-8",
            )
            return WorkspaceOutcome(
                worktree=self.worktree,
                base_revision=self.base_revision,
                changed=True,
                patch_file=patch_file,
                status=status,
            )

        cleanup_error: str | None = None
        try:
            self._git("worktree", "remove", str(self.worktree), cwd=self.repo_path)
            shutil.rmtree(self.root)
        except WorkspaceIsolationError as exc:
            cleanup_error = str(exc)
        return WorkspaceOutcome(
            worktree=self.worktree,
            base_revision=self.base_revision,
            changed=False,
            patch_file=None,
            status=status,
            cleanup_error=cleanup_error,
        )

    @staticmethod
    def _git(
        *args: str,
        cwd: Path,
        check: bool = True,
    ) -> str:
        try:
            completed = subprocess.run(
                ("git", *args),
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise WorkspaceIsolationError(f"Git çalıştırılamadı: {exc}") from exc
        if check and completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "bilinmeyen hata"
            raise WorkspaceIsolationError(f"Git worktree işlemi başarısız: {detail}")
        return completed.stdout
