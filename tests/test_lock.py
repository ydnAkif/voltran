from pathlib import Path

from voltran.lock import FileLockManager


def test_file_lock_lifecycle(tmp_path: Path) -> None:
    lock_mgr = FileLockManager(root_dir=tmp_path)
    target_file = tmp_path / "app.py"
    target_file.write_text("print('test')", encoding="utf-8")

    # 1. Başlangıçta kilit yok
    assert lock_mgr.get_holder(target_file) is None

    # 2. Ajan 1 kilit alır
    assert lock_mgr.acquire(target_file, "agent-1") is True
    assert lock_mgr.get_holder(target_file) == "agent-1"

    # 3. Aynı ajan tekrar kilit alabilir (idempotent)
    assert lock_mgr.acquire(target_file, "agent-1") is True

    # 4. Başka bir ajan aynı dosyaya kilit alamaz (çakışma engelleme)
    assert lock_mgr.acquire(target_file, "agent-2") is False
    assert lock_mgr.get_holder(target_file) == "agent-1"

    # 5. Başka ajan kilidi çözemez
    assert lock_mgr.release(target_file, "agent-2") is False
    assert lock_mgr.get_holder(target_file) == "agent-1"

    # 6. Kilit sahibi kilidi çözer
    assert lock_mgr.release(target_file, "agent-1") is True
    assert lock_mgr.get_holder(target_file) is None

    # 7. Artık Ajan 2 kilit alabilir
    assert lock_mgr.acquire(target_file, "agent-2") is True
    assert lock_mgr.get_holder(target_file) == "agent-2"

    # 8. release_all tüm kilitleri temizler
    lock_mgr.release_all()
    assert lock_mgr.get_holder(target_file) is None


def test_corrupt_lock_is_not_overwritten(tmp_path: Path) -> None:
    lock_mgr = FileLockManager(root_dir=tmp_path)
    target_file = tmp_path / "app.py"
    assert lock_mgr.acquire(target_file, "original-holder") is True
    lock_file = next(lock_mgr.lock_dir.glob("*.lock"))
    lock_file.write_text("not-json", encoding="utf-8")

    assert lock_mgr.acquire(target_file, "agent-1") is False
    assert lock_file.read_text(encoding="utf-8") == "not-json"


def test_long_target_path_uses_bounded_hash_filename(tmp_path: Path) -> None:
    target_file = tmp_path / ("deep-segment-" * 30) / "app.py"
    lock_mgr = FileLockManager(root_dir=tmp_path)

    assert lock_mgr.acquire(target_file, "agent-1") is True
    lock_file = next(lock_mgr.lock_dir.glob("*.lock"))
    assert len(lock_file.name) == 69  # 64 hex characters + '.lock'


def test_stale_lock_can_be_reclaimed(tmp_path: Path) -> None:
    target_file = tmp_path / "app.py"
    lock_mgr = FileLockManager(root_dir=tmp_path, ttl_seconds=0)
    assert lock_mgr.acquire(target_file, "crashed-run") is True

    assert lock_mgr.acquire(target_file, "new-run") is True
    assert lock_mgr.get_holder(target_file) == "new-run"


def test_force_release_removes_unknown_or_corrupt_lock(tmp_path: Path) -> None:
    target_file = tmp_path / "app.py"
    lock_mgr = FileLockManager(root_dir=tmp_path)
    assert lock_mgr.acquire(target_file, "crashed-run") is True
    next(lock_mgr.lock_dir.glob("*.lock")).write_text("corrupt", encoding="utf-8")

    assert lock_mgr.force_release(target_file) is True
    assert list(lock_mgr.lock_dir.glob("*.lock")) == []
