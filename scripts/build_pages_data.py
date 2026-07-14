from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_snapshots(data_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    snapshots: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(data_root.rglob("*.json")):
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if isinstance(payload, dict) and isinstance(payload.get("repositories"), list):
            snapshots.append((path, payload))
    return snapshots


def build_summary(data_root: Path) -> dict[str, Any]:
    snapshots = load_snapshots(data_root)
    if not snapshots:
        return {
            "generated_at": _now(),
            "snapshot_count": 0,
            "latest_snapshot_path": None,
            "latest": None,
            "history": [],
            "agent_leaderboard": [],
            "country_distribution": [],
            "latest_repositories": [],
        }

    history = [
        _snapshot_summary(_display_path(path, data_root), payload)
        for path, payload in snapshots
    ]
    latest_path, latest_payload = snapshots[-1]
    latest_repositories = [
        _repository_summary(repository)
        for repository in latest_payload.get("repositories", [])
    ]

    return {
        "generated_at": _now(),
        "snapshot_count": len(snapshots),
        "latest_snapshot_path": _display_path(latest_path, data_root).as_posix(),
        "latest": history[-1],
        "history": history,
        "agent_leaderboard": _agent_leaderboard(latest_repositories),
        "country_distribution": _country_distribution(latest_repositories),
        "latest_repositories": latest_repositories,
    }


def write_summary(summary: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _snapshot_summary(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    repository_count = _int(payload.get("repository_count"))
    ai_count = _int(payload.get("ai_agent_project_count"))
    ratio = payload.get("ai_agent_project_ratio")
    if not isinstance(ratio, int | float):
        ratio = None
    return {
        "path": path.as_posix(),
        "fetched_at": payload.get("fetched_at"),
        "repository_count": repository_count,
        "ai_agent_project_count": ai_count,
        "ai_agent_project_ratio": ratio,
    }


def _display_path(path: Path, data_root: Path) -> Path:
    try:
        return path.relative_to(data_root.parent)
    except ValueError:
        return path


def _repository_summary(repository: dict[str, Any]) -> dict[str, Any]:
    agents = repository.get("ai_agent_contributors")
    if not isinstance(agents, list):
        agents = []
    contributors = repository.get("contributors")
    if not isinstance(contributors, list):
        contributors = []
    return {
        "repository_name": repository.get("repository_name"),
        "url": repository.get("url"),
        "description": repository.get("description"),
        "primary_language": repository.get("primary_language"),
        "contributor_count": len(contributors),
        "ai_agent_contributors": [agent for agent in agents if isinstance(agent, str)],
        "uses_ai_agent": bool(repository.get("uses_ai_agent")),
        "origin_country": repository.get("origin_country") or "unknown",
        "origin_confidence": repository.get("origin_confidence") or "unknown",
        "origin_evidence": repository.get("origin_evidence") or [],
    }


def _agent_leaderboard(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for repository in repositories:
        for agent in repository["ai_agent_contributors"]:
            counts[agent] += 1
    return [
        {"agent": agent, "project_count": count}
        for agent, count in counts.most_common()
    ]


def _country_distribution(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(
        repository["origin_country"] or "unknown" for repository in repositories
    )
    return [
        {"country": country, "project_count": count}
        for country, count in counts.most_common()
    ]


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("site/data/summary.json"))
    args = parser.parse_args()
    write_summary(build_summary(args.data_root), args.output)


if __name__ == "__main__":
    main()
