import runpy
from pathlib import Path

import pytest

import geektrend.cli as cli
from geektrend.collector import CollectionError


def test_main_collects_into_current_directory_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[Path] = []
    monkeypatch.setattr(cli, "collect", lambda root: seen.append(root) or Path("data/snapshot.json"))

    assert cli.main([]) == 0
    assert seen == [Path(".")]
    assert capsys.readouterr() == ("data/snapshot.json\n", "")


def test_main_accepts_only_output_root_and_prints_posix_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "collect", lambda root: Path("data/2026/07/snapshot.json"))

    assert cli.main(["--output-root", str(tmp_path)]) == 0
    assert capsys.readouterr() == ("data/2026/07/snapshot.json\n", "")


def test_main_reports_expected_collection_failure_without_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cause = RuntimeError("network unavailable")

    def fail(root: Path) -> Path:
        raise CollectionError("fetch stage failed") from cause

    monkeypatch.setattr(cli, "collect", fail)

    assert cli.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "collection failed: fetch stage failed: network unavailable\n"


def test_help_is_available_and_url_or_filter_flags_are_not_supported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as help_exit:
        cli.main(["--help"])
    assert help_exit.value.code == 0
    assert "--output-root" in capsys.readouterr().out

    for unsupported in ("--url", "--language", "--since"):
        with pytest.raises(SystemExit) as bad_exit:
            cli.main([unsupported, "value"])
        assert bad_exit.value.code == 2


def test_module_boundary_exits_with_main_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("geektrend.collector.collect", lambda root: Path("data/snapshot.json"))
    monkeypatch.setattr("sys.argv", ["geektrend"])

    with pytest.warns(RuntimeWarning), pytest.raises(SystemExit) as caught:
        runpy.run_module("geektrend.cli", run_name="__main__")

    assert caught.value.code == 0
