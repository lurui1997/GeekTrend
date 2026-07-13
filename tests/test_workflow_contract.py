from __future__ import annotations

import ast
import copy
import os
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/snapshot.yml"


class WorkflowLoader(yaml.SafeLoader):
    """Parse YAML 1.2 booleans without treating the key ``on`` as true."""


WorkflowLoader.yaml_implicit_resolvers = copy.deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for first_character, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[first_character] = [
        resolver
        for resolver in resolvers
        if resolver[0] != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def load_workflow() -> dict[str, object]:
    return yaml.load(WORKFLOW.read_text(), Loader=WorkflowLoader)


def snapshot_steps() -> list[dict[str, object]]:
    workflow = load_workflow()
    return workflow["jobs"]["snapshot"]["steps"]  # type: ignore[index,return-value]


def test_exact_triggers_permissions_and_concurrency() -> None:
    workflow = load_workflow()

    assert workflow["on"] == {
        "schedule": [{"cron": "0 */2 * * *"}],
        "workflow_dispatch": None,
    }
    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"] == {
        "group": "github-trending-snapshot-${{ github.repository }}",
        "cancel-in-progress": False,
    }


def test_runner_action_pins_and_setup_are_exact() -> None:
    workflow = load_workflow()
    job = workflow["jobs"]["snapshot"]  # type: ignore[index]
    assert job["runs-on"] == "ubuntu-latest"

    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert uses == [
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    ]
    assert all(re.fullmatch(r"(?:actions/checkout|actions/setup-python)@[0-9a-f]{40}", use) for use in uses)
    assert job["steps"][0]["with"] == {"fetch-depth": 0}
    assert job["steps"][1]["with"] == {
        "python-version": "3.13",
        "cache": "pip",
        "cache-dependency-path": "requirements.lock",
    }


def test_install_test_collect_and_publish_contract() -> None:
    steps = snapshot_steps()
    assert [step.get("name") for step in steps[2:]] == [
        "Install dependencies",
        "Test",
        "Collect",
        "Publish exact snapshot",
    ]
    assert steps[2]["run"] == (
        "python -m pip install --upgrade pip==25.1.1\n"
        "python -m pip install -r requirements.lock\n"
    )
    assert steps[3]["run"] == "python -m pytest -q"
    assert steps[4] == {
        "name": "Collect",
        "id": "collect",
        "shell": "bash",
        "run": (
            "set -euo pipefail\n"
            'snapshot_path="$(python -m geektrend.cli)"\n'
            "printf 'snapshot_path=%s\\n' \"$snapshot_path\" >> \"$GITHUB_OUTPUT\"\n"
        ),
    }
    assert steps[5]["run"] == (
        'python scripts/publish_snapshot.py "${{ steps.collect.outputs.snapshot_path }}" '
        '--branch "${{ github.ref_name }}"'
    )


def test_collection_failure_does_not_write_an_output(tmp_path: Path) -> None:
    collection = snapshot_steps()[4]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text("#!/bin/sh\nexit 42\n")
    fake_python.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
    }

    result = subprocess.run(
        ["bash", "-c", collection["run"]],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 42
    assert output.read_text() == ""


def test_fixed_unfiltered_url_and_publish_safeguards() -> None:
    workflow_source = WORKFLOW.read_text()
    application_source = "\n".join(
        path.read_text() for path in sorted((ROOT / "src").rglob("*.py"))
    )
    publication_source = (ROOT / "scripts/publish_snapshot.py").read_text()

    assert set(re.findall(r"https://github\.com/trending/?(?:\?[^\s'\"]*)?", application_source)) == {
        "https://github.com/trending/"
    }
    assert "https://github.com/trending" not in workflow_source
    trending_urls = re.findall(r"https://github\.com/trending[^\s'\"]*", application_source)
    assert all("?" not in url and "language=" not in url and "since=" not in url for url in trending_urls)
    assert "MAX_PUSH_ATTEMPTS = 3" in publication_source
    assert '"diff", "--cached", "--name-only"' in publication_source
    assert '"fetch", "--", remote, branch' in publication_source
    assert '["rebase", "--autostash", upstream]' in publication_source
    assert '"diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"' in publication_source
    assert re.search(r"_git\(\"add\", \"--\", relative\)", publication_source)

    publication_tree = ast.parse(publication_source)
    string_literals = {
        node.value
        for node in ast.walk(publication_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert string_literals.isdisjoint({"-A", "--all", ".", "-f", "--force", "--force-with-lease"})

    add_calls = [
        node
        for node in ast.walk(publication_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_git"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "add"
    ]
    assert len(add_calls) == 1
    assert [
        argument.value if isinstance(argument, ast.Constant) else argument.id
        for argument in add_calls[0].args
    ] == ["add", "--", "relative"]


def test_client_request_cannot_add_filters_dynamically() -> None:
    client_source = (ROOT / "src/geektrend/client.py").read_text()
    tree = ast.parse(client_source)
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    assert assignments["TRENDING_URL"] == "https://github.com/trending/"

    get_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
    ]
    assert len(get_calls) == 1
    assert len(get_calls[0].args) == 1
    assert isinstance(get_calls[0].args[0], ast.Name)
    assert get_calls[0].args[0].id == "TRENDING_URL"
    assert {keyword.arg for keyword in get_calls[0].keywords} == {"headers", "timeout"}
