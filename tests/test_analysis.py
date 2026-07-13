from __future__ import annotations

import requests

from geektrend.analysis import GitHubProfileClient, Profile, analyze_repositories
from geektrend.model import Contributor, Repository


def repository() -> Repository:
    return Repository(
        repository_name="octo/demo",
        url="https://github.com/octo/demo",
        contributors=(
            Contributor("octo", "https://github.com/octo"),
            Contributor("claude", "https://github.com/claude"),
            Contributor("dependabot", "https://github.com/dependabot"),
        ),
        description=None,
        primary_language="Python",
    )


class FakeClient:
    def __init__(self, profiles: dict[str, Profile | None]) -> None:
        self.profiles = profiles
        self.calls: list[str] = []

    def profile(self, username: str) -> Profile | None:
        self.calls.append(username)
        return self.profiles.get(username)


def test_analyzes_ai_agents_and_owner_origin() -> None:
    client = FakeClient(
        {
            "octo": Profile(
                username="octo",
                location="New York City, NY",
                company=None,
                bio=None,
            ),
            "dependabot": Profile(
                username="dependabot",
                location=None,
                company=None,
                bio=None,
            ),
        }
    )

    analyzed = analyze_repositories((repository(),), client=client)[0]

    assert analyzed.ai_agent_contributors == ("claude",)
    assert analyzed.uses_ai_agent is True
    assert analyzed.origin_country == "United States"
    assert analyzed.origin_confidence == "high"
    assert analyzed.origin_evidence == ("octo: location=New York City, NY",)
    assert "claude" not in client.calls


def test_uses_majority_human_contributor_signal_when_owner_is_unknown() -> None:
    repo = Repository(
        repository_name="org/demo",
        url="https://github.com/org/demo",
        contributors=(
            Contributor("alice", "https://github.com/alice"),
            Contributor("bob", "https://github.com/bob"),
            Contributor("copilot", "https://github.com/copilot"),
        ),
        description=None,
        primary_language=None,
    )
    client = FakeClient(
        {
            "alice": Profile("alice", "London", None, None),
            "bob": Profile("bob", None, None, "Shipping AI apps from United Kingdom"),
        }
    )

    analyzed = analyze_repositories((repo,), client=client)[0]

    assert analyzed.ai_agent_contributors == ("copilot",)
    assert analyzed.origin_country == "United Kingdom"
    assert analyzed.origin_confidence == "medium"


def test_unknown_when_profile_signals_are_unavailable() -> None:
    analyzed = analyze_repositories((repository(),), client=FakeClient({}))[0]

    assert analyzed.origin_country == "unknown"
    assert analyzed.origin_confidence == "unknown"
    assert analyzed.origin_evidence == ("No public contributor location signal found",)


class RaisingSession:
    def get(self, *args: object, **kwargs: object) -> object:
        raise requests.ConnectionError("offline")


def test_github_profile_client_returns_none_on_request_failure() -> None:
    client = GitHubProfileClient(session=RaisingSession())  # type: ignore[arg-type]

    assert client.profile("octo") is None
