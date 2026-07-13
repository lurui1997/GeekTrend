"""Immutable, validated records for a GitHub Trending snapshot."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence, TypeVar


SOURCE_URL = "https://github.com/trending/"
CHINA_TIME = timezone(timedelta(hours=8))
Record = TypeVar("Record")


class ValidationError(ValueError):
    """Raised when a snapshot record violates the domain contract."""


def _has_whitespace(value: str) -> bool:
    return any(character.isspace() for character in value)


def _has_url_syntax(value: str) -> bool:
    return any(character in value for character in "?#%\\")


def _as_tuple(value: Sequence[Record], field_name: str) -> tuple[Record, ...]:
    try:
        return tuple(value)
    except TypeError as error:
        raise ValidationError(f"{field_name} must be a sequence") from error


@dataclass(frozen=True, slots=True)
class Contributor:
    username: str
    url: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.username, str)
            or not self.username
            or "/" in self.username
            or _has_whitespace(self.username)
            or _has_url_syntax(self.username)
        ):
            raise ValidationError("username must be one canonical non-empty URL path segment")
        if self.url != f"https://github.com/{self.username}":
            raise ValidationError("url must match the contributor username")

    def to_dict(self) -> dict[str, str]:
        return {"username": self.username, "url": self.url}


@dataclass(frozen=True, slots=True)
class Repository:
    repository_name: str
    url: str
    contributors: Sequence[Contributor]
    description: str | None
    primary_language: str | None
    ai_agent_contributors: Sequence[str] = ()
    uses_ai_agent: bool = False
    origin_country: str = "unknown"
    origin_confidence: str = "unknown"
    origin_evidence: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.repository_name, str):
            raise ValidationError("repository_name must be a string")
        segments = self.repository_name.split("/")
        if (
            len(segments) != 2
            or not all(segments)
            or any(_has_whitespace(segment) for segment in segments)
            or any(_has_url_syntax(segment) for segment in segments)
        ):
            raise ValidationError(
                "repository_name must have exactly two canonical non-empty URL path segments"
            )
        if self.url != f"https://github.com/{self.repository_name}":
            raise ValidationError("url must match the repository_name")
        if self.description is not None and not isinstance(self.description, str):
            raise ValidationError("description must be a string or None")
        if self.primary_language is not None and not isinstance(
            self.primary_language, str
        ):
            raise ValidationError("primary_language must be a string or None")

        object.__setattr__(
            self, "contributors", _as_tuple(self.contributors, "contributors")
        )
        if not all(isinstance(item, Contributor) for item in self.contributors):
            raise ValidationError("contributors must contain Contributor records")
        object.__setattr__(
            self,
            "ai_agent_contributors",
            _as_tuple(self.ai_agent_contributors, "ai_agent_contributors"),
        )
        if not all(isinstance(item, str) and item for item in self.ai_agent_contributors):
            raise ValidationError("ai_agent_contributors must contain non-empty strings")
        if not isinstance(self.uses_ai_agent, bool):
            raise ValidationError("uses_ai_agent must be a boolean")
        if self.uses_ai_agent != bool(self.ai_agent_contributors):
            raise ValidationError("uses_ai_agent must match ai_agent_contributors")
        if not isinstance(self.origin_country, str) or not self.origin_country:
            raise ValidationError("origin_country must be a non-empty string")
        if self.origin_confidence not in {"high", "medium", "low", "unknown"}:
            raise ValidationError("origin_confidence must be high, medium, low, or unknown")
        object.__setattr__(
            self, "origin_evidence", _as_tuple(self.origin_evidence, "origin_evidence")
        )
        if not all(isinstance(item, str) and item for item in self.origin_evidence):
            raise ValidationError("origin_evidence must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_name": self.repository_name,
            "url": self.url,
            "contributors": [item.to_dict() for item in self.contributors],
            "description": self.description,
            "primary_language": self.primary_language,
            "ai_agent_contributors": list(self.ai_agent_contributors),
            "uses_ai_agent": self.uses_ai_agent,
            "origin_country": self.origin_country,
            "origin_confidence": self.origin_confidence,
            "origin_evidence": list(self.origin_evidence),
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    fetched_at: datetime
    source_url: str
    repositories: Sequence[Repository]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fetched_at, datetime)
            or self.fetched_at.utcoffset() != CHINA_TIME.utcoffset(None)
        ):
            raise ValidationError("fetched_at must be an East-8-aware datetime")
        if self.source_url != SOURCE_URL:
            raise ValidationError(f"source_url must be exactly {SOURCE_URL}")

        object.__setattr__(
            self, "repositories", _as_tuple(self.repositories, "repositories")
        )
        if not self.repositories:
            raise ValidationError("repositories must contain at least one repository")
        if not all(isinstance(item, Repository) for item in self.repositories):
            raise ValidationError("repositories must contain Repository records")

        names = [item.repository_name for item in self.repositories]
        if len(names) != len(set(names)):
            raise ValidationError("repository_name values must be unique")

    def to_dict(self) -> dict[str, Any]:
        fetched_at = self.fetched_at.replace(microsecond=0).isoformat()
        return {
            "fetched_at": fetched_at,
            "source_url": self.source_url,
            "repository_count": len(self.repositories),
            "ai_agent_project_count": sum(
                1 for repository in self.repositories if repository.uses_ai_agent
            ),
            "ai_agent_project_ratio": round(
                sum(1 for repository in self.repositories if repository.uses_ai_agent)
                / len(self.repositories),
                4,
            ),
            "repositories": [item.to_dict() for item in self.repositories],
        }
