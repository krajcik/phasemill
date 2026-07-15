#!/usr/bin/env bash
# Prepare, inspect, or explicitly remove the deterministic Codex planning worktree.

set -euo pipefail

usage() {
    cat <<'EOF'
usage:
  worktree.sh plan    --repo <path> --plan <path> [--branch <name>]
  worktree.sh prepare --repo <path> --plan <path> --default-branch <name> [--branch <name>]
  worktree.sh inspect --repo <path> --plan <path> [--branch <name>]
  worktree.sh remove  --repo <path> --plan <path> [--branch <name>] --yes

prepare must be called from the default branch and permits no dirty path other
than the plan. It never commits, checks out the main worktree, or removes an
existing worktree. Repeating prepare reuses the same registered branch/path.
EOF
}

fail() {
    echo "error: $*" >&2
    exit 2
}

derive_branch() {
    local name
    name=$(basename "$1" .md)
    name=$(printf '%s\n' "$name" | sed 's/^[0-9]\{4\}-\{0,1\}[0-9]\{2\}-\{0,1\}[0-9]\{2\}-//')
    [ -n "$name" ] || fail "cannot derive a branch name from plan: $1"
    printf '%s\n' "$name"
}

emit() {
    local status=$1 root=$2 path=$3 branch=$4 plan=$5 copied=$6
    case "$root$path$branch$plan" in
        *$'\n'*) fail "newline characters are not supported in repository paths or branch names" ;;
    esac
    printf 'status=%s\n' "$status"
    printf 'project_root=%s\n' "$path"
    printf 'main_root=%s\n' "$root"
    printf 'branch=%s\n' "$branch"
    printf 'plan_path=%s\n' "$plan"
    printf 'plan_copied=%s\n' "$copied"
}

command=${1:-}
case "$command" in
    plan|prepare|inspect|remove) shift ;;
    -h|--help|"") usage; exit 0 ;;
    *) usage >&2; fail "unknown command: $command" ;;
esac

repo=""
plan=""
default_branch=""
branch=""
confirmed=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo)
            [ "$#" -ge 2 ] || fail "--repo requires a value"
            repo=$2
            shift 2
            ;;
        --plan)
            [ "$#" -ge 2 ] || fail "--plan requires a value"
            plan=$2
            shift 2
            ;;
        --default-branch)
            [ "$#" -ge 2 ] || fail "--default-branch requires a value"
            default_branch=$2
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || fail "--branch requires a value"
            branch=$2
            shift 2
            ;;
        --yes)
            confirmed=true
            shift
            ;;
        *) fail "unknown argument: $1" ;;
    esac
done

[ -n "$repo" ] || fail "--repo is required"
[ -n "$plan" ] || fail "--plan is required"
command -v git >/dev/null 2>&1 || fail "git is required"

repo_root=$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null) || fail "not a Git repository: $repo"
repo_root=$(cd "$repo_root" && pwd -P)
root=$(git -C "$repo_root" worktree list --porcelain | sed -n 's/^worktree //p' | head -1)
[ -n "$root" ] || fail "cannot resolve the main Git worktree: $repo"
root=$(cd "$root" && pwd -P)

