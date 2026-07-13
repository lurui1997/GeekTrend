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

The command prints the relative path it created. Snapshots live at `data/YYYY/MM/DD/YYYY-MM-DDTHH-MM-SSZ.json`. Run the deterministic, offline test suite with:

```sh
python -m pytest -q
```

## Snapshot format

Every file has this exact shape:

```json
{
  "fetched_at": "2026-07-13T02:00:00Z",
  "source_url": "https://github.com/trending/",
  "repository_count": 1,
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
      "primary_language": null
    }
  ]
}
```

`fetched_at` is UTC at whole-second precision. `repository_count` equals the length of `repositories`; repository and contributor URLs are canonical GitHub URLs. `contributors` is always an array (possibly empty). `description` and `primary_language` are the only nullable fields.

## Automation and operating constraints

The `Capture GitHub Trending` Actions workflow is scheduled every two hours and can also be run manually. GitHub schedules are best effort, so a delayed or skipped run is not backfilled. Repository Actions settings must grant workflows **Read and write permissions** (`contents: write`) so a successful snapshot can be committed and pushed.

One concurrency group serializes runs without cancelling an in-progress collection. Publication retries a bounded number of push races, never overwrites or backfills an existing path, and treats every successfully published snapshot as immutable.

GitHub provides no official Trending API. This project parses the public Trending HTML, so GitHub markup changes can break collection; failures leave no snapshot. Tests use local fixtures and never require the network.

The writer publishes atomically with a hard link to guarantee no-overwrite behavior. The output root and its temporary file must therefore be on a filesystem that supports hard links.
