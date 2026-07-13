# GitHub Trending Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested Python collector that captures GitHub's default daily Trending repositories as immutable JSON snapshots and safely publishes one snapshot from GitHub Actions every two hours.

**Architecture:** A small `geektrend` package separates HTTP fetching, HTML parsing, domain validation, atomic snapshot writing, and CLI orchestration. A separate publication script owns all Git operations so the workflow can stage and push exactly the generated path, including bounded non-fast-forward recovery. Deterministic fixtures and temporary repositories test behavior without network or GitHub credentials; the live site is used only for the final manual smoke test.

**Tech Stack:** Python 3.13, Requests, Beautiful Soup 4, pytest, PyYAML, GitHub Actions, Git CLI

---

## File map

- Create `pyproject.toml`: package metadata, console entry point, pytest configuration, and direct dependency declarations.
- Create `requirements.lock`: exact direct and transitive runtime/test versions used locally and in CI.
- Create `src/geektrend/__init__.py`: package version only.
- Create `src/geektrend/model.py`: immutable contributor/repository/snapshot records plus validation.
- Create `src/geektrend/parser.py`: all selectors and HTML-to-record conversion.
- Create `src/geektrend/client.py`: fixed Trending URL, user agent, timeout, and HTTP error translation.
- Create `src/geektrend/writer.py`: UTC+08:00 path calculation and atomic UTF-8 JSON persistence.
- Create `src/geektrend/collector.py`: fetch/parse/validate/write coordination with injected clock and collaborators.
- Create `src/geektrend/cli.py`: command-line boundary, stable success output, and non-zero failures.
- Create `scripts/publish_snapshot.py`: exact-path staging, commit, bounded fetch/rebase/push retry, and post-rebase safety checks.
- Create `.github/workflows/snapshot.yml`: two-hour/manual workflow with serialized runs and immutable action pins.
- Create `tests/fixtures/trending.html`: representative complete and optional-field cards copied down to the minimum stable markup needed by parser tests.
- Create `tests/fixtures/empty.html`: structurally valid page with no repository cards.
- Create `tests/test_model.py`: identity, URL, duplicate, and snapshot validation tests.
- Create `tests/test_parser.py`: fixture parsing, normalization, optional fields, contributors, malformed markup, and duplicates.
- Create `tests/test_client.py`: request contract and network/status failure tests.
- Create `tests/test_writer.py`: path/schema/encoding/newline/overwrite and fault-injection atomicity tests.
- Create `tests/test_collector.py`: collaborator orchestration and no-write-on-failure tests.
- Create `tests/test_cli.py`: stdout/path and error exit contract tests.
- Create `tests/test_publish_snapshot.py`: isolated Git-repository tests for exact staging and retry safety.
- Create `tests/test_workflow_contract.py`: deterministic YAML/source contract checks for schedule, permissions, ordering, URL, timestamp, and publish behavior.
- Create `tests/test_lock.py`: exact dependency-set and exact-version lock contract.
- Modify `README.md`: setup, operation, schema, automation permissions, and scraper limitations.
- Create `data/.gitkeep`: documents the snapshot root while allowing the empty tree to be committed.

### Task 1: Bootstrap the locked Python project

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.lock`
- Create: `src/geektrend/__init__.py`
- Create: `tests/test_package.py`
- Create: `tests/test_lock.py`
- Create: `data/.gitkeep`

- [ ] **Step 0: Commit this approved implementation plan**

Run:

```bash
git add docs/superpowers/plans/2026-07-13-github-trending-snapshot.md
git commit -m "docs: plan trending snapshot implementation"
```

Expected: the plan is tracked before implementation begins, so later clean-tree assertions include it.

- [ ] **Step 0a: Provision the required interpreter and deterministic red-test tooling**

Run:

```bash
uv python install 3.13
uv venv --seed --python 3.13 .venv
uv pip install --python .venv/bin/python pytest==8.4.1
.venv/bin/python --version
```

Expected: the final command prints `Python 3.13.x`. All subsequent local commands use `.venv/bin/python`; do not rely on a system `python3.13` binary.

- [ ] **Step 1: Write the failing package smoke test**

```python
# tests/test_package.py
from geektrend import __version__


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to prove the package is not configured**

