from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import NoReturn


MAX_PUSH_ATTEMPTS = 3
_SNAPSHOT_PATH = re.compile(r"data/\d{4}/\d{2}/\d{2}/[^/]+\.json")
_SAFE_REMOTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


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


def _verify_head(relative: str, expected_oid: str | None = None) -> None:
    changed = _names("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    if changed != [relative]:
        _fail("rebased HEAD does not contain exactly the snapshot path")
    if expected_oid is not None:
        committed_oid = _git("rev-parse", f"HEAD:{relative}").stdout.strip()
        if committed_oid != expected_oid:
            _fail("committed snapshot blob differs from the validated staged file")


def _validate_destination(branch: str, remote: str) -> None:
    destination = f"refs/heads/{branch}"
    if branch.startswith("-") or branch.startswith("refs/"):
        raise ValueError("branch must be a safe short branch name")
    if _git("check-ref-format", destination, check=False).returncode != 0:
        raise ValueError("branch does not form a valid destination ref")
    if not _SAFE_REMOTE.fullmatch(remote) or remote not in _names("remote"):
        raise ValueError("remote must be an existing safe remote name")


def _verify_staged_file(relative: str) -> str:
    supplied = Path(_git("rev-parse", "--show-toplevel").stdout.strip()) / relative
    staged = _names("ls-files", "--stage", "--", relative)
    if len(staged) != 1:
        _fail("snapshot path does not have exactly one staged object")
    metadata = staged[0].split(maxsplit=3)
    if len(metadata) != 4 or metadata[0] not in {"100644", "100755"}:
        _fail("staged snapshot is not a regular file")
    if supplied.is_symlink() or not supplied.is_file():
        _fail("snapshot changed before it could be committed")
    worktree_oid = _git("hash-object", "--no-filters", "--", relative).stdout.strip()
    if metadata[1] != worktree_oid:
        _fail("staged snapshot content differs from the validated file")
    return metadata[1]


def _is_non_fast_forward(push: subprocess.CompletedProcess[str], branch: str) -> bool:
    expected_ref = f"refs/heads/{branch}"
    for line in push.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[0] != "!":
            continue
        if fields[1] != f"HEAD:{expected_ref}":
            continue
        if fields[2] in {
            "[rejected] (non-fast-forward)",
            "[rejected] (fetch first)",
        }:
            return True
    return False


def _diagnostic(result: subprocess.CompletedProcess[str]) -> str:
    details = [text.strip() for text in (result.stderr, result.stdout) if text.strip()]
    return "\n".join(details) or "git command failed without diagnostics"


def publish(
    snapshot_path: Path,
    *,
    branch: str,
    remote: str = "origin",
    max_push_attempts: int = MAX_PUSH_ATTEMPTS,
) -> None:
    if max_push_attempts < 1:
        raise ValueError("max_push_attempts must be positive")

    _validate_destination(branch, remote)
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
    expected_oid = _verify_staged_file(relative)

    timestamp = Path(relative).stem
    _git("commit", "-m", f"chore(data): capture GitHub Trending snapshot {timestamp}", "--", relative)
    _verify_head(relative, expected_oid)

    for attempt in range(1, max_push_attempts + 1):
        push = _run_push(
            ["git", "push", "--porcelain", "--", remote, f"HEAD:refs/heads/{branch}"]
        )
        if push.returncode == 0:
            return
        diagnostic = _diagnostic(push)
        if not _is_non_fast_forward(push, branch):
            _fail(f"push failed without a retryable non-fast-forward: {diagnostic}")
        if attempt == max_push_attempts:
            _fail(f"push failed after {max_push_attempts} attempts: {diagnostic}")

        _git("fetch", "--", remote, branch)
        upstream = f"refs/remotes/{remote}/{branch}"
        rebase = _run_rebase(["rebase", "--autostash", upstream])
        if rebase.returncode != 0:
            abort = _git("rebase", "--abort", check=False)
            if abort.returncode != 0:
                _fail(
                    "rebase failed and abort also failed: "
                    f"rebase: {_diagnostic(rebase)}; abort: {_diagnostic(abort)}"
                )
            detail = _diagnostic(rebase)
            _fail(f"rebase failed; publication aborted: {detail}")
        _verify_head(relative, expected_oid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_path", type=Path)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    publish(args.snapshot_path, branch=args.branch)


if __name__ == "__main__":
    main()
