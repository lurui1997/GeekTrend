from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path

import pytest


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, text=True, capture_output=True
    )


def configure(repo: Path) -> None:
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")


@pytest.fixture
def clones(tmp_path: Path) -> tuple[Path, Path, Path]:
    origin = tmp_path / "origin.git"
    first = tmp_path / "first"
    second = tmp_path / "second"
    git(tmp_path, "init", "--bare", str(origin))
    git(tmp_path, "clone", str(origin), str(first))
    configure(first)
    (first / "README.md").write_text("seed\n")
    git(first, "add", "README.md")
    git(first, "commit", "-m", "seed")
    git(first, "branch", "-M", "main")
    git(first, "push", "-u", "origin", "main")
    git(tmp_path, "clone", "--branch", "main", str(origin), str(second))
    configure(second)
    return origin, first, second


def snapshot(repo: Path, name: str = "2026-07-13T02-00-03Z.json") -> Path:
    relative = Path("data/2026/07/13") / name
    (repo / relative).parent.mkdir(parents=True, exist_ok=True)
    (repo / relative).write_text("{}\n")
    return relative


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/data/2026/07/13/a.json",
        "data/2026/07/13/../a.json",
        "data/2026/07/13/a.txt",
        "other/2026/07/13/a.json",
        "data/2026/07/a.json",
        "data/26/07/13/a.json",
    ],
)
def test_rejects_malformed_snapshot_paths(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, bad_path: str
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError):
        publish(Path(bad_path), branch="main")


def test_rejects_path_resolving_outside_repository(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    outside = repo.parent / "outside"
    outside.mkdir()
    data = repo / "data"
    data.symlink_to(outside, target_is_directory=True)
    relative = Path("data/2026/07/13/a.json")
    (outside / "2026/07/13").mkdir(parents=True)
    (outside / "2026/07/13/a.json").write_text("{}\n")
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError):
        publish(relative, branch="main")


def test_rejects_snapshot_symlink_inside_repository(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    target = repo / "payload.json"
    target.write_text("{}\n")
    relative = Path("data/2026/07/13/a.json")
    (repo / relative).parent.mkdir(parents=True)
    (repo / relative).symlink_to(target)
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError, match="regular file"):
        publish(relative, branch="main")


