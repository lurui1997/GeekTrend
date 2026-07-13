from pathlib import Path

import pytest

from geektrend.parser import ParseError, parse_trending


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_multiple_card_scoped_repositories() -> None:
    repositories = parse_trending((FIXTURES / "trending.html").read_text())

    assert repositories[0].repository_name == "octo/demo"
    assert repositories[0].url == "https://github.com/octo/demo"
    assert repositories[0].description == "A useful repository for testing"
    assert repositories[0].primary_language == "Python"
    assert [(item.username, item.url) for item in repositories[0].contributors] == [
        ("octocat", "https://github.com/octocat"),
        ("hubot", "https://github.com/hubot"),
    ]
    assert repositories[1].repository_name == "acme/minimal"
    assert repositories[1].url == "https://github.com/acme/minimal"
    assert repositories[1].description is None
    assert repositories[1].primary_language is None
    assert repositories[1].contributors == ()
    assert len(repositories) == 2


def test_accepts_absolute_canonical_repository_and_profile_links() -> None:
    html = """
    <article class="Box-row">
      <h2><a href="https://github.com/owner/repo">owner/repo</a></h2>
      <span class="d-inline-block">
        <a data-hovercard-type="user" href="https://github.com/alice">alice</a>
      </span>
    </article>
    """

    repository = parse_trending(html)[0]

    assert repository.url == "https://github.com/owner/repo"
    assert repository.contributors[0].url == "https://github.com/alice"


@pytest.mark.parametrize(
    ("html", "message"),
    [
        (
            '<article class="Box-row"><h2><a href="/owner/repo">owner/repo</a></h2></article>'
            '<article class="Box-row"><h2><a href="/owner/repo">owner/repo</a></h2></article>',
            "duplicate",
        ),
        (
            '<article class="Box-row"><h2><a href="/owner">owner</a></h2></article>',
            "invalid repository card",
        ),
        (
            '<article class="Box-row"><h2><a href="/owner/other">owner/repo</a></h2></article>',
            "invalid repository card",
        ),
        (
            '<article class="Box-row"><h2><a href="/owner/repo?tab=readme">owner/repo</a></h2></article>',
            "invalid repository card",
        ),
        (
            '<article class="Box-row"><h2><a>owner/repo</a></h2></article>',
            "invalid repository card",
        ),
        (
            '<article class="Box-row"><h2><a href="/owner/repo">owner/repo</a></h2>'
            '<span class="d-inline-block"><a data-hovercard-type="user" href="/bob">alice</a></span>'
            "</article>",
            "invalid repository card",
        ),
    ],
)
def test_rejects_every_malformed_card(html: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        parse_trending(html)


def test_rejects_page_without_repository_cards() -> None:
    html = (FIXTURES / "empty.html").read_text()

    with pytest.raises(ParseError, match="no repository cards"):
        parse_trending(html)


def test_does_not_skip_a_malformed_card_after_a_valid_card() -> None:
    html = """
    <article class="Box-row"><h2><a href="/good/repo">good/repo</a></h2></article>
    <article class="Box-row"><h2>missing link</h2></article>
    """

    with pytest.raises(ParseError, match="invalid repository card 2"):
        parse_trending(html)
