"""SEC-07 için görev bazlı, incelemeli Git worktree izolasyonu."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorkspaceIsolationError(RuntimeError):
    """Güvenli çalışma alanı kurulamadığında yükseltilir."""


def _git_output(*args: str, cwd: Path, check: bool = True) -> str:
    try:
        completed = subprocess.run(
            ("git", *args), cwd=cwd, text=True, capture_output=True, check=False
        )
    except OSError as exc:
        raise WorkspaceIsolationError(f"Git çalıştırılamadı: {exc}") from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "bilinmeyen hata"
        raise WorkspaceIsolationError(detail)
    return completed.stdout


def review_root(repo_path: Path) -> Path:
    """İnceleme worktree'lerinin tutulduğu dizin (`.git` altında)."""

    common = _git_output("rev-parse", "--git-common-dir", cwd=repo_path).strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (repo_path / common_path).resolve()
    return common_path / "voltran" / "worktrees"


def list_review_worktrees(start: Path | None = None) -> list[ReviewWorktree]:
    """Bu depoda inceleme için korunmuş worktree'leri listeler."""

    cwd = (start or Path.cwd()).expanduser().resolve()
    repo_path = Path(_git_output("rev-parse", "--show-toplevel", cwd=cwd).strip()).resolve()
    root = review_root(repo_path)
    if not root.is_dir():
        return []
    found: list[ReviewWorktree] = []
    for entry in sorted(root.iterdir()):
        worktree = entry / "worktree"
        if not worktree.is_dir():
            continue
        patch = entry / "review" / "changes.patch"
        found.append(
            ReviewWorktree(
                run_id=entry.name,
                worktree=worktree,
                patch_file=patch if patch.is_file() else None,
            )
        )
    return found


def prune_review_worktrees(start: Path | None = None) -> int:
    """Korunmuş inceleme worktree'lerini kaldırır ve Git kayıtlarını temizler."""

    cwd = (start or Path.cwd()).expanduser().resolve()
    repo_path = Path(_git_output("rev-parse", "--show-toplevel", cwd=cwd).strip()).resolve()
    removed = 0
    for review in list_review_worktrees(repo_path):
        _git_output(
            "worktree", "remove", "--force", str(review.worktree), cwd=repo_path, check=False
        )
        shutil.rmtree(review.worktree.parent, ignore_errors=True)
        removed += 1
    # Dizinleri elle silinmiş worktree kayıtlarını da düşür.
    _git_output("worktree", "prune", cwd=repo_path, check=False)
    return removed


@dataclass(frozen=True)
class WorkspaceOutcome:
    worktree: Path
    base_revision: str
    changed: bool
    patch_file: Path | None
    status: str
    cleanup_error: str | None = None


@dataclass(frozen=True)
class ReviewWorktree:
    """İnceleme için korunmuş bir worktree kaydı."""

    run_id: str
    worktree: Path
    patch_file: Path | None


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
        # Kullanıcının HEAD ile diskteki hâli arasındaki fark. Worktree HEAD'den
        # açıldığı için bu değişiklikler göreve girmez; sessizce yok saymak yerine
        # çağırana bildirilir.
        self.dirty_files: tuple[str, ...] = tuple(
            line[3:].strip()
            for line in self._git("status", "--porcelain", cwd=self.repo_path).splitlines()
            if line.strip()
        )
        # Worktree'yi `.git` altında tut: çalışma ağacını kirletmez, `/tmp` gibi
        # yeniden başlatmada silinmez ve depoyla birlikte taşınır.
        self.root = review_root(self.repo_path) / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.worktree = self.root / "worktree"
        self.artifact_dir = self.root / "review"
        self.artifact_dir.mkdir(exist_ok=True)
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

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_files)

    def dirty_warning(self) -> str | None:
        """Commit edilmemiş değişiklikler varsa kullanıcıya gösterilecek uyarı."""

        if not self.dirty_files:
            return None
        preview = ", ".join(self.dirty_files[:5])
        if len(self.dirty_files) > 5:
            preview = f"{preview} (+{len(self.dirty_files) - 5} dosya daha)"
        return (
            f"Çalışma ağacında commit edilmemiş {len(self.dirty_files)} değişiklik var "
            f"({preview}). Model HEAD ({self.base_revision[:8]}) sürümünü gördü ve düzenledi; "
            "bu değişiklikler göreve dâhil edilmedi. Modelin güncel kodu görmesi için "
            "önce commit veya stash yapın."
        )

    def translate(self, path: Path) -> Path | None:
        """Depo içindeki bir yolu izole worktree'deki karşılığına çevirir.

        Bağlam dosyası bu yolla okunur; aksi hâlde model, düzenlediğinden farklı
        bir sürüme bakarak akıl yürütür.
        """

        try:
            relative = path.expanduser().resolve().relative_to(self.repo_path)
        except ValueError:
            return None
        candidate = self.worktree / relative
        return candidate if candidate.is_file() else None

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
