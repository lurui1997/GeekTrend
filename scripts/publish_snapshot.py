from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import NoReturn


MAX_PUSH_ATTEMPTS = 3
_SNAPSHOT_PATH = re.compile(r"data/\d{4}/\d{2}/\d{2}/[^/]+\.json")


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], check=check, text=True, capture_output=True
    )


def _default_push(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True)


def _default_rebase(args: list[str]) -> subprocess.CompletedProcess[str]:
    return _git(*args, check=False)


# These narrow seams let tests bound repeated push failures without mocking Git's
# staging, commit, fetch, or normal rebase semantics.
_run_push = _default_push
_run_rebase = _default_rebase


def _fail(message: str) -> NoReturn:
    raise RuntimeError(message)


def _validated_path(snapshot_path: Path) -> str:
    raw = str(snapshot_path)
    posix = PurePosixPath(raw)
    if (
        snapshot_path.is_absolute()
        or "\\" in raw
        or ".." in posix.parts
        or raw != posix.as_posix()
        or not _SNAPSHOT_PATH.fullmatch(raw)
    ):
        raise ValueError("snapshot path must be data/YYYY/MM/DD/*.json")

    root = Path(_git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
    supplied = root / raw
    candidate = supplied.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("snapshot path resolves outside the repository")
    if supplied.is_symlink():
        raise ValueError("snapshot path must be a regular file, not a symlink")
    if not candidate.is_file():
        _fail("snapshot path does not exist as a file")
    return raw


def _names(*args: str) -> list[str]:
    return _git(*args).stdout.splitlines()


def _verify_head(relative: str) -> None:
    changed = _names("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    if changed != [relative]:
        _fail("rebased HEAD does not contain exactly the snapshot path")


def publish(
    snapshot_path: Path,
    *,
    branch: str,
    remote: str = "origin",
    max_push_attempts: int = MAX_PUSH_ATTEMPTS,
) -> None:
    if not branch or not remote:
        raise ValueError("branch and remote must be non-empty")
    if max_push_attempts < 1:
        raise ValueError("max_push_attempts must be positive")

    relative = _validated_path(snapshot_path)
    if _names("diff", "--cached", "--name-only"):
        _fail("index must be clean before publication")
    if _git("check-ignore", "--quiet", "--", relative, check=False).returncode == 0:
        _fail("snapshot path is ignored")
    if _git("ls-files", "--error-unmatch", "--", relative, check=False).returncode == 0:
        _fail("snapshot path is already tracked")

    _git("add", "--", relative)
    if _names("diff", "--cached", "--name-only") != [relative]:
        _fail("snapshot path is not the sole staged path")

    timestamp = Path(relative).stem
    _git("commit", "-m", f"chore(data): capture GitHub Trending snapshot {timestamp}", "--", relative)
    _verify_head(relative)

    for attempt in range(1, max_push_attempts + 1):
        push = _run_push(["git", "push", remote, f"HEAD:{branch}"])
        if push.returncode == 0:
            return
        if attempt == max_push_attempts:
            _fail(f"push failed after {max_push_attempts} attempts")

        _git("fetch", remote, branch)
        rebase = _run_rebase(["rebase", "--autostash", f"{remote}/{branch}"])
        if rebase.returncode != 0:
            _git("rebase", "--abort", check=False)
            _fail("rebase failed; publication aborted")
        _verify_head(relative)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_path", type=Path)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    publish(args.snapshot_path, branch=args.branch)


if __name__ == "__main__":
    main()