Run: `.venv/bin/python -m pytest tests/test_package.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'geektrend'`.

- [ ] **Step 3: Add package metadata and the minimal package**

Create `pyproject.toml` with this contract:

```toml
[build-system]
requires = ["setuptools==80.9.0"]
build-backend = "setuptools.build_meta"

[project]
name = "geektrend"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = ["beautifulsoup4==4.13.4", "requests==2.32.4"]

[project.scripts]
geektrend = "geektrend.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
```

Create `src/geektrend/__init__.py` containing only `__version__ = "0.1.0"`. Create an empty `data/.gitkeep`.

- [ ] **Step 4: Add and verify a fully exact dependency lock**

Create `requirements.lock` with no ranges or floating references. It must contain the exact versions resolved for Python 3.13 from the two project dependencies plus test/build tools: `beautifulsoup4`, `certifi`, `charset-normalizer`, `idna`, `iniconfig`, `packaging`, `pluggy`, `Pygments`, `pytest`, `PyYAML`, `requests`, `setuptools`, `soupsieve`, `typing_extensions`, and `urllib3`. Generate it in a clean Python 3.13 environment rather than guessing transitive versions:

```bash
.venv/bin/python -m pip install --upgrade 'pip==25.1.1'
.venv/bin/python -m pip install 'pip-tools==7.4.1'
.venv/bin/pip-compile --resolver=backtracking --strip-extras \
  --output-file=requirements.lock \
  <(printf '%s\n' '-e .' 'pytest==8.4.1' 'PyYAML==6.0.2' 'setuptools==80.9.0')
```

If process substitution is not accepted by `pip-compile`, create a temporary file outside the repository, pass it as the input, then delete it. Inspect the result and ensure every installable line uses `==`; retain the generated provenance comments.

Run: `.venv/bin/python -m pip install -r requirements.lock && .venv/bin/python -m pytest tests/test_package.py -q`

Expected: `1 passed`.

- [ ] **Step 4a: Add a deterministic exact-lock contract test**

`tests/test_lock.py` must parse logical requirement lines with `packaging.requirements.Requirement`, explicitly allow only the local `-e .` entry, reject URLs, hashes standing alone, ranges, environment-dependent alternate versions, and any non-`==` specifier. Assert the normalized package-name set is exactly:

```python
EXPECTED = {
    "beautifulsoup4", "certifi", "charset-normalizer", "idna", "iniconfig",
    "packaging", "pluggy", "pygments", "pytest", "pyyaml", "requests",
    "setuptools", "soupsieve", "typing-extensions", "urllib3",
}
```

Also query `importlib.metadata.version()` for every expected name and assert it equals the single locked version, proving the installed environment matches the reviewed lock. If the actual clean Python 3.13 resolution has a justified additional transitive distribution, add it both to the generated lock and this explicit set after inspection—never weaken the assertion to a subset.

Run: `.venv/bin/python -m pytest tests/test_lock.py -q`

Expected: all lock contract tests PASS.

- [ ] **Step 5: Commit the bootstrap**

```bash
git add pyproject.toml requirements.lock src/geektrend/__init__.py tests/test_package.py tests/test_lock.py data/.gitkeep
git commit -m "build: bootstrap locked Python project"
```

### Task 2: Define and validate the snapshot domain model

**Files:**
- Create: `src/geektrend/model.py`
- Create: `tests/test_model.py`

- [ ] **Step 1: Write failing tests for valid records and all required rejection cases**

Use frozen dataclasses `Contributor`, `Repository`, and `Snapshot`. Tests must assert:

