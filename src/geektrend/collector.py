"""Orchestrate one immutable GitHub Trending snapshot collection."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from geektrend.client import fetch_trending
from geektrend.model import SOURCE_URL, Repository, Snapshot
from geektrend.parser import parse_trending
from geektrend.writer import write_snapshot


class CollectionError(RuntimeError):
    """Raised with the pipeline stage that prevented collection."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def collect(
    root: Path,
    fetcher: Callable[[], str] = fetch_trending,
    parser: Callable[[str], Sequence[Repository]] = parse_trending,
    writer: Callable[[Snapshot, Path], Path] = write_snapshot,
    clock: Callable[[], datetime] = _utc_now,
) -> Path:
    """Fetch, parse, timestamp, and write one snapshot under *root*."""
    try:
        html = fetcher()
    except Exception as error:
        raise CollectionError("fetch stage failed") from error

    try:
        repositories = parser(html)
    except Exception as error:
        raise CollectionError("parse stage failed") from error

    try:
        fetched_at = clock().replace(microsecond=0)
    except Exception as error:
        raise CollectionError("clock stage failed") from error

    try:
        snapshot = Snapshot(
            fetched_at=fetched_at,
            source_url=SOURCE_URL,
            repositories=repositories,
        )
    except Exception as error:
        raise CollectionError("validation stage failed") from error
    try:
        return writer(snapshot, root)
    except Exception as error:
        raise CollectionError("write stage failed") from error
