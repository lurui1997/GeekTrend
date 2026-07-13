"""Best-effort contributor analysis for a Trending snapshot."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import requests

from geektrend.client import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from geektrend.model import Repository


AI_AGENT_USERNAMES = frozenset({"claude", "codex", "cursor", "github-copilot", "copilot"})
GITHUB_API_URL = "https://api.github.com"


@dataclass(frozen=True, slots=True)
class Profile:
    username: str
    location: str | None
    company: str | None
    bio: str | None


LOCATION_COUNTRIES = (
    ("hong kong", "Hong Kong"),
    ("hku", "Hong Kong"),
    ("south china normal university", "China"),
    ("beijing", "China"),
    ("shanghai", "China"),
    ("bangalore", "India"),
    ("blr", "India"),
    ("istanbul", "Turkey"),
    ("netherlands", "Netherlands"),
    ("thailand", "Thailand"),
    ("hat yai", "Thailand"),
    ("japan", "Japan"),
    ("italy", "Italy"),
    ("london", "United Kingdom"),
    ("united kingdom", "United Kingdom"),
    (" uk", "United Kingdom"),
    ("paris", "France"),
    ("france", "France"),
    ("morocco", "Morocco"),
    ("dhaka", "Bangladesh"),
    ("bangladesh", "Bangladesh"),
    ("palestine", "Palestine"),
    ("new york", "United States"),
    ("nyc", "United States"),
    (" ny", "United States"),
    ("san diego", "United States"),
    ("louisville", "United States"),
    (" ky", "United States"),
    ("usa", "United States"),
    ("united states", "United States"),
)


class GitHubProfileClient:
    """Small GitHub REST client used for best-effort public profile lookups."""

    def __init__(
        self, session: requests.Session | None = None, token: str | None = None
    ) -> None:
        self._session = session if session is not None else requests.Session()
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN")

    def profile(self, username: str) -> Profile | None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = self._session.get(
                f"{GITHUB_API_URL}/users/{username}",
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (requests.RequestException, ValueError):
            return None
        return Profile(
            username=username,
            location=_optional_string(payload.get("location")),
            company=_optional_string(payload.get("company")),
            bio=_optional_string(payload.get("bio")),
        )


def analyze_repositories(
    repositories: Sequence[Repository],
    client: GitHubProfileClient | None = None,
) -> tuple[Repository, ...]:
    """Return repositories enriched with AI-agent and country-origin analysis."""
    profile_client = client if client is not None else GitHubProfileClient()
    cache: dict[str, Profile | None] = {}

    def profile(username: str) -> Profile | None:
        key = username.lower()
        if key not in cache:
            cache[key] = profile_client.profile(username)
        return cache[key]

    enriched: list[Repository] = []
    for repository in repositories:
        ai_agents = tuple(
            contributor.username
            for contributor in repository.contributors
            if _is_ai_agent(contributor.username)
        )
        humans = [
            contributor.username
            for contributor in repository.contributors
            if not _is_ai_agent(contributor.username)
        ]
        country, confidence, evidence = infer_origin(
            repository.repository_name, humans, profile
        )
        enriched.append(
            Repository(
                repository_name=repository.repository_name,
                url=repository.url,
                contributors=repository.contributors,
                description=repository.description,
                primary_language=repository.primary_language,
                ai_agent_contributors=ai_agents,
                uses_ai_agent=bool(ai_agents),
                origin_country=country,
                origin_confidence=confidence,
                origin_evidence=evidence,
            )
        )
    return tuple(enriched)


def infer_origin(
    repository_name: str,
    human_usernames: Sequence[str],
    profile_lookup: Callable[[str], Profile | None],
) -> tuple[str, str, tuple[str, ...]]:
    """Infer a repository origin from public contributor profile text."""
    owner = repository_name.split("/", maxsplit=1)[0]
    observations: list[tuple[str, str, str]] = []

    for username in human_usernames:
        profile = profile_lookup(username)
        if profile is None:
            continue
        country, evidence = _country_from_profile(profile)
        if country is not None and evidence is not None:
            observations.append((username, country, evidence))

    if not observations:
        return "unknown", "unknown", ("No public contributor location signal found",)

    owner_observation = next(
        (
            observation
            for observation in observations
            if observation[0].lower() == owner.lower()
        ),
        None,
    )
    if owner_observation is not None:
        username, country, evidence = owner_observation
        return country, "high", (f"{username}: {evidence}",)

    counts = Counter(country for _, country, _ in observations)
    country, count = counts.most_common(1)[0]
    evidence = tuple(
        f"{username}: {detail}"
        for username, observed_country, detail in observations
        if observed_country == country
    )
    if count >= 2:
        return country, "medium", evidence[:3]
    return country, "low", evidence[:1]


def _is_ai_agent(username: str) -> bool:
    return username.lower() in AI_AGENT_USERNAMES


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _country_from_profile(profile: Profile) -> tuple[str | None, str | None]:
    fields = (
        ("location", profile.location),
        ("company", profile.company),
        ("bio", profile.bio),
    )
    for field_name, value in fields:
        if not value:
            continue
        normalized = f" {value.casefold()} "
        for needle, country in LOCATION_COUNTRIES:
            if needle in normalized:
                return country, f"{field_name}={value}"
    return None, None