```python
def test_valid_snapshot_serializes_to_schema():
    snapshot = Snapshot(
        fetched_at=datetime(2026, 7, 13, 10, tzinfo=CHINA_TIME),
        source_url="https://github.com/trending/",
        repositories=(Repository(
            repository_name="octo/demo",
            url="https://github.com/octo/demo",
            contributors=(Contributor("octocat", "https://github.com/octocat"),),
            description="你好",
            primary_language="Python",
        ),),
    )
    assert snapshot.to_dict()["repository_count"] == 1
    assert snapshot.to_dict()["fetched_at"] == "2026-07-13T10:00:00+08:00"
```

Add parametrized failures for a zero-repository snapshot, duplicate repository names, names without exactly one slash, empty owner/name segments (`/repo`, `owner/`), whitespace within either segment, mismatched repository URLs, URLs with query/fragment, blank contributor usernames, contributor usernames containing a slash or any whitespace, mismatched/non-GitHub contributor URLs, a naive timestamp, an aware but non-UTC+08:00 timestamp, and a source URL other than the exact fixed URL. Assert the domain-specific `ValidationError` text names the offending field.

- [ ] **Step 2: Run the model tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'geektrend.model'`.

- [ ] **Step 3: Implement the immutable model and centralized validation**

Implement frozen, slotted dataclasses. Validate in `__post_init__`; accept optional description/language as `str | None`; store repositories/contributors as tuples. A repository identity must consist of exactly two non-empty slash-separated segments with no whitespace in either; a contributor username must be one non-empty segment with no slash or whitespace. Repository URLs must equal `f"https://github.com/{repository_name}"`; contributor URLs must equal `f"https://github.com/{username}"`. Reject duplicate repository names. Require `fetched_at.utcoffset() == timedelta(hours=8)` rather than merely timezone-awareness. `Snapshot.to_dict()` must return only JSON primitives in the exact key order from the spec and render UTC+08:00 as second-precision ISO 8601 with `+08:00`.

- [ ] **Step 4: Run focused and complete tests**

Run: `.venv/bin/python -m pytest tests/test_model.py -q`

Expected: all model tests PASS.

Run: `.venv/bin/python -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit the model**

```bash
git add src/geektrend/model.py tests/test_model.py
git commit -m "feat: validate trending snapshot records"
```

### Task 3: Parse checked-in Trending markup

**Files:**
- Create: `src/geektrend/parser.py`
- Create: `tests/fixtures/trending.html`
- Create: `tests/fixtures/empty.html`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Check in minimal representative fixtures**

`trending.html` must include at least two `article.Box-row` cards: one with a multiline `h2 a[href='/owner/repo']`, description, language, and two `span.d-inline-block a[data-hovercard-type='user']`; the other must omit description, language, and built-by users. Include surrounding unrelated links to prove selectors are card-scoped. `empty.html` must contain the page shell but no `article.Box-row`.

- [ ] **Step 2: Write the failing parser tests**

Test exact extraction of `owner/repo`, absolute canonical repository URL, collapsed description whitespace, primary language, ordered contributor usernames/profile URLs, multiple cards, and `None`/empty tuple for optional fields. Add inline HTML parametrized cases for absolute repository/profile links, duplicate repositories, malformed repository hrefs/names, mismatched profile identity, and zero cards. Require `ParseError` to wrap malformed/empty results while preserving a useful message.

- [ ] **Step 3: Run parser tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_parser.py -q`

Expected: FAIL importing `geektrend.parser`.

- [ ] **Step 4: Implement the smallest card-scoped parser**

Expose `parse_trending(html: str) -> tuple[Repository, ...]`. Keep selectors as module constants. For each card, normalize text with `" ".join(element.stripped_strings)`, resolve links with `urljoin("https://github.com", href)`, remove no URL components, and rely on `Repository`/`Contributor` validation to reject noncanonical values. Convert domain validation failures to `ParseError("invalid repository card ...")`. Reject zero cards and duplicate identities; do not silently skip malformed cards.

- [ ] **Step 5: Run focused and full tests**

Run: `.venv/bin/python -m pytest tests/test_parser.py -q`

Expected: all parser tests PASS.

Run: `.venv/bin/python -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit parser and fixtures**

