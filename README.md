# GeekTrend

GeekTrend records immutable JSON snapshots of GitHub Trending. Each collection uses GitHub's default **All languages** and **Daily** view; the collector intentionally exposes no language or time-range filters.

## Install and run

Python 3.13 is required. Create an isolated environment and install the fully pinned lock file:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

Collect into the current directory, or select another root for a smoke test:

```sh
python -m geektrend.cli
python -m geektrend.cli --output-root /tmp/geektrend-smoke
```

The command prints the relative path it created. Snapshots use UTC+08:00 time and live at `data/YYYY/MM/DD/YYYY-MM-DDTHH-MM-SS+08-00.json`. Run the deterministic, offline test suite with:

```sh
python -m pytest -q
```

## Snapshot format

Every file has this exact shape:

```json
{
  "fetched_at": "2026-07-13T10:00:00+08:00",
  "source_url": "https://github.com/trending/",
  "repository_count": 1,
  "ai_agent_project_count": 1,
  "ai_agent_project_ratio": 1.0,
  "repositories": [
    {
      "repository_name": "owner/repository",
      "url": "https://github.com/owner/repository",
      "contributors": [
        {
          "username": "octocat",
          "url": "https://github.com/octocat"
        }
      ],
      "description": null,
      "primary_language": null,
      "ai_agent_contributors": ["claude"],
      "uses_ai_agent": true,
      "origin_country": "United States",
      "origin_confidence": "high",
      "origin_evidence": ["owner: location=New York City, NY"]
    }
  ]
}
```

`fetched_at` is UTC+08:00 at whole-second precision. `repository_count` equals the length of `repositories`; repository and contributor URLs are canonical GitHub URLs. `contributors` is always an array (possibly empty). `description` and `primary_language` are the only nullable fields.

Contributor analysis is best-effort and uses public GitHub profile fields. `ai_agent_contributors` records known AI coding agent usernames such as `claude`, `codex`, `cursor`, `github-copilot`, and `copilot`; Dependabot is not counted as an AI coding agent. `origin_country` is an inferred project origin, not a claim about nationality. `origin_confidence` is `high` when the owner profile provides the signal, `medium` when multiple human contributors agree, `low` for a single non-owner signal, and `unknown` when no usable public signal is available. `ai_agent_project_ratio` is the share of repositories in the snapshot where `uses_ai_agent` is true.

## Automation and operating constraints

The `Capture GitHub Trending` Actions workflow is scheduled every two hours and can also be run manually. GitHub schedules are best effort, so a delayed or skipped run is not backfilled. In the repository, select **Settings → Actions → General → Workflow permissions → Read and write permissions** (`contents: write`) so a successful snapshot can be committed and pushed. The workflow passes `GITHUB_TOKEN` to the collector so GitHub profile enrichment uses the repository's Actions API quota.

One concurrency group serializes runs without cancelling an in-progress collection. Publication retries a bounded number of push races, never overwrites or backfills an existing path, and treats every successfully published snapshot as immutable.

GitHub provides no official Trending API. This project parses the public Trending HTML, so GitHub markup changes can break collection; failures leave no snapshot. Tests use local fixtures and never require the network.

The writer publishes atomically with a hard link to guarantee no-overwrite behavior. The output root and its temporary file must therefore be on a filesystem that supports hard links.
