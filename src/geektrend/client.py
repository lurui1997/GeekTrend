"""HTTP client for the one supported GitHub Trending source."""

import requests


TRENDING_URL = "https://github.com/trending/"
USER_AGENT = "GeekTrend/0.1 (+https://github.com/drulu/GeekTrend)"
REQUEST_TIMEOUT_SECONDS = 20


class FetchError(RuntimeError):
    """Raised when the fixed Trending page cannot be fetched."""


def fetch_trending(session: requests.Session | None = None) -> str:
    """Fetch and return the fixed GitHub Trending page."""
    client = session if session is not None else requests.Session()
    try:
        response = client.get(
            TRENDING_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.text
    except requests.Timeout as error:
        raise FetchError("fetch timed out") from error
    except requests.ConnectionError as error:
        raise FetchError("fetch connection failed") from error
    except requests.HTTPError as error:
        raise FetchError("fetch failed with HTTP status") from error
    except requests.RequestException as error:
        raise FetchError("fetch request failed") from error
