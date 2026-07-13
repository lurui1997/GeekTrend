"""Parse GitHub Trending repository cards into validated records."""

from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from geektrend.model import Contributor, Repository, ValidationError


GITHUB_BASE_URL = "https://github.com"
REPOSITORY_CARD_SELECTOR = "article.Box-row"
REPOSITORY_LINK_SELECTOR = "h2 a"
DESCRIPTION_SELECTOR = "p.col-9"
LANGUAGE_SELECTOR = '[itemprop="programmingLanguage"]'
CONTRIBUTOR_LINK_SELECTOR = (
    'span.d-inline-block a[data-hovercard-type="user"]'
)


class ParseError(ValueError):
    """Raised when Trending markup cannot produce valid repository records."""


def _text(element: Tag) -> str:
    return " ".join(
        normalized
        for text in element.stripped_strings
        if (normalized := " ".join(text.split()))
    )


def _repository_name(link: Tag) -> str:
    parts = _text(link).split("/")
    return "/".join(part.strip() for part in parts)


def _contributor_name(link: Tag) -> str:
    image = link.find("img", alt=True)
    identity = str(image["alt"]) if image is not None else _text(link)
    return identity.removeprefix("@")


def _required_href(link: Tag) -> str:
    href = link.get("href")
    if not isinstance(href, str) or not href:
        raise ValueError("link is missing href")
    return href


def _parse_card(card: Tag) -> Repository:
    repository_link = card.select_one(REPOSITORY_LINK_SELECTOR)
    if repository_link is None:
        raise ValueError("repository link is missing")

    description = card.select_one(DESCRIPTION_SELECTOR)
    language = card.select_one(LANGUAGE_SELECTOR)
    contributors = tuple(
        Contributor(
            username=_contributor_name(link),
            url=urljoin(GITHUB_BASE_URL, _required_href(link)),
        )
        for link in card.select(CONTRIBUTOR_LINK_SELECTOR)
    )
    return Repository(
        repository_name=_repository_name(repository_link),
        url=urljoin(GITHUB_BASE_URL, _required_href(repository_link)),
        contributors=contributors,
        description=_text(description) if description is not None else None,
        primary_language=_text(language) if language is not None else None,
    )


def parse_trending(html: str) -> tuple[Repository, ...]:
    """Return every Trending card in page order, rejecting malformed pages."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(REPOSITORY_CARD_SELECTOR)
    if not cards:
        raise ParseError("no repository cards found in Trending page")

    repositories: list[Repository] = []
    seen_names: set[str] = set()
    for index, card in enumerate(cards, start=1):
        try:
            repository = _parse_card(card)
        except (ValidationError, ValueError) as error:
            raise ParseError(f"invalid repository card {index}: {error}") from error
        if repository.repository_name in seen_names:
            raise ParseError(
                f"duplicate repository in card {index}: {repository.repository_name}"
            )
        seen_names.add(repository.repository_name)
        repositories.append(repository)

    return tuple(repositories)
