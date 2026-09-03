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
