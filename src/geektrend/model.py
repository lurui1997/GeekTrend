"""Immutable, validated records for a GitHub Trending snapshot."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


SOURCE_URL = "https://github.com/trending/"


class ValidationError(ValueError):
    """Raised when a snapshot record violates the domain contract."""


def _has_whitespace(value: str) -> bool:
    return any(character.isspace() for character in value)


def _has_url_syntax(value: str) -> bool:
    return any(character in value for character in "?#%\\")


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
    contributors: tuple[Contributor, ...]
    description: str | None
    primary_language: str | None

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

        object.__setattr__(self, "contributors", tuple(self.contributors))
        if not all(isinstance(item, Contributor) for item in self.contributors):
            raise ValidationError("contributors must contain Contributor records")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_name": self.repository_name,
            "url": self.url,
            "contributors": [item.to_dict() for item in self.contributors],
            "description": self.description,
            "primary_language": self.primary_language,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    fetched_at: datetime
    source_url: str
    repositories: tuple[Repository, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fetched_at, datetime) or self.fetched_at.utcoffset() != timedelta(0):
            raise ValidationError("fetched_at must be a UTC-aware datetime")
        if self.source_url != SOURCE_URL:
            raise ValidationError(f"source_url must be exactly {SOURCE_URL}")

        object.__setattr__(self, "repositories", tuple(self.repositories))
        if not self.repositories:
            raise ValidationError("repositories must contain at least one repository")
        if not all(isinstance(item, Repository) for item in self.repositories):
            raise ValidationError("repositories must contain Repository records")

        names = [item.repository_name for item in self.repositories]
        if len(names) != len(set(names)):
            raise ValidationError("repository_name values must be unique")

    def to_dict(self) -> dict[str, Any]:
        fetched_at = self.fetched_at.replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
        return {
            "fetched_at": fetched_at,
            "source_url": self.source_url,
            "repository_count": len(self.repositories),
            "repositories": [item.to_dict() for item in self.repositories],
        }
