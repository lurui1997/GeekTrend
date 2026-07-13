from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import Any, Sequence

import pytest

from geektrend.model import CHINA_TIME, Contributor, Repository, Snapshot, ValidationError


def contributor(
    username: str = "octocat", url: str = "https://github.com/octocat"
) -> Contributor:
    return Contributor(username=username, url=url)


def repository(
    repository_name: str = "octo/demo",
    url: str = "https://github.com/octo/demo",
    contributors: Sequence[Contributor] = (),
    ai_agent_contributors: Sequence[str] = (),
    uses_ai_agent: bool = False,
    origin_country: str = "unknown",
    origin_confidence: str = "unknown",
    origin_evidence: Sequence[str] = (),
) -> Repository:
    return Repository(
        repository_name=repository_name,
        url=url,
        contributors=contributors,
        description=None,
        primary_language=None,
        ai_agent_contributors=ai_agent_contributors,
        uses_ai_agent=uses_ai_agent,
        origin_country=origin_country,
        origin_confidence=origin_confidence,
        origin_evidence=origin_evidence,
    )


def snapshot(
    *,
    fetched_at: datetime = datetime(2026, 7, 13, 10, tzinfo=CHINA_TIME),
    source_url: str = "https://github.com/trending/",
    repositories: Sequence[Repository] = (repository(),),
) -> Snapshot:
    return Snapshot(
        fetched_at=fetched_at,
        source_url=source_url,
        repositories=repositories,
    )


def test_valid_snapshot_serializes_to_exact_schema() -> None:
    record = Snapshot(
        fetched_at=datetime(2026, 7, 13, 10, 0, 0, 999999, tzinfo=CHINA_TIME),
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
                ai_agent_contributors=("claude",),
                uses_ai_agent=True,
                origin_country="United States",
                origin_confidence="high",
                origin_evidence=("octocat: location=New York",),
            ),
        ),
    )

    serialized = record.to_dict()

    assert list(serialized) == [
        "fetched_at",
        "source_url",
        "repository_count",
        "ai_agent_project_count",
        "ai_agent_project_ratio",
        "repositories",
    ]
    assert list(serialized["repositories"][0]) == [
        "repository_name",
        "url",
        "contributors",
        "description",
        "primary_language",
        "ai_agent_contributors",
        "uses_ai_agent",
        "origin_country",
        "origin_confidence",
        "origin_evidence",
    ]
    assert list(serialized["repositories"][0]["contributors"][0]) == [
        "username",
        "url",
    ]
    assert serialized == {
        "fetched_at": "2026-07-13T10:00:00+08:00",
        "source_url": "https://github.com/trending/",
        "repository_count": 1,
        "ai_agent_project_count": 1,
        "ai_agent_project_ratio": 1.0,
        "repositories": [
            {
                "repository_name": "octo/demo",
                "url": "https://github.com/octo/demo",
                "contributors": [
                    {
                        "username": "octocat",
                        "url": "https://github.com/octocat",
                    }
                ],
                "description": "你好",
                "primary_language": "Python",
                "ai_agent_contributors": ["claude"],
                "uses_ai_agent": True,
                "origin_country": "United States",
                "origin_confidence": "high",
                "origin_evidence": ["octocat: location=New York"],
            }
        ],
    }


def test_records_are_frozen_slotted_and_store_nested_collections_as_tuples() -> None:
    repo = repository(contributors=[contributor()])
    record = snapshot(repositories=[repo])

    assert repo.contributors == (contributor(),)
    assert repo.ai_agent_contributors == ()
    assert repo.origin_evidence == ()
    assert record.repositories == (repo,)
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.source_url = "https://example.com"  # type: ignore[misc]


@pytest.mark.parametrize("contributors", [None, 7])
def test_repository_translates_noniterable_contributors_to_validation_error(
    contributors: Any,
) -> None:
    with pytest.raises(ValidationError, match="contributors"):
        repository(contributors=contributors)


@pytest.mark.parametrize("repositories", [None, 7])
def test_snapshot_translates_noniterable_repositories_to_validation_error(
    repositories: Any,
) -> None:
    with pytest.raises(ValidationError, match="repositories"):
        snapshot(repositories=repositories)


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"ai_agent_contributors": [None]}, "ai_agent_contributors"),
        ({"ai_agent_contributors": ["claude"], "uses_ai_agent": False}, "uses_ai_agent"),
        ({"uses_ai_agent": "yes"}, "uses_ai_agent"),
        ({"origin_country": ""}, "origin_country"),
        ({"origin_confidence": "certain"}, "origin_confidence"),
        ({"origin_evidence": [None]}, "origin_evidence"),
    ],
)
def test_repository_rejects_invalid_analysis_fields(
    kwargs: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        repository(**kwargs)


@pytest.mark.parametrize(
    ("repositories", "field"),
    [
        ((), "repositories"),
        ((repository(), repository()), "repository_name"),
    ],
)
def test_snapshot_rejects_invalid_repository_collection(
    repositories: tuple[Repository, ...], field: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        snapshot(repositories=repositories)


@pytest.mark.parametrize(
    "repository_name",
    ["owner", "owner/repo/extra", "/repo", "owner/", "own er/repo", "owner/re\tpo"],
)
def test_repository_rejects_invalid_name(repository_name: str) -> None:
    with pytest.raises(ValidationError, match="repository_name"):
        repository(repository_name=repository_name)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/other/demo",
        "https://example.com/octo/demo",
        "https://github.com/octo/demo?tab=readme",
        "https://github.com/octo/demo#readme",
    ],
)
def test_repository_rejects_noncanonical_url(url: str) -> None:
    with pytest.raises(ValidationError, match="url"):
        repository(url=url)


@pytest.mark.parametrize("delimiter", ["?", "#", "%2F", "\\"])
def test_repository_rejects_url_delimiter_in_matching_name(delimiter: str) -> None:
    repository_name = f"octo/demo{delimiter}readme"

    with pytest.raises(ValidationError, match="repository_name"):
        repository(
            repository_name=repository_name,
            url=f"https://github.com/{repository_name}",
        )


@pytest.mark.parametrize("username", ["", " ", "octo/cat", "octo cat", "octo\tcat"])
def test_contributor_rejects_invalid_username(username: str) -> None:
    with pytest.raises(ValidationError, match="username"):
        contributor(username=username)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/other",
        "https://example.com/octocat",
        "http://github.com/octocat",
        "https://github.com/octocat?tab=repositories",
        "https://github.com/octocat#profile",
    ],
)
def test_contributor_rejects_noncanonical_url(url: str) -> None:
    with pytest.raises(ValidationError, match="url"):
        contributor(url=url)


@pytest.mark.parametrize("delimiter", ["?", "#", "%2F", "\\"])
def test_contributor_rejects_url_delimiter_in_matching_username(delimiter: str) -> None:
    username = f"octocat{delimiter}profile"

    with pytest.raises(ValidationError, match="username"):
        contributor(username=username, url=f"https://github.com/{username}")


@pytest.mark.parametrize(
    "fetched_at",
    [
        datetime(2026, 7, 13, 2),
        datetime(2026, 7, 13, 2, tzinfo=timezone.utc),
    ],
)
def test_snapshot_rejects_timestamp_that_is_not_east_8(fetched_at: datetime) -> None:
    with pytest.raises(ValidationError, match="fetched_at"):
        snapshot(fetched_at=fetched_at)


def test_snapshot_rejects_noncanonical_source_url() -> None:
    with pytest.raises(ValidationError, match="source_url"):
        snapshot(source_url="https://github.com/trending")
