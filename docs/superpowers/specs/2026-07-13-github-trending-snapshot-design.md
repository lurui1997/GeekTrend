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
data/YYYY/MM/DD/YYYY-MM-DDTHH-MM-SS+08-00.json
```

Each snapshot contains:

```json
{
  "fetched_at": "2026-07-13T10:00:00+08:00",
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
      "primary_language": "Python"
    }
  ]
}
```

Missing descriptions and primary languages are represented as `null`. `primary_language` is the language displayed by GitHub on the Trending card. A repository may have an empty contributors list when GitHub does not render “Built by” entries.

JSON is UTF-8, pretty-printed, and ends with a newline so snapshots remain readable and diff-friendly.

## Collection Flow

1. Send an HTTP GET request with an explicit user agent and timeout.
2. Require a successful HTTP response.
3. Parse all Trending repository cards.
4. Normalize relative GitHub links into absolute HTTPS URLs.
5. Validate that at least one repository was parsed. Each name must have exactly the `owner/repository` shape, and its URL must be the corresponding `https://github.com/{owner}/{repository}` URL with no query or fragment. Contributor entries must have a non-empty username and matching `https://github.com/{username}` profile URL. Duplicate repository names make the collection fail rather than being silently merged.
6. Write the completed snapshot atomically, creating date directories as needed.
7. In GitHub Actions, commit only when a new snapshot file exists.

The timestamp is generated in UTC+08:00. Every successful collection is preserved as a separate immutable file. Failed, delayed, or missed scheduled runs are not backfilled, and history is never overwritten or rewritten. If a manually retried run uses the same second-level timestamp, the command refuses to overwrite the existing snapshot.

## Failure Handling

Network errors, timeouts, non-success responses, empty result sets, malformed required fields, and write failures make the command exit non-zero. No empty or partially written snapshot is committed. Optional fields remain nullable rather than failing the entire run.

Parser selectors are kept in one module so adaptations to GitHub markup remain localized. Error messages identify whether failure occurred during fetching, parsing, validation, or writing.

## Automation

The workflow uses the two-hour `0 */2 * * *` cron schedule and `workflow_dispatch`. It requests only `contents: write`. It installs a fixed Python minor version and exact direct and transitive dependency versions from a committed lock file; third-party actions are pinned to immutable full commit SHAs. Tests run before collection, and publication happens only after both steps succeed.

Because GitHub Actions cron schedules are best-effort, a run may start later than its nominal time. The snapshot records the actual fetch time rather than the scheduled time.

Workflow concurrency uses a repository-wide group such as `github-trending-snapshot-${{ github.repository }}` with `cancel-in-progress: false`, serializing scheduled and manual runs without discarding an active collection.

The collector prints or exposes the exact relative path it created. Publication stages only that path, never `git add .` or unrelated workspace files. It commits with a bot identity and attempts a normal push. On a non-fast-forward rejection, it fetches the remote branch, rebases the already-created snapshot commit onto it, verifies that the rebased commit still changes exactly the intended snapshot path, and retries the push a bounded number of times. It exits non-zero if safe publication remains impossible. No force push is allowed.

## Testing

Parser tests use checked-in HTML fixtures rather than the live website. Tests cover complete cards, missing optional fields, contributor extraction, URL normalization, multiple repositories, duplicate repositories, malformed repository/contributor identities, and an empty or structurally changed page.

Writer tests verify the directory layout, JSON schema, UTF-8 output, and overwrite protection. Fault-injection tests prove that serialization, write, flush, and atomic-rename failures leave no destination snapshot and clean up temporary artifacts so nothing partial can be committed. Coordinator tests use a fake HTTP response or mocked fetcher to verify successful collection and failure behavior without network access.

Automation contract tests parse the workflow and supporting publish script to verify the two-hour cron, manual dispatch, serialized non-canceling concurrency, UTC+08:00-stamped output, test-before-collection ordering, exact-file staging, bounded push retry, and non-zero conflict behavior.

A live collection can be run manually for smoke testing, but it is not required for deterministic automated tests.

## Documentation

The README explains local setup, manual collection, tests, snapshot structure, GitHub Actions scheduling, the required workflow write permission, and the limitations of scraping an undocumented page structure.

## Success Criteria

- The default GitHub Trending page is collected into the documented JSON schema.
- Contributors include usernames and GitHub profile links when present.
- A new UTC+08:00-stamped snapshot is scheduled every two hours.
- Failed or empty collections never create committed snapshots.
- Tests exercise parsing, validation, and file output without relying on live GitHub availability.
