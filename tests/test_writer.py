import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from geektrend.model import CHINA_TIME, Contributor, Repository, Snapshot
from geektrend.writer import (
    SnapshotExistsError,
    WriteError,
    snapshot_relative_path,
    write_snapshot,
)


def snapshot() -> Snapshot:
    return Snapshot(
        fetched_at=datetime(2026, 7, 13, 10, 0, 3, tzinfo=CHINA_TIME),
        source_url="https://github.com/trending/",
        repositories=(
            Repository(
                repository_name="octo/demo",
                url="https://github.com/octo/demo",
                contributors=(
                    Contributor("octocat", "https://github.com/octocat"),
                ),
                description="你好",
                primary_language="Python",
            ),
        ),
    )


def temp_artifacts(root: Path) -> list[Path]:
    return list(root.rglob("*.tmp"))


def test_snapshot_path_uses_east_8_calendar_and_second_precision() -> None:
    assert snapshot_relative_path(snapshot().fetched_at) == Path(
        "data/2026/07/13/2026-07-13T10-00-03+08-00.json"
    )


def test_writes_pretty_utf8_json_with_exactly_one_final_newline(tmp_path: Path) -> None:
    relative = write_snapshot(snapshot(), tmp_path)
    destination = tmp_path / relative
    raw = destination.read_bytes()

    assert relative == Path("data/2026/07/13/2026-07-13T10-00-03+08-00.json")
    assert raw.decode("utf-8").endswith("\n")
    assert not raw.decode("utf-8").endswith("\n\n")
    assert b"\\u4f60" not in raw
    assert json.loads(raw) == snapshot().to_dict()
    assert raw.decode() == json.dumps(snapshot().to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert temp_artifacts(tmp_path) == []


def test_refuses_to_overwrite_an_existing_snapshot(tmp_path: Path) -> None:
    destination = tmp_path / snapshot_relative_path(snapshot().fetched_at)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"competitor")

    with pytest.raises(SnapshotExistsError) as caught:
        write_snapshot(snapshot(), tmp_path)

    assert isinstance(caught.value.__cause__, FileExistsError)
    assert destination.read_bytes() == b"competitor"
    assert temp_artifacts(tmp_path) == []


@pytest.mark.parametrize("operation", ["serialize", "write", "flush", "fsync", "link"])
def test_failure_before_publication_leaves_no_destination_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    import geektrend.writer as writer

    original_unlink = writer._unlink
    cleanup_attempted = False
    error = OSError(f"{operation} failed")

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    def track_unlink(path: Path) -> None:
        nonlocal cleanup_attempted
        cleanup_attempted = True
        original_unlink(path)

    monkeypatch.setattr(writer, f"_{operation}", fail)
    monkeypatch.setattr(writer, "_unlink", track_unlink)

    with pytest.raises(WriteError) as caught:
        write_snapshot(snapshot(), tmp_path)

    assert caught.value.__cause__ is error
    assert not (tmp_path / snapshot_relative_path(snapshot().fetched_at)).exists()
    assert cleanup_attempted
    assert temp_artifacts(tmp_path) == []


def test_unlink_failure_after_link_keeps_complete_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import geektrend.writer as writer

    original_unlink = writer._unlink
    attempts = 0
    error = OSError("unlink failed")

    def fail_first_unlink(path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise error
        original_unlink(path)

    monkeypatch.setattr(writer, "_unlink", fail_first_unlink)

    with pytest.raises(WriteError) as caught:
        write_snapshot(snapshot(), tmp_path)

    destination = tmp_path / snapshot_relative_path(snapshot().fetched_at)
    assert caught.value.__cause__ is error
    assert json.loads(destination.read_text(encoding="utf-8")) == snapshot().to_dict()
    assert attempts == 2
    assert temp_artifacts(tmp_path) == []


def test_competitor_winning_immediately_before_link_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import geektrend.writer as writer

    destination = tmp_path / snapshot_relative_path(snapshot().fetched_at)
    original_link = os.link
    competitor = b'{"winner": true}\n'

    def competing_link(source: Path, target: Path) -> None:
        destination.write_bytes(competitor)
        original_link(source, target)

    monkeypatch.setattr(writer, "_link", competing_link)

    with pytest.raises(SnapshotExistsError) as caught:
        write_snapshot(snapshot(), tmp_path)

    assert isinstance(caught.value.__cause__, FileExistsError)
    assert destination.read_bytes() == competitor
    assert temp_artifacts(tmp_path) == []
