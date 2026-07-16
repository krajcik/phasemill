#!/usr/bin/env bash
set -euo pipefail

# Install the local marketplace into a clean Codex home and exercise only the
# installed copies. The Python body keeps JSON parsing and fixture assertions
# deterministic without jq or third-party packages.
exec python3 - "$0" "$@" <<'PY'
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


SCRIPT = Path(sys.argv[1]).resolve()
DEFAULT_REPO = SCRIPT.parents[2]
MARKETPLACE = "phasemill"
EXPECTED_SKILLS = {
    "phasemill": {
        "ask-codex",
        "brainstorm",
        "clarify",
        "config",
        "dialectic",
        "git-review",
        "learn",
        "lazy",
        "md-copy",
        "plan",
        "plan-review",
        "pr-review",
        "release",
        "root-cause-investigator",
        "run",
        "status",
        "txt-copy",
        "unreleased",
        "writing-style",
        "wrong",
    },
}


class SmokeError(RuntimeError):
    pass


def run(
    argv: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    expected: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(part) for part in argv],
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in expected:
        command = " ".join(str(part) for part in argv)
        raise SmokeError(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def run_json(argv: list[str | Path], **kwargs: Any) -> dict[str, Any]:
    result = run(argv, **kwargs)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"invalid JSON from {' '.join(map(str, argv))}: {exc}") from exc
    if not isinstance(value, dict):
        raise SmokeError(f"expected JSON object from {' '.join(map(str, argv))}")
    return value


def git(repo: Path, *args: str) -> str:
    return run(["git", "-C", repo, *args]).stdout.strip()


def init_repo(path: Path, *, plan_name: str) -> Path:
    path.mkdir(parents=True)
    run(["git", "init", "-b", "main"], cwd=path)
    git(path, "config", "user.email", "codex-smoke@example.invalid")
    git(path, "config", "user.name", "Codex Smoke")
    git(path, "config", "core.excludesFile", "/dev/null")
    (path / "README.md").write_text("# Codex plugin smoke fixture\n", encoding="utf-8")
    (path / ".gitignore").write_text("/.phasemill/runs/\n", encoding="utf-8")
    plan = path / "docs/plans" / plan_name
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# Smoke plan\n\n"
        "## Overview\n\nExercise the installed planning package.\n\n"
        "### Task 1: Produce fixture output\n\n"
        "- [ ] create `result.txt`\n"
        "- [ ] validate the fixture result\n",
        encoding="utf-8",
    )
    git(path, "add", ".gitignore", "README.md", str(plan.relative_to(path)))
    git(path, "commit", "-m", "fixture")
    return plan


def frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise SmokeError(f"missing YAML frontmatter: {path}")
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "name":
            return value.strip()
    raise SmokeError(f"missing skill name in frontmatter: {path}")