@pytest.mark.parametrize("condition", ["absent", "ignored", "tracked", "staged"])
def test_rejects_unsafe_repository_state(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    relative = Path("data/2026/07/13/a.json")
    if condition != "absent":
        snapshot(repo, "a.json")
    if condition == "ignored":
        (repo / ".git/info/exclude").write_text("data/\n")
    elif condition == "tracked":
        git(repo, "add", str(relative))
        git(repo, "commit", "-m", "already tracked")
    elif condition == "staged":
        (repo / "other.txt").write_text("staged\n")
        git(repo, "add", "other.txt")
    monkeypatch.chdir(repo)

    with pytest.raises(RuntimeError):
        publish(relative, branch="main")


def test_first_push_commits_only_snapshot_and_preserves_unrelated_changes(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, observer = clones
    relative = snapshot(repo)
    (repo / "README.md").write_text("locally modified\n")
    (repo / "scratch.txt").write_text("untracked\n")
    monkeypatch.chdir(repo)

    publish(relative, branch="main")

    assert git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.splitlines() == [relative.as_posix()]
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == "chore(data): capture GitHub Trending snapshot 2026-07-13T02-00-03Z"
    assert git(repo, "status", "--short").stdout.splitlines() == [" M README.md", "?? scratch.txt"]
    git(observer, "pull", "--ff-only")
    assert (observer / relative).is_file()


def test_non_fast_forward_fetches_rebases_and_retries_real_push(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, competitor = clones
    relative = snapshot(repo)
    (repo / "README.md").write_text("preserve through rebase\n")
    (competitor / "remote.txt").write_text("remote\n")
    git(competitor, "add", "remote.txt")
    git(competitor, "commit", "-m", "advance remote")
    git(competitor, "push", "origin", "HEAD:main")
    monkeypatch.chdir(repo)

    publish(relative, branch="main")

    assert git(repo, "rev-list", "--count", "origin/main..HEAD").stdout.strip() == "0"
    assert (repo / "remote.txt").is_file()
    assert (repo / "README.md").read_text() == "preserve through rebase\n"
    assert git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.splitlines() == [relative.as_posix()]


def test_refuses_retry_when_rebased_head_contains_another_path(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.publish_snapshot as publisher

    _, repo, _ = clones
    relative = snapshot(repo)
    calls = 0

    def reject_and_replace_head(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            result = subprocess.CompletedProcess(
                command,
                1,
                "!\tHEAD:refs/heads/main\t[rejected] (non-fast-forward)\nDone\n",
                "error: failed to push some refs\n",
            )
            original = publisher._run_rebase

            def unsafe_rebase(args: list[str]) -> subprocess.CompletedProcess[str]:
                outcome = original(args)
                (repo / "other.txt").write_text("unsafe\n")
                git(repo, "add", "other.txt")
                git(repo, "commit", "--amend", "--no-edit")
                return outcome

            monkeypatch.setattr(publisher, "_run_rebase", unsafe_rebase)
            return result
        return subprocess.run(command, text=True, capture_output=True)

    monkeypatch.setattr(publisher, "_run_push", reject_and_replace_head)
    monkeypatch.chdir(repo)

    with pytest.raises(RuntimeError, match="rebased HEAD"):
        publisher.publish(relative, branch="main")

    assert calls == 1


def test_push_failures_are_bounded_and_never_force(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.publish_snapshot as publisher

    _, repo, _ = clones
    relative = snapshot(repo)
    commands: list[list[str]] = []

    def always_reject(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            1,
            "!\tHEAD:refs/heads/main\t[rejected] (non-fast-forward)\nDone\n",
            "error: failed to push some refs\n",
        )

    monkeypatch.setattr(publisher, "_run_push", always_reject)
    monkeypatch.chdir(repo)

    with pytest.raises(RuntimeError, match="3 attempts"):
        publisher.publish(relative, branch="main")

    assert len(commands) == publisher.MAX_PUSH_ATTEMPTS == 3
    assert all("--force" not in command and "-f" not in command for command in commands)


@pytest.mark.parametrize(
    ("stderr", "stdout"),
    [
        ("fatal: Authentication failed\n", ""),
        ("fatal: unable to access remote: network down\n", ""),
        ("remote: protected branch hook declined\n", "!\tHEAD:refs/heads/main\t[remote rejected] (hook declined)\n"),
        ("fatal: invalid refspec\n", ""),
        ("fatal: unexpected failure\n", ""),
    ],
)
def test_non_nff_push_failure_stops_immediately_with_diagnostic(
    clones: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
    stdout: str,
) -> None:
    import scripts.publish_snapshot as publisher

    _, repo, _ = clones
    relative = snapshot(repo)
    commands: list[list[str]] = []

    def fail(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout, stderr)

    monkeypatch.setattr(publisher, "_run_push", fail)
    monkeypatch.chdir(repo)

    with pytest.raises(RuntimeError, match=re.escape(stderr.strip())):
        publisher.publish(relative, branch="main")

    assert len(commands) == 1
    assert git(repo, "reflog", "--format=%gs").stdout.count("rebase") == 0


@pytest.mark.parametrize("branch", ["-bad", "bad..name", "bad name", "main:evil", "refs/heads/main"])
def test_rejects_unsafe_branch_before_staging(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, branch: str
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    relative = snapshot(repo)
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError, match="branch"):
        publish(relative, branch=branch)

    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


@pytest.mark.parametrize("remote", ["-c", "--upload-pack=evil", "origin/evil", "missing"])
def test_rejects_unsafe_or_missing_remote_before_staging(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, remote: str
) -> None:
    from scripts.publish_snapshot import publish

    _, repo, _ = clones
    relative = snapshot(repo)
    monkeypatch.chdir(repo)

    with pytest.raises(ValueError, match="remote"):
        publish(relative, branch="main", remote=remote)

    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_cli_requires_branch() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/publish_snapshot.py", "data/2026/07/13/a.json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "--branch" in result.stderr


def test_git_diagnostic_preserves_stdout_and_stderr() -> None:
    import scripts.publish_snapshot as publisher

    result = subprocess.CompletedProcess([], 1, "stdout detail\n", "stderr detail\n")

    assert publisher._diagnostic(result) == "stderr detail\nstdout detail"


def test_refuses_commit_if_index_changes_after_staged_blob_validation(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.publish_snapshot as publisher

    _, repo, _ = clones
    relative = snapshot(repo)
    original = publisher._verify_staged_file

    def swap_after_validation(path: str) -> str:
        expected = original(path)
        (repo / relative).write_text('{"swapped": true}\n')
        git(repo, "add", "--", path)
        return expected

    monkeypatch.setattr(publisher, "_verify_staged_file", swap_after_validation)
    monkeypatch.chdir(repo)

    with pytest.raises(RuntimeError, match="committed snapshot blob"):
        publisher.publish(relative, branch="main")