```bash
git add src/geektrend/parser.py tests/test_parser.py tests/fixtures/trending.html tests/fixtures/empty.html
git commit -m "feat: parse GitHub Trending cards"
```

### Task 4: Fetch the fixed source and atomically write snapshots

**Files:**
- Create: `src/geektrend/client.py`
- Create: `src/geektrend/writer.py`
- Create: `tests/test_client.py`
- Create: `tests/test_writer.py`

- [ ] **Step 1: Write failing HTTP contract tests**

Inject a fake `requests.Session`. Assert `fetch_trending()` calls exactly `GET https://github.com/trending/` with a nonempty explicit `User-Agent` and `timeout=20`, returns response text after `raise_for_status()`, and translates timeout, connection, and status failures to `FetchError` with stage-specific messages.

- [ ] **Step 2: Run and implement the client**

Run: `.venv/bin/python -m pytest tests/test_client.py -q`

Expected: FAIL importing `geektrend.client`.

Implement constants `TRENDING_URL`, `USER_AGENT`, and `REQUEST_TIMEOUT_SECONDS`; expose `fetch_trending(session: requests.Session | None = None) -> str`. Catch `requests.RequestException` only, preserve its cause with `raise ... from error`, and never accept a caller-supplied URL.

Run: `.venv/bin/python -m pytest tests/test_client.py -q`

Expected: all client tests PASS.

- [ ] **Step 3: Write failing atomic writer tests**

With `tmp_path`, assert timestamp `2026-07-13T10:00:03+08:00` produces `data/2026/07/13/2026-07-13T10-00-03+08-00.json`; JSON is UTF-8, pretty-printed with `ensure_ascii=False`, ends in exactly one newline, and matches `Snapshot.to_dict()`. Assert an existing destination raises `SnapshotExistsError` unchanged.

Add fault injection through private wrappers or injected callables for serialization, temporary-file write, flush, `os.fsync`, atomic `os.link`, and cleanup `os.unlink`. For failures before/during `os.link`, assert the destination does not exist; for cleanup unlink failure after a successful link, assert the complete destination exists and no partial JSON is observable. In every case assert cleanup is attempted, any safe-to-remove temporary artifact is removed, and `WriteError` retains the original exception as `__cause__`. Add a same-destination race test in which a competing complete destination appears immediately before `os.link`: the link must fail with `FileExistsError`, the competitor's bytes must remain unchanged, and the collector's temp must be cleaned. Keep the temporary file in the destination directory so the hard-link publication occurs on one filesystem.

- [ ] **Step 4: Run and implement the writer**

Run: `.venv/bin/python -m pytest tests/test_writer.py -q`

Expected: FAIL importing `geektrend.writer`.

Implement `snapshot_relative_path(fetched_at) -> Path` and `write_snapshot(snapshot, root=Path(".")) -> Path`. Open a unique temp file with exclusive creation, write JSON, flush, fsync, close, then atomically publish it with `os.link(temp_path, destination)`. A hard link is the concrete no-overwrite primitive: it atomically creates the destination and fails if one already exists; then unlink the temp name. Clean the temp in `finally`, while never deleting a successfully published destination. Return the repository-relative `data/...json` path, never an absolute path. Document in code that this is the atomic-publication equivalent of rename chosen to preserve strict no-overwrite semantics.

Run: `.venv/bin/python -m pytest tests/test_writer.py -q && .venv/bin/python -m pytest -q`

Expected: writer tests and full suite PASS.

- [ ] **Step 5: Commit client and writer**

```bash
git add src/geektrend/client.py src/geektrend/writer.py tests/test_client.py tests/test_writer.py
git commit -m "feat: fetch and atomically store snapshots"
```