def verify_install(codex: str, repo: Path, codex_home: Path) -> dict[str, Path]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    codex_home.mkdir(parents=True)

    added = run_json([codex, "plugin", "marketplace", "add", repo, "--json"], env=env)
    if added.get("marketplaceName") != MARKETPLACE:
        raise SmokeError(f"unexpected marketplace name: {added}")

    available = run_json(
        [codex, "plugin", "list", "--marketplace", MARKETPLACE, "--available", "--json"],
        env=env,
    ).get("available", [])
    available_names = {item.get("name") for item in available if isinstance(item, dict)}
    if available_names != set(EXPECTED_SKILLS):
        raise SmokeError(f"available plugin mismatch: {sorted(available_names)}")

    installed_roots: dict[str, Path] = {}
    for plugin in EXPECTED_SKILLS:
        result = run_json([codex, "plugin", "add", f"{plugin}@{MARKETPLACE}", "--json"], env=env)
        if result.get("name") != plugin:
            raise SmokeError(f"installed wrong plugin for {plugin}: {result}")
        root = Path(str(result.get("installedPath", ""))).resolve()
        if not root.is_dir():
            raise SmokeError(f"installed cache missing for {plugin}: {root}")
        installed_roots[plugin] = root

    listing = run_json([codex, "plugin", "list", "--json"], env=env)
    installed = listing.get("installed", [])
    by_name = {item.get("name"): item for item in installed if isinstance(item, dict)}
    if set(by_name) != set(EXPECTED_SKILLS):
        raise SmokeError(f"installed plugin mismatch: {sorted(by_name)}")
    for plugin, item in by_name.items():
        if item.get("installed") is not True or item.get("enabled") is not True:
            raise SmokeError(f"plugin is not installed and enabled: {plugin}")

    discovered: set[str] = set()
    for plugin, expected in EXPECTED_SKILLS.items():
        root = installed_roots[plugin]
        manifest_path = root / ".codex-plugin/plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != plugin:
            raise SmokeError(f"manifest mismatch in installed cache: {plugin}")
        skill_path = manifest.get("skills")
        if not isinstance(skill_path, str) or not skill_path.startswith("./"):
            raise SmokeError(f"invalid installed skill path for {plugin}: {skill_path}")
        skill_root = (root / skill_path).resolve()
        try:
            skill_root.relative_to(root)
        except ValueError as exc:
            raise SmokeError(f"installed skill path escapes plugin root: {plugin}") from exc
        skill_files = list(skill_root.glob("*/SKILL.md"))
        actual = {frontmatter_name(path) for path in skill_files}
        if actual != expected:
            raise SmokeError(f"skill name mismatch for {plugin}: {sorted(actual)}")
        for path in skill_files:
            name = frontmatter_name(path)
            if name in discovered:
                raise SmokeError(f"duplicate global skill name: {name}")
            discovered.add(name)

    expected_all = set().union(*EXPECTED_SKILLS.values())
    if discovered != expected_all:
        raise SmokeError(f"discovered skill mismatch: {sorted(discovered)}")

    phasemill_root = installed_roots["phasemill"]
    hook_path = (phasemill_root / "hooks/hooks.json").resolve()
    hooks = json.loads(hook_path.read_text(encoding="utf-8"))
    if "UserPromptSubmit" not in hooks.get("hooks", {}):
        raise SmokeError("installed Phasemill hook is not wired to UserPromptSubmit")
    if "SessionStart" not in hooks.get("hooks", {}):
        raise SmokeError("installed Phasemill hook is not wired to SessionStart")

    mcp = json.loads((phasemill_root / ".mcp.json").read_text(encoding="utf-8"))
    if "phasemill" not in mcp.get("mcpServers", {}):
        raise SmokeError("installed Phasemill MCP server is not declared")

    return installed_roots


def assert_mutation_guards(installed: dict[str, Path]) -> None:
    root = installed["phasemill"]
    checks = {
        root / "skills/run/SKILL.md": (
            "Do not commit, push, rebase, publish, deploy",
            "explicit approval before calling `worktree.sh prepare`",
        ),
        root / "skills/release/SKILL.md": (
            "Ask for explicit approval of this exact preview",
            "Abort on drift",
        ),
        root / "skills/pr-review/SKILL.md": (
            "require the user's explicit approval",
            "Approval to post a review does not authorize merging",
        ),
        root / "skills/learn/SKILL.md": (
            "ask which candidate numbers to apply",
            "ask for approval before writing",
        ),
        root / "skills/lazy/SKILL.md": (
            "plan_write_mode=create-exclusive",
            "worktree.sh lazy-plan",
            "lazy-stage.py checkpoint",
            "never push",
            "never start a second run",
            "never applies `.codex/phasemill/`",
        ),
    }
    for path, phrases in checks.items():
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                raise SmokeError(f"missing mutation guard in {path}: {phrase}")


