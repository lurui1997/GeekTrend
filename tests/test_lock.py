from importlib.metadata import version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


EXPECTED = {
    "beautifulsoup4",
    "certifi",
    "charset-normalizer",
    "idna",
    "iniconfig",
    "packaging",
    "pluggy",
    "pygments",
    "pytest",
    "pyyaml",
    "requests",
    "setuptools",
    "soupsieve",
    "typing-extensions",
    "urllib3",
}


def _logical_lines() -> list[str]:
    lines: list[str] = []
    current = ""
    lock = Path(__file__).parents[1] / "requirements.lock"
    for raw_line in lock.read_text(encoding="utf-8").splitlines():
        content = raw_line.split("#", 1)[0].strip()
        if not content:
            continue
        current += content.removesuffix("\\").strip()
        if content.endswith("\\"):
            current += " "
            continue
        lines.append(current)
        current = ""
    assert not current, "requirements.lock has an unfinished continuation"
    return lines


def _locked_requirements() -> dict[str, Requirement]:
    lines = _logical_lines()
    assert lines.count("-e .") == 1
    assert all(not line.startswith("-e ") or line == "-e ." for line in lines)

    locked: dict[str, Requirement] = {}
    for line in lines:
        if line == "-e .":
            continue
        assert not line.startswith("--"), f"standalone option is not allowed: {line}"
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        specifiers = list(requirement.specifier)
        assert requirement.url is None, f"URL is not allowed for {name}"
        assert requirement.marker is None, f"marker is not allowed for {name}"
        assert len(specifiers) == 1 and specifiers[0].operator == "==", (
            f"{name} must have one exact version"
        )
        assert name not in locked, f"duplicate locked requirement: {name}"
        locked[name] = requirement
    return locked


def test_lock_contains_only_the_expected_exact_requirements() -> None:
    assert set(_locked_requirements()) == EXPECTED


def test_installed_versions_match_the_lock() -> None:
    for name, requirement in _locked_requirements().items():
        locked_version = next(iter(requirement.specifier)).version
        assert version(name) == locked_version
