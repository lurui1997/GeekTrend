"""Atomic, no-overwrite persistence for immutable snapshots."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from geektrend.model import Snapshot


class WriteError(RuntimeError):
    """Raised when a snapshot cannot be written completely."""


class SnapshotExistsError(WriteError):
    """Raised when the destination snapshot already exists."""


def snapshot_relative_path(fetched_at: datetime) -> Path:
    date_path = fetched_at.strftime("%Y/%m/%d")
    timezone_suffix = fetched_at.strftime("%z")
    formatted_suffix = f"{timezone_suffix[:3]}-{timezone_suffix[3:]}"
    filename = fetched_at.strftime("%Y-%m-%dT%H-%M-%S") + f"{formatted_suffix}.json"
    return Path("data") / date_path / filename


def _serialize(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _open_temp(path: Path) -> TextIO:
    return path.open("x", encoding="utf-8", newline="\n")


def _write(file: TextIO, content: str) -> None:
    file.write(content)


def _flush(file: TextIO) -> None:
    file.flush()


def _fsync(file_descriptor: int) -> None:
    os.fsync(file_descriptor)


def _link(source: Path, destination: Path) -> None:
    os.link(source, destination)


def _unlink(path: Path) -> None:
    os.unlink(path)


def write_snapshot(snapshot: Snapshot, root: Path = Path(".")) -> Path:
    """Write *snapshot* atomically and return its repository-relative path."""
    relative_path = snapshot_relative_path(snapshot.fetched_at)
    destination = root / relative_path
    temp_path: Path | None = None
    failure: tuple[type[WriteError], str, Exception] | None = None

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        with _open_temp(temp_path) as temp_file:
            content = _serialize(snapshot.to_dict())
            _write(temp_file, content)
            _flush(temp_file)
            _fsync(temp_file.fileno())

        try:
            # A hard link is the atomic-publication equivalent of rename used here
            # because it also guarantees strict no-overwrite behavior.
            _link(temp_path, destination)
        except FileExistsError as error:
            failure = (SnapshotExistsError, "snapshot already exists", error)
        else:
            _unlink(temp_path)
            temp_path = None
    except Exception as error:
        failure = (WriteError, "failed to write snapshot", error)
    finally:
        if temp_path is not None:
            try:
                _unlink(temp_path)
            except FileNotFoundError:
                pass
            except Exception as cleanup_error:
                if failure is None:
                    failure = (WriteError, "failed to clean snapshot temporary file", cleanup_error)

    if failure is not None:
        error_type, message, cause = failure
        raise error_type(message) from cause
    return relative_path