### Task 5: Coordinate collection and expose the CLI

**Files:**
- Create: `src/geektrend/collector.py`
- Create: `src/geektrend/cli.py`
- Create: `tests/test_collector.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing coordinator tests with injected collaborators**

Assert `collect(root, fetcher, parser, writer, clock)` calls each collaborator once, uses a timezone-aware UTC+08:00 timestamp truncated to seconds, sets the exact source URL, and returns the relative writer path. Tests for fetch, parse, validation, and write exceptions must prove later collaborators are not called and no output exists.

- [ ] **Step 2: Run and implement the coordinator**

Run: `.venv/bin/python -m pytest tests/test_collector.py -q`

Expected: FAIL importing `geektrend.collector`.

Implement the straight-line flow `fetch -> parse -> Snapshot -> write`; default the clock to `datetime.now(CHINA_TIME)`. Add a `CollectionError` only when it adds stage context; retain exception chaining and do not swallow typed errors useful to the CLI.

Run: `.venv/bin/python -m pytest tests/test_collector.py -q`

Expected: all coordinator tests PASS.

- [ ] **Step 3: Write failing CLI contract tests**

Call `main(["--output-root", str(tmp_path)])` with a patched collector. On success assert exit code `0` and stdout is exactly the POSIX relative snapshot path plus newline—this is the workflow handoff contract. On any expected collector error assert exit code `1`, no stdout, and stderr begins `collection failed:`. Assert `--help` works and no URL/filter flags exist.

- [ ] **Step 4: Run and implement the CLI**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`

Expected: FAIL importing `geektrend.cli`.

Implement `main(argv: Sequence[str] | None = None) -> int` and a `if __name__ == "__main__": raise SystemExit(main())` boundary. Permit only `--output-root`, defaulting to the current directory. Print the path only after a successful completed write; send concise chained-error context to stderr.

Run: `.venv/bin/python -m pytest tests/test_collector.py tests/test_cli.py -q && .venv/bin/python -m pytest -q`

Expected: focused tests and full suite PASS.

- [ ] **Step 5: Commit coordinator and CLI**

```bash
git add src/geektrend/collector.py src/geektrend/cli.py tests/test_collector.py tests/test_cli.py
git commit -m "feat: add trending collection command"
```

### Task 6: Implement exact-path safe publication

**Files:**
- Create: `scripts/publish_snapshot.py`
- Create: `tests/test_publish_snapshot.py`

- [ ] **Step 1: Write failing tests around isolated temporary Git repositories**

