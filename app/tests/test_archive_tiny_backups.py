from app.ops.archive_tiny_backups import archive_tiny_backups, find_tiny_backups


def test_find_tiny_backups_returns_only_small_sql_gz_files(tmp_path):
    tiny = tmp_path / "tiny.sql.gz"
    healthy = tmp_path / "healthy.sql.gz"
    other = tmp_path / "tiny.txt"
    tiny.write_bytes(b"x")
    healthy.write_bytes(b"x" * 20)
    other.write_bytes(b"x")

    result = find_tiny_backups(tmp_path, min_size_bytes=10)

    assert result == [tiny]


def test_archive_tiny_backups_dry_run_does_not_move_files(tmp_path):
    tiny = tmp_path / "tiny.sql.gz"
    tiny.write_bytes(b"x")

    report = archive_tiny_backups(tmp_path, min_size_bytes=10)

    assert report["mode"] == "dry-run"
    assert report["count"] == 1
    assert report["backups"][0]["status"] == "would_archive"
    assert tiny.exists()
    assert not (tmp_path / "archive" / "tiny.sql.gz").exists()


def test_archive_tiny_backups_apply_moves_files(tmp_path):
    tiny = tmp_path / "tiny.sql.gz"
    tiny.write_bytes(b"x")

    report = archive_tiny_backups(tmp_path, min_size_bytes=10, apply=True)

    archived = tmp_path / "archive" / "tiny.sql.gz"
    assert report["mode"] == "apply"
    assert report["count"] == 1
    assert report["backups"][0]["status"] == "archived"
    assert not tiny.exists()
    assert archived.exists()


def test_archive_tiny_backups_accepts_custom_archive_dir(tmp_path):
    tiny = tmp_path / "tiny.sql.gz"
    archive_dir = tmp_path / "custom"
    tiny.write_bytes(b"x")

    report = archive_tiny_backups(
        tmp_path,
        archive_dir=archive_dir,
        min_size_bytes=10,
        apply=True,
    )

    assert report["archive_dir"] == str(archive_dir)
    assert (archive_dir / "tiny.sql.gz").exists()