def verify_planning_pipeline(installed: dict[str, Path], root: Path) -> None:
    planning = installed["phasemill"]
    fixture = root / "planning-fixture"
    plan = init_repo(fixture, plan_name="20260715-smoke.md")
    config_dir = fixture / ".codex/phasemill"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        "[review.external]\nbackend = \"none\"\n\n"
        "[finalize]\nenabled = false\n\n"
        "[plans]\nmove_on_completion = false\n",
        encoding="utf-8",
    )

    config = planning / "engine/config.py"
    plan_state = planning / "engine/plan_state.py"
    controller = planning / "engine/phase_controller.py"
    run([sys.executable, config, "--project-root", fixture, "validate"])
    inspected = run_json([sys.executable, plan_state, "--project-root", fixture, "inspect", plan])
    if inspected.get("next_task", {}).get("identifier") != "1":
        raise SmokeError(f"Phasemill plan fixture is not actionable: {inspected}")

    base = [sys.executable, controller, "--project-root", fixture, "--default-branch", "main"]
    head_before = git(fixture, "rev-parse", "HEAD")
    branch_before = git(fixture, "branch", "--show-current")

    first = run_json([*base, "start", plan])
    if first.get("kind") != "task" or first.get("max_parallel_agents") != 1:
        raise SmokeError(f"first action is not a sequential task: {first}")
    if first.get("agent", {}).get("model") != "gpt-5.6-sol":
        raise SmokeError(f"task action lost its native model profile: {first}")
    if first.get("agent", {}).get("model_reasoning_effort") != "medium":
        raise SmokeError(f"task action lost its native reasoning profile: {first}")
    resumed = run_json([*base, "next", plan])
    if resumed.get("action_id") != first.get("action_id"):
        raise SmokeError("interrupted task did not resume the same revision-bound action")

    retry = run_json(
        [*base, "record", plan, "--action-id", str(first["action_id"])],
        input_text=json.dumps({"outcome": "failed", "summary": "synthetic retry"}),
    )
    if retry.get("kind") != "task" or retry.get("action_id") == first.get("action_id"):
        raise SmokeError(f"task retry policy did not advance revision: {retry}")
    if retry.get("agent", {}).get("model_reasoning_effort") != "xhigh":
        raise SmokeError(f"task retry did not escalate to the recovery profile: {retry}")
    retry_resumed = run_json([*base, "next", plan])
    if retry_resumed.get("action_id") != retry.get("action_id"):
        raise SmokeError("retry action was not restart-stable")

    (fixture / "result.txt").write_text("installed planning pipeline passed\n", encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8")
    first_review = run_json(
        [*base, "record", plan, "--action-id", str(retry["action_id"])],
        input_text=json.dumps({"outcome": "completed", "summary": "fixture task completed"}),
    )
    if first_review.get("kind") != "review" or first_review.get("phase") != "review-first":
        raise SmokeError(f"task did not advance to first review: {first_review}")
    if first_review.get("max_parallel_agents", 0) < 2 or len(first_review.get("roles", [])) < 2:
        raise SmokeError("first review does not expose bounded parallel read-only roles")
    required_runtime = {"model", "model_reasoning_effort"}
    if any(not required_runtime.issubset(role.get("agent", {})) for role in first_review["roles"]):
        raise SmokeError("first review lost per-role native runtime profiles")
    if run_json([*base, "next", plan]).get("action_id") != first_review.get("action_id"):
        raise SmokeError("first review did not survive process restart")

    critical_review = run_json(
        [*base, "record", plan, "--action-id", str(first_review["action_id"])],
        input_text=json.dumps({"outcome": "findings", "summary": "first review findings fixed"}),
    )
    if critical_review.get("kind") != "review" or critical_review.get("phase") != "review":
        raise SmokeError(f"first review did not enter convergence review: {critical_review}")
    if critical_review.get("max_parallel_agents") != 2:
        raise SmokeError("critical review concurrency is not bounded to two")

    learning = run_json(
        [*base, "record", plan, "--action-id", str(critical_review["action_id"])],
        input_text=json.dumps({"outcome": "clean", "summary": "critical review clean"}),
    )
    if learning.get("kind") != "learning" or learning.get("prompt_name") != "learning":
        raise SmokeError(f"planning pipeline did not enter proposal-only learning: {learning}")
    if ".codex/phasemill/" not in learning.get("prompt", ""):
        raise SmokeError("learning action lost its project-scope allowlist")
    if "${PLUGIN_DATA}/profiles/<language>.md" not in learning.get("prompt", ""):
        raise SmokeError("learning action lost its explicit user-global language scope")
    if "Only when the user explicitly asks" not in learning.get("prompt", ""):
        raise SmokeError("learning action can promote global guidance without an explicit request")
    done = run_json(
        [*base, "record", plan, "--action-id", str(learning["action_id"])],
        input_text=json.dumps({"outcome": "clean", "summary": "no durable learning signals"}),
    )
    if done.get("kind") != "done" or done.get("reason") != "completed":
        raise SmokeError(f"planning pipeline did not complete: {done}")
    unexpected_scope_writes = [
        path
        for path in config_dir.rglob("*")
        if path.is_file() and path.name != "config.toml"
    ]
    if unexpected_scope_writes:
        raise SmokeError(f"proposal-only learning mutated project scope: {unexpected_scope_writes}")
    state = run_json([*base, "show", plan]).get("state", {})
    if state.get("status") != "completed" or state.get("task_retry_count") != 0:
        raise SmokeError(f"durable completed state is invalid: {state}")

    run_files = list((fixture / ".phasemill/runs").glob("*"))
    if not any(path.suffix == ".json" for path in run_files):
        raise SmokeError("durable JSON run state was not created")
    if not any(path.suffix == ".md" for path in run_files):
        raise SmokeError("human-readable progress log was not created")
    if ".phasemill/runs" in git(fixture, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SmokeError("runtime state polluted the implementation status")
    if git(fixture, "rev-parse", "HEAD") != head_before:
        raise SmokeError("planning pipeline created a commit without approval")
    if git(fixture, "branch", "--show-current") != branch_before:
        raise SmokeError("planning pipeline switched the main branch")
    if git(fixture, "remote"):
        raise SmokeError("fixture unexpectedly gained a remote")


def verify_lazy_pipeline(installed: dict[str, Path], root: Path) -> None:
    phasemill = installed["phasemill"]
    fixture = root / "lazy-fixture"
    init_repo(fixture, plan_name="20260715-existing.md")
    origin_config = fixture / ".codex/phasemill/config.toml"
    origin_config.parent.mkdir(parents=True)
    origin_config.write_text(
        "[review.external]\nbackend = \"none\"\n\n"
        "[plans]\nmove_on_completion = false\n",
        encoding="utf-8",
    )
    git(fixture, "add", ".codex/phasemill/config.toml")
    git(fixture, "commit", "-m", "lazy fixture config")
    remote = root / "lazy-remote.git"
    run(["git", "init", "--bare", remote])
    git(fixture, "remote", "add", "origin", str(remote))
    lazy = phasemill / "engine/lazy_controller.py"
    worktree_helper = phasemill / "scripts/worktree.sh"
    stage_helper = phasemill / "scripts/lazy-stage.py"
    run_controller = phasemill / "engine/phase_controller.py"
    lazy_base = [sys.executable, lazy, "--project-root", fixture]
    head_before = git(fixture, "rev-parse", "HEAD")
    branch_before = git(fixture, "branch", "--show-current")

    action = run_json(
        [
            *lazy_base,
            "start",
            "--request-id",
            "installed-lazy-smoke-request",
            "--idea",
            "Add a retry result fixture",
        ]
    )
    if action.get("kind") != "worktree":
        raise SmokeError(f"lazy journey did not start with early worktree: {action}")
    replay = run_json(
        [
            *lazy_base,
            "start",
            "--request-id",
            "installed-lazy-smoke-request",
            "--idea",
            "Add a retry result fixture",
        ]
    )
    if replay.get("action_id") != action.get("action_id"):
        raise SmokeError("lost lazy_start response did not replay the same action")
    journey_id = str(action["action_id"]).split(":", 1)[0]

    prepared = parse_kv(
        run(
            [
                worktree_helper,
                "lazy-prepare",
                "--repo",
                fixture,
                "--journey-id",
                journey_id,
                "--head",
                str(action["origin_head"]),
            ]
        ).stdout
    )
    execution = Path(prepared["project_root"])
    if prepared.get("status") != "created" or not execution.is_dir():
        raise SmokeError(f"lazy early worktree was not created: {prepared}")
    reused = parse_kv(
        run(
            [
                worktree_helper,
                "lazy-prepare",
                "--repo",
                fixture,
                "--journey-id",
                journey_id,
                "--head",
                str(action["origin_head"]),
            ]
        ).stdout
    )
    if reused.get("status") != "reused" or Path(reused["project_root"]) != execution:
        raise SmokeError("lazy worktree replay did not reuse exact coordinates")

    def lazy_record(result: dict[str, Any]) -> dict[str, Any]:
        nonlocal action
        action = run_json(
            [*lazy_base, "record", journey_id, "--action-id", str(action["action_id"])],
            input_text=json.dumps(result),
        )
        return action

    def checkpoint(action_id: str, base_head: str, message: str, *paths: str) -> dict[str, Any]:
        command = [
            sys.executable,
            stage_helper,
            "checkpoint",
            "--project-root",
            execution,
            "--action-id",
            action_id,
            "--message",
            message,
            "--expected-head",
            base_head,
        ]
        for path in paths:
            command.extend(["--path", path])
        return run_json(command)

    lazy_record(
        {
            "outcome": "completed",
            "execution_project_root": str(execution),
            "execution_branch": prepared["branch"],
        }
    )
    if action.get("kind") != "bootstrap-config":
        raise SmokeError(f"lazy worktree did not advance to config bootstrap: {action}")
    config_action = str(action["action_id"])
    config_head = git(execution, "rev-parse", "HEAD")
    consent = run_json([sys.executable, stage_helper, "consent", "--project-root", execution])
    if consent.get("status") != "updated":
        raise SmokeError(f"lazy consent was not bootstrapped: {consent}")
    config_commit = checkpoint(
        config_action,
        config_head,
        "chore(phasemill): initialize lazy workflow",
        ".codex/phasemill/config.toml",
    )
    if config_commit.get("status") != "committed":
        raise SmokeError(f"lazy config stage did not commit: {config_commit}")
    replayed = checkpoint(
        config_action,
        config_head,
        "chore(phasemill): initialize lazy workflow",
        ".codex/phasemill/config.toml",
    )
    if replayed.get("status") != "reused" or replayed.get("head") != config_commit.get("head"):
        raise SmokeError("lazy config crash replay created or selected another commit")
    lazy_record({"outcome": "completed", "summary": "installed consent bootstrap complete"})

    lazy_record(
        {
            "outcome": "completed",
            "summary": "installed discovery complete",
            "scope_paths": ["src", "tests"],
        }
    )
    if action.get("kind") != "design":
        raise SmokeError(f"lazy discovery did not advance to design: {action}")

    lazy_record({"outcome": "completed", "summary": "conservative design selected"})
    if action.get("kind") != "plan" or action.get("plan_write_mode") != "create-exclusive":
        raise SmokeError(f"lazy design did not reserve an exclusive plan: {action}")
    if "Lazy authorization override" not in action.get("prompt", ""):
        raise SmokeError("lazy plan prompt did not supersede only the acceptance pause")

    plan = execution / str(action["plan_path"])
    plan_action = str(action["action_id"])
    plan_head = git(execution, "rev-parse", "HEAD")
    plan.parent.mkdir(parents=True, exist_ok=True)
    with plan.open("x", encoding="utf-8") as output:
        output.write(
            "# Lazy installed plan\n\n"
            "### Task 1: Produce retry result\n\n"
            "- [ ] create `lazy-result.txt`\n"
            "- [ ] validate installed lazy behavior\n"
        )
    plan_commit = checkpoint(
        plan_action,
        plan_head,
        "docs(phasemill): create implementation plan",
        str(action["plan_path"]),
    )
    if plan_commit.get("status") != "committed":
        raise SmokeError(f"lazy plan was not checkpointed: {plan_commit}")
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    lazy_record(
        {
            "outcome": "completed",
            "plan_path": str(action["plan_path"]),
            "plan_digest": digest,
        }
    )
    if action.get("kind") != "plan-review" or len(action.get("roles", [])) < 2:
        raise SmokeError(f"lazy plan did not enter bounded review: {action}")

    finding = {
        "id": "smoke-validation",
        "location": f"{action['plan_path']}:5",
        "evidence": "the plan needs an explicit narrow command",
        "consequence": "validation would be ambiguous",
        "proposed_fix": "add the exact assertion to the plan",
    }
    lazy_record({"outcome": "findings", "findings": [finding]})
    if action.get("kind") != "plan-fix":
        raise SmokeError(f"lazy findings did not enter plan fix: {action}")
    fix_action = str(action["action_id"])
    fix_head = git(execution, "rev-parse", "HEAD")
    previous_digest = str(action["plan_digest"])
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\nValidation: `test -f lazy-result.txt`.\n",
        encoding="utf-8",
    )
    fix_commit = checkpoint(
        fix_action,
        fix_head,
        "docs(phasemill): address plan review",
        str(action["plan_path"]),
    )
    if fix_commit.get("status") != "committed":
        raise SmokeError(f"lazy plan fix was not checkpointed: {fix_commit}")
    fixed_digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    lazy_record(
        {
            "outcome": "completed",
            "plan_path": str(action["plan_path"]),
            "previous_plan_digest": previous_digest,
            "plan_digest": fixed_digest,
        }
    )
    if action.get("kind") != "plan-review":
        raise SmokeError(f"lazy plan fix did not return to review: {action}")
    lazy_record({"outcome": "clean", "summary": "verified plan is executable"})
    if action.get("kind") != "handoff" or action.get("matching_run_id"):
        raise SmokeError(f"lazy clean plan did not reach empty handoff: {action}")

    run_base = [sys.executable, run_controller, "--project-root", execution, "--default-branch", "main"]
    run_action = run_json([*run_base, "start", plan])
    if run_action.get("kind") != "task":
        raise SmokeError(f"synthetic exact run did not start: {run_action}")
    matching = run_json([*lazy_base, "next", journey_id])
    run_id = str(run_action["action_id"]).split(":", 1)[0]
    if matching.get("matching_run_id") != run_id or matching.get("action_id") != action.get("action_id"):
        raise SmokeError("lazy handoff did not discover the crash-window exact run")

    task_action = str(run_action["action_id"])
    task_head = git(execution, "rev-parse", "HEAD")
    (execution / "lazy-result.txt").write_text("installed lazy pipeline passed\n", encoding="utf-8")
    plan.write_text(plan.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8")
    task_commit = checkpoint(
        task_action,
        task_head,
        "chore(phasemill): complete task",
        "lazy-result.txt",
        str(plan.relative_to(execution)),
    )
    if task_commit.get("status") != "committed":
        raise SmokeError(f"lazy implementation stage was not committed: {task_commit}")
    run_action = run_json(
        [*run_base, "record", plan, "--action-id", str(run_action["action_id"])],
        input_text=json.dumps({"outcome": "completed", "summary": "synthetic implementation complete"}),
    )
    if run_action.get("kind") != "review":
        raise SmokeError(f"synthetic run did not reach review: {run_action}")
    run_action = run_json(
        [*run_base, "record", plan, "--action-id", str(run_action["action_id"])],
        input_text=json.dumps({"outcome": "clean", "summary": "synthetic review clean"}),
    )
    if run_action.get("kind") != "learning":
        raise SmokeError(f"synthetic run did not reach proposal-only learning: {run_action}")
    run_action = run_json(
        [*run_base, "record", plan, "--action-id", str(run_action["action_id"])],
        input_text=json.dumps({"outcome": "clean", "summary": "no durable learning signal"}),
    )
    if run_action.get("kind") != "done":
        raise SmokeError(f"synthetic exact run did not complete: {run_action}")

    action = matching
    lazy_record(
        {
            "outcome": "completed",
            "linked_run_id": run_id,
            "execution_project_root": str(execution),
            "execution_plan_path": str(action["execution_plan_path"]),
            "execution_branch": prepared["branch"],
            "run_outcome": "completed",
        }
    )
    if action.get("kind") != "done" or action.get("matching_run_id") != run_id:
        raise SmokeError(f"lazy journey did not record terminal exact run: {action}")
    lazy_status = run_json([*lazy_base, "status", "--journey-id", journey_id]).get("state", {})
    if lazy_status.get("status") != "completed" or lazy_status.get("linked_run_id") != run_id:
        raise SmokeError(f"lazy terminal state is invalid: {lazy_status}")

    config_dir = execution / ".codex/phasemill"
    unexpected_scope_writes = [path for path in config_dir.rglob("*") if path.is_file() and path.name != "config.toml"]
    if unexpected_scope_writes:
        raise SmokeError(f"lazy proposal-only learning mutated project scope: {unexpected_scope_writes}")
    if ".phasemill/runs" in git(execution, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SmokeError("lazy runtime state polluted Git status")
    if git(fixture, "rev-parse", "HEAD") != head_before:
        raise SmokeError("lazy pipeline changed origin HEAD")
    if git(fixture, "branch", "--show-current") != branch_before:
        raise SmokeError("lazy pipeline changed the main branch")
    if int(git(execution, "rev-list", "--count", f"{head_before}..HEAD")) < 4:
        raise SmokeError("lazy pipeline did not create per-stage commits")
    messages = git(execution, "log", "--format=%B", f"{head_before}..HEAD")
    if messages.count("Phasemill-Action:") < 4:
        raise SmokeError("lazy stage commits lost their stable action trailers")
    config_text = (config_dir / "config.toml").read_text(encoding="utf-8")
    if "data_sharing_approved = true" not in config_text:
        raise SmokeError("lazy project consent is not durable")
    remote_refs = subprocess.run(
        ["git", f"--git-dir={remote}", "show-ref"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    if remote_refs:
        raise SmokeError("lazy pipeline pushed a ref despite its local-only contract")


def parse_kv(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def verify_worktree(installed: dict[str, Path], root: Path) -> None:
    fixture = root / "worktree-fixture"
    plan = init_repo(fixture, plan_name="20260715-smoke-worktree.md")
    helper = installed["phasemill"] / "scripts/worktree.sh"
    head_before = git(fixture, "rev-parse", "HEAD")
    branch_before = git(fixture, "branch", "--show-current")
    status_before = git(fixture, "status", "--short")

    planned = parse_kv(run([helper, "plan", "--repo", fixture, "--plan", plan]).stdout)
    if planned.get("status") != "planned":
        raise SmokeError(f"worktree planning failed: {planned}")
    prepared = parse_kv(
        run(
            [
                helper,
                "prepare",
                "--repo",
                fixture,
                "--plan",
                plan,
                "--default-branch",
                "main",
            ]
        ).stdout
    )
    worktree = Path(prepared.get("project_root", ""))
    if prepared.get("status") != "created" or not worktree.is_dir():
        raise SmokeError(f"worktree prepare failed: {prepared}")
    reused = parse_kv(run([helper, "inspect", "--repo", fixture, "--plan", plan]).stdout)
    if reused.get("status") != "reused" or Path(reused.get("project_root", "")) != worktree:
        raise SmokeError(f"worktree inspect did not reuse identity: {reused}")
    if git(fixture, "rev-parse", "HEAD") != head_before:
        raise SmokeError("worktree creation changed main HEAD")
    if git(fixture, "branch", "--show-current") != branch_before:
        raise SmokeError("worktree creation changed main branch")
    if git(fixture, "status", "--short") != status_before:
        raise SmokeError("worktree creation changed main status")

    removed = parse_kv(
        run([helper, "remove", "--repo", fixture, "--plan", plan, "--yes"]).stdout
    )
    if removed.get("status") != "removed" or worktree.exists():
        raise SmokeError(f"explicit clean worktree removal failed: {removed}")
    branch = prepared.get("branch", "")
    git(fixture, "show-ref", "--verify", f"refs/heads/{branch}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="tests/smoke/run-codex-plugin-smoke.sh",
        description="Install Phasemill into a clean Codex home and run offline smoke checks.",
    )
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args(argv)

    repo = args.repo.expanduser().resolve()
    if not (repo / ".agents/plugins/marketplace.json").is_file():
        raise SmokeError(f"not a Phasemill marketplace root: {repo}")
    codex = shutil.which(args.codex)
    if not codex:
        raise SmokeError(f"Codex CLI not found: {args.codex}")

    temp_root = Path(tempfile.mkdtemp(prefix="phasemill-codex-smoke-"))
    try:
        installed = verify_install(codex, repo, temp_root / "codex-home")
        assert_mutation_guards(installed)
        verify_planning_pipeline(installed, temp_root)
        verify_lazy_pipeline(installed, temp_root)
        verify_worktree(installed, temp_root)
        summary = {
            "status": "passed",
            "marketplace": MARKETPLACE,
            "plugins": len(installed),
            "skills": sum(len(names) for names in EXPECTED_SKILLS.values()),
            "clean_codex_home": True,
            "installed_cache_only": True,
            "planning_pipeline": "passed",
            "lazy_pipeline": "passed",
            "retry_resume": "passed",
            "review_fanout_contract": "passed",
            "proposal_only_learning": "passed",
            "worktree_isolation": "passed",
            "external_mutations": "none",
            "model_or_network_calls": "none",
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.keep_temp:
            print(f"temporary_root={temp_root}")
        return 0
    finally:
        if not args.keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)


try:
    raise SystemExit(main(sys.argv[2:]))
except SmokeError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
