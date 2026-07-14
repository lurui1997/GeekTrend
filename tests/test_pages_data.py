from __future__ import annotations

import json
from pathlib import Path

from scripts.build_pages_data import build_summary, write_summary


def _write_snapshot(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_summary_returns_empty_shape_without_snapshots(tmp_path: Path) -> None:
    summary = build_summary(tmp_path / "data")

    assert summary["snapshot_count"] == 0
    assert summary["latest"] is None
    assert summary["history"] == []
    assert summary["agent_leaderboard"] == []
    assert summary["country_distribution"] == []
    assert summary["latest_repositories"] == []


def test_build_summary_handles_old_and_analyzed_snapshots(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_snapshot(
        data_root / "2026/07/13/old.json",
        {
            "fetched_at": "2026-07-13T13:14:01Z",
            "repository_count": 1,
            "repositories": [
                {
                    "repository_name": "old/project",
                    "url": "https://github.com/old/project",
                    "contributors": [],
                    "description": "before analysis",
                    "primary_language": "Python",
                }
            ],
        },
    )
    _write_snapshot(
        data_root / "2026/07/14/new.json",
        {
            "fetched_at": "2026-07-14T09:11:23+08:00",
            "repository_count": 2,
            "ai_agent_project_count": 1,
            "ai_agent_project_ratio": 0.5,
            "repositories": [
                {
                    "repository_name": "agent/project",
                    "url": "https://github.com/agent/project",
                    "contributors": [{"username": "claude", "url": "https://github.com/claude"}],
                    "description": "uses agent",
                    "primary_language": "TypeScript",
                    "ai_agent_contributors": ["claude"],
                    "uses_ai_agent": True,
                    "origin_country": "United States",
                    "origin_confidence": "high",
                    "origin_evidence": ["owner: location=San Francisco"],
                },
                {
                    "repository_name": "human/project",
                    "url": "https://github.com/human/project",
                    "contributors": [{"username": "human", "url": "https://github.com/human"}],
                    "description": "no agent",
                    "primary_language": "Go",
                    "ai_agent_contributors": [],
                    "uses_ai_agent": False,
                    "origin_country": "China",
                    "origin_confidence": "medium",
                    "origin_evidence": ["contributors: location=Shanghai"],
                },
            ],
        },
    )

    summary = build_summary(data_root)

    assert summary["snapshot_count"] == 2
    assert summary["latest_snapshot_path"] == "data/2026/07/14/new.json"
    assert summary["latest"]["ai_agent_project_ratio"] == 0.5
    assert summary["history"][0]["ai_agent_project_count"] is None
    assert summary["agent_leaderboard"] == [{"agent": "claude", "project_count": 1}]
    assert summary["country_distribution"] == [
        {"country": "United States", "project_count": 1},
        {"country": "China", "project_count": 1},
    ]
    assert summary["latest_repositories"][0]["contributor_count"] == 1


def test_write_summary_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "site/data/summary.json"

    write_summary({"snapshot_count": 0}, output)

    assert json.loads(output.read_text(encoding="utf-8")) == {"snapshot_count": 0}