if [ ! -f "$plan" ]; then
    case "$plan" in
        /*) fail "plan file does not exist: $plan" ;;
        *) plan="$repo_root/$plan" ;;
    esac
fi
[ -f "$plan" ] || fail "plan file does not exist: $plan"
plan_dir=$(cd "$(dirname "$plan")" && pwd -P)
plan_abs="$plan_dir/$(basename "$plan")"
case "$plan_abs" in
    "$root"/*) plan_rel=${plan_abs#"$root"/} ;;
    "$repo_root"/*) plan_rel=${plan_abs#"$repo_root"/} ;;
    *) fail "plan must be inside the repository: $plan_abs" ;;
esac

[ -n "$branch" ] || branch=$(derive_branch "$plan_abs")
git check-ref-format --branch "$branch" >/dev/null 2>&1 || fail "invalid branch name: $branch"

parent=$(dirname "$root")
repo_name=$(basename "$root")
base="$parent/.${repo_name}-phasemill-worktrees"
worktree="$base/$branch"
worktree_plan="$worktree/$plan_rel"

inspect_existing() {
    [ -d "$worktree" ] || return 1
    local actual_root actual_branch
    actual_root=$(git -C "$worktree" rev-parse --show-toplevel 2>/dev/null) || return 1
    [ "$(cd "$actual_root" && pwd -P)" = "$(cd "$worktree" && pwd -P)" ] || return 1
    actual_branch=$(git -C "$worktree" branch --show-current)
    [ "$actual_branch" = "$branch" ] || fail "worktree path uses branch $actual_branch, expected $branch: $worktree"
    [ -f "$worktree_plan" ] || fail "registered worktree is missing its plan: $worktree_plan"
    return 0
}

if [ "$command" = "inspect" ]; then
    if inspect_existing; then
        emit "reused" "$root" "$worktree" "$branch" "$worktree_plan" false
        exit 0
    fi
    fail "planning worktree does not exist: $worktree"
fi

if [ "$command" = "plan" ]; then
    if inspect_existing; then
        emit "reused" "$root" "$worktree" "$branch" "$worktree_plan" false
    else
        [ ! -e "$worktree" ] || fail "path exists but is not the expected registered worktree: $worktree"
        emit "planned" "$root" "$worktree" "$branch" "$worktree_plan" false
    fi
    exit 0
fi

if [ "$command" = "remove" ]; then
    [ "$confirmed" = true ] || fail "remove requires explicit --yes confirmation"
    inspect_existing || fail "planning worktree does not exist: $worktree"
    dirty=$(git -C "$worktree" status --porcelain=v1 --untracked-files=all)
    [ -z "$dirty" ] || fail "refusing to remove a dirty worktree: $worktree"
    git -C "$root" worktree remove "$worktree"
    printf 'status=removed\nproject_root=%s\nmain_root=%s\nbranch=%s\nplan_path=%s\nplan_copied=false\n' \
        "$worktree" "$root" "$branch" "$worktree_plan"
    exit 0
fi

[ -n "$default_branch" ] || fail "prepare requires --default-branch"
current_branch=$(git -C "$root" branch --show-current)
[ -n "$current_branch" ] || fail "worktree preparation requires an attached default branch"
[ "$current_branch" = "$default_branch" ] || \
    fail "worktree preparation requires $default_branch branch, currently on $current_branch"

if inspect_existing; then
    emit "reused" "$root" "$worktree" "$branch" "$worktree_plan" false
    exit 0
fi
[ ! -e "$worktree" ] || fail "path exists but is not the expected registered worktree: $worktree"
[ "$repo_root" = "$root" ] || fail "a new planning worktree must be prepared from the main worktree: $root"

other_changes=$(git -C "$root" status --porcelain=v1 --untracked-files=all -- . ":(exclude)$plan_rel")
if [ -n "$other_changes" ]; then
    printf 'error: cannot create worktree with changes outside the plan:\n%s\n' "$other_changes" >&2
    exit 2
fi

head_before=$(git -C "$root" rev-parse HEAD)
git -C "$root" worktree prune
mkdir -p "$base"

created=false
cleanup_created() {
    if [ "$created" = true ]; then
        git -C "$root" worktree remove --force "$worktree" >/dev/null 2>&1 || true
    fi
}
trap cleanup_created ERR INT TERM

if git -C "$root" show-ref --verify --quiet "refs/heads/$branch"; then
    git -C "$root" worktree add "$worktree" "$branch"
else
    git -C "$root" worktree add "$worktree" -b "$branch"
fi
created=true

plan_status=$(git -C "$root" status --porcelain=v1 --untracked-files=all -- "$plan_rel")
copied=false
if [ -n "$plan_status" ] || [ ! -f "$worktree_plan" ]; then
    mkdir -p "$(dirname "$worktree_plan")"
    cp "$plan_abs" "$worktree_plan"
    copied=true
fi

exclude_file=$(git -C "$worktree" rev-parse --git-path info/exclude)
exclude_dir=$(dirname "$exclude_file")
mkdir -p "$exclude_dir"
touch "$exclude_file"
if ! grep -Fxq '/.phasemill/runs/' "$exclude_file"; then
    printf '/.phasemill/runs/\n' >> "$exclude_file"
fi

head_after=$(git -C "$root" rev-parse HEAD)
[ "$head_before" = "$head_after" ] || fail "main HEAD changed during worktree preparation"
[ "$(git -C "$root" branch --show-current)" = "$default_branch" ] || \
    fail "main branch changed during worktree preparation"

trap - ERR INT TERM
created=false
emit "created" "$root" "$worktree" "$branch" "$worktree_plan" "$copied"
