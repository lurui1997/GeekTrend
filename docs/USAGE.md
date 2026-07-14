# GeekTrend Usage Guide

This guide explains how to run GeekTrend locally, understand generated
snapshots, and operate the scheduled GitHub Actions collector.

## What GeekTrend Collects

GeekTrend captures GitHub Trending's default view:

- source: `https://github.com/trending/`
- language filter: all languages
- time range: daily
- schedule: every 2 hours through GitHub Actions
- snapshot time zone: UTC+08:00

Each snapshot stores repository basics, contributor usernames, AI-agent
contributor detection, inferred project origin, and the overall AI-agent project
ratio for that run.

## Local Setup

Use Python 3.13 and install the pinned dependencies:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

Run the offline test suite:

```sh
python -m pytest -q
```

## Run One Collection Manually

Collect into the repository:

```sh
python -m geektrend.cli
```

Collect into a temporary directory for a smoke test:

```sh
python -m geektrend.cli --output-root /tmp/geektrend-smoke
```

The command prints a repository-relative snapshot path, for example:

```text
data/2026/07/14/2026-07-14T10-00-00+08-00.json
```

## Read The Latest Snapshot

You can also open the live GitHub Pages report:

```text
https://lurui1997.github.io/GeekTrend/
```

The report visualizes the latest AI-agent adoption ratio, agent leaderboard,
project-origin distribution, and repository table. It is rebuilt automatically
after a successful scheduled snapshot run.

Find the newest local snapshot:

```sh
find data -type f -name '*.json' | sort | tail -1
```

Print top-level AI-agent adoption stats:

```sh
export latest="$(find data -type f -name '*.json' | sort | tail -1)"
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(Path(os.environ["latest"]).read_text())
print("snapshot:", os.environ["latest"])
print("repositories:", data["repository_count"])
print("AI-agent projects:", data.get("ai_agent_project_count", "n/a"))
print("AI-agent ratio:", data.get("ai_agent_project_ratio", "n/a"))
PY
```

List projects that used a known AI agent contributor:

```sh
export latest="$(find data -type f -name '*.json' | sort | tail -1)"
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path

data = json.loads(Path(os.environ["latest"]).read_text())
for repo in data["repositories"]:
    if repo.get("uses_ai_agent"):
        agents = ", ".join(repo["ai_agent_contributors"])
        print(f"{repo['repository_name']}: {agents}")
PY
```

## Understand Contributor Analysis

GeekTrend identifies AI-agent contributors by username. The current known agent
set includes:

- `claude`
- `codex`
- `cursor`
- `github-copilot`
- `copilot`

Dependabot is intentionally not counted as an AI coding agent.

Origin analysis is best-effort. GeekTrend reads public GitHub profile fields
such as `location`, `company`, and `bio` from human contributors. The result is
an inferred project origin, not a claim about nationality.

Confidence values mean:

| Confidence | Meaning |
|---|---|
| `high` | The repository owner profile provides the origin signal |
| `medium` | Multiple human contributors point to the same origin |
| `low` | One non-owner human contributor provides the only usable signal |
| `unknown` | No reliable public profile signal is available |

If GitHub profile requests fail, the collection still succeeds and the origin
fields degrade to `unknown`.

## Scheduled Automation

The workflow lives at `.github/workflows/snapshot.yml` and is named
`Capture GitHub Trending`.

It runs on:

```yaml
schedule:
  - cron: "0 */2 * * *"
workflow_dispatch:
```

GitHub cron is evaluated in UTC. Snapshot filenames and `fetched_at` values are
stored in UTC+08:00.

The workflow needs repository write permission so it can commit new snapshots.
In GitHub, check:

```text
Settings → Actions → General → Workflow permissions → Read and write permissions
```

The workflow passes `GITHUB_TOKEN` to the collector so profile enrichment uses
the Actions API quota instead of anonymous GitHub API limits.

## Troubleshooting

If no new snapshot appears:

1. Open the `Capture GitHub Trending` workflow in GitHub Actions.
2. Check whether the scheduled run started; GitHub schedules are best effort.
3. Check the `Test`, `Collect`, and `Publish exact snapshot` steps.
4. Confirm workflow permissions are set to `contents: write`.

Common failure modes:

| Symptom | Likely Cause |
|---|---|
| `Author identity unknown` | The workflow did not configure the Git commit author |
| Push rejected | Another scheduled run committed first; bounded retry should handle normal races |
| No origin country | Public contributor profile signals were missing or unavailable |
| Parse failure | GitHub changed Trending page markup |

Successful snapshots are immutable. The publisher never overwrites an existing
snapshot path and does not backfill missed schedule windows.
