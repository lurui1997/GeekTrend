# GitHub Trending Snapshot Design

## Goal

Build a small, maintainable project that captures GitHub's default Trending repositories every two hours and preserves each run as a JSON snapshot in this repository.

## Scope

The collector reads `https://github.com/trending/` with its default filters: all languages and the daily time range. It records every repository rendered in the list. Language-specific lists, weekly/monthly lists, dashboards, databases, and notifications are outside the initial scope.

## Architecture

The project uses Python 3. A focused HTTP client downloads the Trending HTML, and a parser built with BeautifulSoup converts each repository card into a typed record. A command-line entry point coordinates download, parsing, validation, and snapshot writing.

GitHub Actions runs the command every two hours and also supports manual dispatch. After a successful collection, the workflow commits the newly created snapshot to the repository using the workflow token.

The design avoids browser automation because the required content is present in the returned HTML. It avoids a GitHub API dependency because GitHub does not provide an official Trending API.

## Data Model

Snapshots are stored at:

```text
data/YYYY/MM/DD/YYYY-MM-DDTHH-MM-SSZ.json
```

Each snapshot contains:

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
      "description": "Repository description",
      "language": "Python"
    }
  ]
}
```

Missing descriptions and languages are represented as `null`. A repository may have an empty contributors list when GitHub does not render “Built by” entries.

JSON is UTF-8, pretty-printed, and ends with a newline so snapshots remain readable and diff-friendly.

## Collection Flow

1. Send an HTTP GET request with an explicit user agent and timeout.
2. Require a successful HTTP response.
3. Parse all Trending repository cards.
4. Normalize relative GitHub links into absolute HTTPS URLs.
5. Validate that at least one repository was parsed and that every repository has a name and canonical URL.
6. Write the completed snapshot atomically, creating date directories as needed.
7. In GitHub Actions, commit only when a new snapshot file exists.

The timestamp is generated in UTC. Separate runs produce separate files. If a manually retried run uses the same second-level timestamp, the command refuses to overwrite the existing snapshot.

## Failure Handling

Network errors, timeouts, non-success responses, empty result sets, malformed required fields, and write failures make the command exit non-zero. No empty or partially written snapshot is committed. Optional fields remain nullable rather than failing the entire run.

Parser selectors are kept in one module so adaptations to GitHub markup remain localized. Error messages identify whether failure occurred during fetching, parsing, validation, or writing.

## Automation

The workflow uses a two-hour cron schedule and `workflow_dispatch`. It grants only `contents: write`, installs pinned project dependencies, runs the test suite, executes the collector, and commits the generated data with a bot identity.

Because GitHub Actions cron schedules are best-effort, a run may start later than its nominal time. The snapshot records the actual fetch time rather than the scheduled time.

Concurrent workflow runs are grouped to avoid simultaneous commits. The workflow pulls/rebases before pushing when needed, and fails visibly if it cannot safely publish the snapshot.

## Testing

Parser tests use checked-in HTML fixtures rather than the live website. Tests cover complete cards, missing optional fields, contributor extraction, URL normalization, multiple repositories, and an empty/changed page.

Writer tests verify the directory layout, JSON schema, UTF-8 output, and overwrite protection. Coordinator tests use a fake HTTP response or mocked fetcher to verify successful collection and failure behavior without network access.

A live collection can be run manually for smoke testing, but it is not required for deterministic automated tests.

## Documentation

The README explains local setup, manual collection, tests, snapshot structure, GitHub Actions scheduling, the required workflow write permission, and the limitations of scraping an undocumented page structure.

## Success Criteria

- The default GitHub Trending page is collected into the documented JSON schema.
- Contributors include usernames and GitHub profile links when present.
- A new UTC-stamped snapshot is scheduled every two hours.
- Failed or empty collections never create committed snapshots.
- Tests exercise parsing, validation, and file output without relying on live GitHub availability.
