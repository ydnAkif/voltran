"""VOLTRAN Dosya Kilitleme Motoru (File Locking & Write Safety).

Çoklu ajan işbirliği sırasında aynı dosyanın iki ajan tarafından aynı anda
çakışan şekilde değiştirilmesini önler (Forge esintili sapma ve kilit denetimi).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class LockInfo:
    """Bir dosya kilidinin meta verisi."""

    file_path: str
    holder: str
    acquired_at: float


class FileLockManager:
    """Yerel disk üzerinde dosya kilitlerini yöneten hafif kilit yöneticisi."""

    DEFAULT_TTL_SECONDS: ClassVar[float] = 4 * 60 * 60

    def __init__(
        self,
        root_dir: Path | None = None,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.lock_dir = self.root_dir / ".voltran" / "locks"
        self.ttl_seconds = ttl_seconds

    def _ensure_lock_dir(self) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    def _lock_file_path(self, target_file: Path) -> Path:
        resolved = target_file.resolve()
        # Dosya sistemi ad sınırından bağımsız, deterministik bir kilit adı kullan.
        digest = sha256(str(resolved).encode("utf-8")).hexdigest()
        return self.lock_dir / f"{digest}.lock"

    def acquire(self, target_file: Path, holder: str) -> bool:
        """Belirtilen dosya için kilit alır. Kilit boşsa veya aynı tutucuya aitse True döner."""
        self._ensure_lock_dir()
        lock_path = self._lock_file_path(target_file)

        return self._acquire_once(lock_path, target_file, holder, retry_stale=True)

    def _acquire_once(
        self,
        lock_path: Path,
        target_file: Path,
        holder: str,
        *,
        retry_stale: bool,
    ) -> bool:

        payload = {
            "file_path": str(target_file.resolve()),
            "holder": holder,
            "acquired_at": time.time(),
        }
        try:
            # O_EXCL, iki süreç aynı anda kilit almaya çalıştığında yalnızca
            # birinin dosyayı oluşturabilmesini garanti eder.
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            return True
        except FileExistsError:
            try:
                data = json.loads(lock_path.read_text(encoding="utf-8"))
                if str(data.get("holder", "")) == holder:
                    return True
                acquired_at = float(data.get("acquired_at", 0.0))
                if retry_stale and time.time() - acquired_at >= self.ttl_seconds:
                    lock_path.unlink(missing_ok=True)
                    return self._acquire_once(lock_path, target_file, holder, retry_stale=False)
                return False
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                # Sahibi doğrulanamayan bir kilidi ezmek güvenli değildir.
                return False
        except OSError:
            return False

    def release(self, target_file: Path, holder: str) -> bool:
        """Belirtilen dosyanın kilidini çözer. Yalnızca kilidi elinde tutan ajan çözebilir."""
        lock_path = self._lock_file_path(target_file)
        if not lock_path.exists():
            return True

        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            if str(data.get("holder", "")) == holder:
                lock_path.unlink(missing_ok=True)
                return True
            return False
        except (json.JSONDecodeError, OSError):
            lock_path.unlink(missing_ok=True)
            return True

    def get_holder(self, target_file: Path) -> str | None:
        """Dosyanın kilit sahibini döndürür; kilit yoksa None döner."""
        lock_path = self._lock_file_path(target_file)
        if not lock_path.exists():
            return None
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            return str(data.get("holder")) if data.get("holder") else None
        except (json.JSONDecodeError, OSError):
            return None

    def has_lock(self, target_file: Path) -> bool:
        """Hedef dosya için diskte bir kilit var mı? Bozuk kilit dosyaları da sayılır."""

        return self._lock_file_path(target_file).exists()

    def force_release(self, target_file: Path) -> bool:
        """Kullanıcının açık isteğiyle hedef dosyanın kilidini kaldır."""

        lock_path = self._lock_file_path(target_file)
        try:
            lock_path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def release_all(self, holder: str | None = None) -> int:
        """Tüm kilitleri veya belirtilen ajana ait tüm kilitleri temizler."""
        if not self.lock_dir.exists():
            return 0

        released = 0
        for lock_file in self.lock_dir.glob("*.lock"):
            if holder is None:
                lock_file.unlink(missing_ok=True)
                released += 1
            else:
                try:
                    data = json.loads(lock_file.read_text(encoding="utf-8"))
                    if str(data.get("holder", "")) == holder:
                        lock_file.unlink(missing_ok=True)
                        released += 1
                except (json.JSONDecodeError, OSError):
                    lock_file.unlink(missing_ok=True)
                    released += 1
        return released

    def list_active_locks(self) -> list[LockInfo]:
        """Mevcut tüm aktif dosya kilitlerini döndürür."""
        if not self.lock_dir.exists():
            return []

        locks: list[LockInfo] = []
        for lock_file in self.lock_dir.glob("*.lock"):
            try:
                data = json.loads(lock_file.read_text(encoding="utf-8"))
                file_path = str(data.get("file_path", ""))
                holder = str(data.get("holder", ""))
                acquired_at = float(data.get("acquired_at", 0.0))
                if file_path and holder:
                    locks.append(
                        LockInfo(
                            file_path=file_path,
                            holder=holder,
                            acquired_at=acquired_at,
                        )
                    )
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return locks
