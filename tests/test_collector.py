from datetime import datetime, timezone
from pathlib import Path

import pytest

from geektrend.collector import CollectionError, collect
from geektrend.model import CHINA_TIME, Repository


def repository() -> Repository:
    return Repository(
        repository_name="octo/demo",
        url="https://github.com/octo/demo",
        contributors=(),
        description=None,
        primary_language="Python",
    )


def test_collect_runs_pipeline_once_and_writes_second_precision_snapshot(tmp_path: Path) -> None:
    calls: list[object] = []
    repositories = (repository(),)
    instant = datetime(2026, 7, 13, 10, 3, 4, 987654, tzinfo=CHINA_TIME)
    expected_path = Path("data/2026/07/13/snapshot.json")

    def fetcher() -> str:
        calls.append("fetch")
        return "<html>trending</html>"

    def parser(html: str) -> tuple[Repository, ...]:
        calls.append(("parse", html))
        return repositories

    def analyzer(items: object) -> tuple[Repository, ...]:
        calls.append(("analyze", items))
        return repositories

    def clock() -> datetime:
        calls.append("clock")
        return instant

    def writer(snapshot: object, root: Path) -> Path:
        calls.append(("write", snapshot, root))
        return expected_path

    result = collect(tmp_path, fetcher, parser, writer, clock, analyzer)

    assert result == expected_path
    assert [call if isinstance(call, str) else call[0] for call in calls] == [
        "fetch", "parse", "analyze", "clock", "write"
    ]
    snapshot = calls[-1][1]
    assert snapshot.fetched_at == instant.replace(microsecond=0)
    assert snapshot.source_url == "https://github.com/trending/"
    assert snapshot.repositories == repositories
    assert calls[-1][2] == tmp_path


@pytest.mark.parametrize(
    ("failing_stage", "expected_calls"),
    [("fetch", ["fetch"]), ("parse", ["fetch", "parse"]), ("clock", ["fetch", "parse", "analyze", "clock"]),
     ("write", ["fetch", "parse", "analyze", "clock", "write"])],
)
def test_collect_stops_after_failure(
    tmp_path: Path, failing_stage: str, expected_calls: list[str]
) -> None:
    calls: list[str] = []
    cause = RuntimeError("boom")

    def step(name: str, value: object) -> object:
        calls.append(name)
        if name == failing_stage:
            raise cause
        return value

    with pytest.raises(CollectionError) as caught:
        collect(
            tmp_path,
            lambda: step("fetch", "html"),
            lambda html: step("parse", (repository(),)),
            lambda snapshot, root: step("write", Path("data/snapshot.json")),
            lambda: step("clock", datetime(2026, 7, 13, tzinfo=CHINA_TIME)),
            lambda repositories: step("analyze", repositories),
        )

    assert calls == expected_calls
    assert caught.value.__cause__ is cause
    assert str(caught.value) == f"{failing_stage} stage failed"
    assert list(tmp_path.rglob("*")) == []


def test_collect_falls_back_when_analysis_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def analyzer(repositories: object) -> object:
        calls.append("analyze")
        raise RuntimeError("GitHub API unavailable")

    def writer(snapshot: object, root: Path) -> Path:
        calls.append("write")
        assert snapshot.repositories[0].origin_country == "unknown"
        assert snapshot.repositories[0].origin_evidence == ("Contributor analysis failed",)
        return Path("data/snapshot.json")

    result = collect(
        tmp_path,
        lambda: "html",
        lambda html: (repository(),),
        writer,
        lambda: datetime(2026, 7, 13, tzinfo=CHINA_TIME),
        analyzer,
    )

    assert result == Path("data/snapshot.json")
    assert calls == ["analyze", "write"]


def test_collect_reports_snapshot_validation_before_writer(tmp_path: Path) -> None:
    writer_called = False

    def writer(snapshot: object, root: Path) -> Path:
        nonlocal writer_called
        writer_called = True
        return Path("data/snapshot.json")

    with pytest.raises(CollectionError) as caught:
        collect(
            tmp_path,
            lambda: "html",
            lambda html: (),
            writer,
            lambda: datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

    assert str(caught.value) == "validation stage failed"
    assert caught.value.__cause__ is not None
    assert writer_called is False