Create a bare `origin`, clone it twice, configure identities, and use subprocess Git commands (never mock Git's semantics). Cover:

- rejecting absolute paths, `..`, non-JSON paths, and paths outside `data/YYYY/MM/DD/`;
- staging/committing only the supplied new snapshot while an unrelated untracked/modified file remains untouched;
- refusing a supplied path that is absent, ignored, already tracked, or not the only staged/committed path;
- successful first push;
- a non-fast-forward caused by the second clone, followed by fetch/rebase and one successful retry;
- refusing after rebase if `git diff-tree --no-commit-id --name-only -r HEAD` is not exactly the snapshot path;
- bounded failure after `MAX_PUSH_ATTEMPTS` and no force-push argument in any invocation.

Make the push command runner injectable only where needed to deterministically simulate repeated rejection; otherwise exercise real local repositories.

- [ ] **Step 2: Run publication tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_publish_snapshot.py -q`

Expected: FAIL because `scripts/publish_snapshot.py` does not exist.

- [ ] **Step 3: Implement the publication script**

Expose `publish(snapshot_path: Path, *, branch: str, remote: str = "origin", max_push_attempts: int = 3)`. Resolve and validate the relative POSIX path, require clean index before staging, `git add -- <exact path>`, verify `git diff --cached --name-only` equals only that path, and commit with `chore(data): capture GitHub Trending snapshot <timestamp>`. Push `HEAD:<branch>` normally. Tests and the CLI must pass `branch` by keyword.

On non-zero push: if attempts remain, run `git fetch <remote> <branch>`, rebase onto `<remote>/<branch>`, verify the rebased `HEAD` changes exactly the supplied snapshot path, and retry. Abort an unsuccessful rebase before exiting. Never run force push, never stage again after rebase, and treat every unsafe/malformed/conflicting condition as non-zero. The CLI requires `snapshot_path` and `--branch`; default attempts to the module constant `MAX_PUSH_ATTEMPTS = 3`.

- [ ] **Step 4: Verify publication behavior**

Run: `.venv/bin/python -m pytest tests/test_publish_snapshot.py -q`

Expected: all publication tests PASS, including real non-fast-forward recovery.

Run: `grep -R --line-number -E 'git add (\.|-A)|--force|-f([[:space:]]|$)' scripts .github 2>/dev/null`

Expected: no output.

- [ ] **Step 5: Commit publication automation**

```bash
git add scripts/publish_snapshot.py tests/test_publish_snapshot.py
git commit -m "feat: safely publish one snapshot"
```

### Task 7: Add the pinned two-hour GitHub Actions workflow and contract tests

**Files:**
- Create: `.github/workflows/snapshot.yml`
- Create: `tests/test_workflow_contract.py`

- [ ] **Step 1: Write failing deterministic workflow contract tests**

Load YAML with a custom loader that does not coerce the key `on` to boolean. Assert:

- triggers are exactly `schedule: [{cron: "0 */2 * * *"}]` and `workflow_dispatch`;
- top-level permissions are exactly `contents: write`;
- concurrency group is `github-trending-snapshot-${{ github.repository }}` and `cancel-in-progress` is false;
- the job runs on `ubuntu-latest`, checks out the current repository, and sets up exact Python `3.13`;
- every `uses:` value ends in a 40-character lowercase hexadecimal SHA and is allowlisted to checkout/setup-python;
- install uses only `python -m pip install -r requirements.lock` after pinning pip to the version used to generate the lock;
- the test step precedes collection, and collection precedes publication;
- collection first assigns the CLI result in a separate fail-fast command, then writes it to `$GITHUB_OUTPUT` as `snapshot_path` without recomputing a timestamp in shell;
- publication invokes `scripts/publish_snapshot.py` with exactly that output and `${{ github.ref_name }}`;
- workflow/source contain only the fixed unfiltered `https://github.com/trending/` URL and no `since`/language query;
- publication source contains exact-path index verification, `MAX_PUSH_ATTEMPTS = 3`, fetch/rebase, post-rebase diff verification, and no force push or broad add.

Add a subprocess contract test that runs the collection step's exact shell body with a fake `python` executable that exits non-zero. Assert the shell exits non-zero and a temporary `GITHUB_OUTPUT` remains empty. This prevents command-substitution failures from being hidden by an outer `echo`/`printf`.

- [ ] **Step 2: Run the contract tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_workflow_contract.py -q`

Expected: FAIL because `.github/workflows/snapshot.yml` is absent.

- [ ] **Step 3: Create the minimal workflow with immutable action pins**

Use these reviewed full SHAs (confirm their release provenance from the official action repositories immediately before committing; update the plan/test allowlist if an official security release supersedes them):

```yaml
name: Capture GitHub Trending

on:
  schedule:
    - cron: "0 */2 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: github-trending-snapshot-${{ github.repository }}
  cancel-in-progress: false

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          fetch-depth: 0
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements.lock
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip==25.1.1
          python -m pip install -r requirements.lock
      - name: Test
        run: python -m pytest -q
      - name: Collect
        id: collect
        shell: bash
        run: |
          set -euo pipefail
          snapshot_path="$(python -m geektrend.cli)"
          printf 'snapshot_path=%s\n' "$snapshot_path" >> "$GITHUB_OUTPUT"
      - name: Publish exact snapshot
        run: python scripts/publish_snapshot.py "${{ steps.collect.outputs.snapshot_path }}" --branch "${{ github.ref_name }}"
```

Do not add `pull-requests`, `actions`, or broad write permissions. The separate assignment plus `set -e` must stop the step before `printf` writes an output if collection fails.

- [ ] **Step 4: Run YAML and complete-suite verification**

Run: `.venv/bin/python -m pytest tests/test_workflow_contract.py -q`

Expected: all workflow contract tests PASS.

Run: `.venv/bin/python -m pytest -q`

Expected: all tests PASS with no network access.

- [ ] **Step 5: Commit workflow and contract**

```bash
git add .github/workflows/snapshot.yml tests/test_workflow_contract.py
git commit -m "ci: capture trending every two hours"
```

### Task 8: Document operation and perform final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the placeholder README with operator documentation**

Document: purpose and default All languages/Daily scope; Python 3.13 setup using `requirements.lock`; `python -m geektrend.cli`; `python -m pytest -q`; exact JSON schema including nullable optional fields and contributor arrays; `data/YYYY/MM/DD/...` layout; two-hour best-effort schedule and manual dispatch; repository Settings → Actions → General → Workflow permissions → Read and write permissions; concurrency/no-backfill behavior; immutable snapshots; and the risk that undocumented GitHub HTML changes can require selector maintenance. Explicitly say there is no official Trending API and deterministic tests do not call the live site.

- [ ] **Step 2: Run the complete deterministic verification from a clean environment**

Run:

```bash
rm -rf .venv
uv python install 3.13
uv venv --seed --python 3.13 .venv
.venv/bin/python -m pip install --upgrade pip==25.1.1
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest -q
git status --short
```

Expected: dependency install succeeds; all tests PASS; status lists only the intended README change before commit. Do not delete or overwrite any user-owned files if the worktree is not clean—inspect and adapt instead.

- [ ] **Step 3: Run one live smoke collection without polluting tracked data**

Run:

```bash
smoke_root="$(mktemp -d)"
export SMOKE_ROOT="$smoke_root"
.venv/bin/python -m geektrend.cli --output-root "$SMOKE_ROOT" | tee /tmp/geektrend-smoke-path.txt
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

relative = Path(Path('/tmp/geektrend-smoke-path.txt').read_text(encoding='utf-8').strip())
assert not relative.is_absolute() and relative.parts[0] == 'data'
payload = json.loads((Path(os.environ['SMOKE_ROOT']) / relative).read_text(encoding='utf-8'))
assert payload['source_url'] == 'https://github.com/trending/'
assert payload['repository_count'] == len(payload['repositories']) > 0
for repository in payload['repositories']:
    assert repository['repository_name'].count('/') == 1
    assert repository['url'] == f"https://github.com/{repository['repository_name']}"
print(payload['repository_count'])
PY
rm -rf -- "$SMOKE_ROOT"
rm -f -- /tmp/geektrend-smoke-path.txt
```

Expected: CLI prints one `data/YYYY/MM/DD/...json` path; validation prints a positive repository count; the project working tree gains no `data/*.json`. If GitHub is unavailable or its markup has changed, record the live-smoke failure separately; do not weaken deterministic parser validation or create a snapshot.

- [ ] **Step 4: Review the resulting diff and documentation**

Run: `git diff --check && git diff -- README.md && git status --short`

Expected: no whitespace errors; README covers every documented operational requirement; only intended files are pending.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md
git commit -m "docs: explain snapshot collection"
```

- [ ] **Step 6: Final repository verification**

Run: `.venv/bin/python -m pytest -q && git status --short && git log --oneline -8`

Expected: all tests PASS, working tree is clean, and the task commits appear in order. Ask a verifier/reviewer to compare the implementation against `docs/superpowers/specs/2026-07-13-github-trending-snapshot-design.md`; address any issue and rerun the full suite before claiming completion.
