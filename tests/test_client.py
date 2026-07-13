from unittest.mock import Mock

import pytest
import requests

from geektrend.client import (
    REQUEST_TIMEOUT_SECONDS,
    TRENDING_URL,
    USER_AGENT,
    FetchError,
    fetch_trending,
)


def test_fetches_the_fixed_trending_page_with_explicit_request_contract() -> None:
    response = Mock(text="<html>trending</html>")
    session = Mock()
    session.get.return_value = response

    assert fetch_trending(session) == "<html>trending</html>"

    session.get.assert_called_once_with(
        "https://github.com/trending/",
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status.assert_called_once_with()
    assert TRENDING_URL == "https://github.com/trending/"
    assert REQUEST_TIMEOUT_SECONDS == 20
    assert USER_AGENT.strip()


@pytest.mark.parametrize(
    ("error", "stage"),
    [
        (requests.Timeout("late"), "timed out"),
        (requests.ConnectionError("offline"), "connection failed"),
    ],
)
def test_translates_request_failures_and_preserves_the_cause(
    error: requests.RequestException, stage: str
) -> None:
    session = Mock()
    session.get.side_effect = error

    with pytest.raises(FetchError, match=stage) as caught:
        fetch_trending(session)

    assert caught.value.__cause__ is error


def test_translates_http_status_failure_and_preserves_the_cause() -> None:
    error = requests.HTTPError("503")
    response = Mock(text="unavailable")
    response.raise_for_status.side_effect = error
    session = Mock()
    session.get.return_value = response

    with pytest.raises(FetchError, match="status") as caught:
        fetch_trending(session)

    assert caught.value.__cause__ is error


def test_does_not_catch_non_request_exceptions() -> None:
    session = Mock()
    error = RuntimeError("programming error")
    session.get.side_effect = error

    with pytest.raises(RuntimeError) as caught:
        fetch_trending(session)

    assert caught.value is error
