"""Orchestrate one immutable GitHub Trending snapshot collection."""

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from geektrend.analysis import analyze_repositories
from geektrend.client import fetch_trending
from geektrend.model import CHINA_TIME, SOURCE_URL, Repository, Snapshot
from geektrend.parser import parse_trending
from geektrend.writer import write_snapshot


class CollectionError(RuntimeError):
    """Raised with the pipeline stage that prevented collection."""


def _china_time_now() -> datetime:
    return datetime.now(CHINA_TIME)


def collect(
    root: Path,
    fetcher: Callable[[], str] = fetch_trending,
    parser: Callable[[str], Sequence[Repository]] = parse_trending,
    writer: Callable[[Snapshot, Path], Path] = write_snapshot,
    clock: Callable[[], datetime] = _china_time_now,
    analyzer: Callable[[Sequence[Repository]], Sequence[Repository]] = analyze_repositories,
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
        repositories = analyzer(repositories)
    except Exception:
        repositories = _without_analysis(repositories)

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


def _without_analysis(repositories: Sequence[Repository]) -> tuple[Repository, ...]:
    return tuple(
        Repository(
            repository_name=repository.repository_name,
            url=repository.url,
            contributors=repository.contributors,
            description=repository.description,
            primary_language=repository.primary_language,
            origin_evidence=("Contributor analysis failed",),
        )
        for repository in repositories
    )
