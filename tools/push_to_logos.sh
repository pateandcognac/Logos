#!/usr/bin/env bash
# tools/push_to_logos.sh
#
# A walkthrough for getting changes made in a live robot workspace
# (~/robot_workspaces/<name>) back into this Logos/ repo, and from there
# up to GitHub as a pull request.
#
# Why two hops? When logos_cog.sh spins up a workspace, it does a plain
# `git clone` of THIS Logos/ directory -- so a workspace's "origin" remote
# is this local folder, not GitHub. Only this Logos/ folder's "origin" is
# actually https://github.com/pateandcognac/Logos.git. So the trip is:
#
#   workspace  --push-->  Logos/ (local)  --push-->  GitHub  --PR-->  master
#
# This script is meant to be read, not just run. It pauses before every
# git command that changes state and tells you what's about to happen.
#
# Run it from EITHER a spawned workspace or from Logos/ itself -- it
# figures out which hop(s) you need.

set -euo pipefail

confirm() {
    local prompt="$1"
    local reply
    read -r -p "${prompt} [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

if [[ ! -d .git ]]; then
    echo "This doesn't look like a git repo: $HERE" >&2
    exit 1
fi

ORIGIN_URL="$(git config --get remote.origin.url || true)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

say "Step 0: where am I?"
echo "  Directory:      $HERE"
echo "  Current branch: $CURRENT_BRANCH"
echo "  origin remote:  ${ORIGIN_URL:-<none>}"

IS_WORKSPACE_CLONE=false
if [[ "$ORIGIN_URL" != *github.com* ]]; then
    IS_WORKSPACE_CLONE=true
    echo "  -> origin points at a local path, so this is a WORKSPACE clone,"
    echo "     not the main Logos/ repo. We'll need both hops."
else
    echo "  -> origin points at GitHub, so this already IS the Logos/ repo."
    echo "     We only need the second hop (Logos/ -> GitHub)."
fi

say "Step 1: is there anything to save?"
git status --short
if [[ -z "$(git status --porcelain)" ]]; then
    echo "  Working tree is clean."
else
    echo "  You have uncommitted changes (above)."
    if confirm "Commit everything now with a message you'll type?"; then
        read -r -p "Commit message: " msg
        git add -A
        git commit -m "$msg"
    else
        echo "  Skipping commit -- note that uncommitted changes won't travel"
        echo "  with a push. Commit them before continuing, or re-run this script."
    fi
fi

if [[ "$IS_WORKSPACE_CLONE" == true ]]; then
    say "Step 2 (hop 1 of 2): push this workspace's branch into Logos/"
    echo "  This runs:  git push origin $CURRENT_BRANCH"
    echo "  It updates the '$CURRENT_BRANCH' branch inside the local Logos/"
    echo "  folder (NOT GitHub yet). If Logos/ has '$CURRENT_BRANCH' checked"
    echo "  out right now, this push will be refused -- that's git protecting"
    echo "  you from silently rewriting someone's checked-out working copy."
    if confirm "Run 'git push origin $CURRENT_BRANCH' now?"; then
        git push origin "$CURRENT_BRANCH"
    else
        echo "  Stopping here. Re-run this script from Logos/ itself once you're ready for hop 2."
        exit 0
    fi

    say "Step 3 (hop 2 of 2): from inside Logos/, push up to GitHub"
    echo "  I can't 'cd' your shell for you, so do this next:"
    echo ""
    echo "    cd ~/robot_workspaces/Logos"
    echo "    git checkout $CURRENT_BRANCH   # if not already on it"
    echo "    ./tools/push_to_logos.sh       # run me again from here"
    exit 0
fi

# From here on, we're inside Logos/ itself with a GitHub origin.
say "Step 2: push '$CURRENT_BRANCH' to GitHub"
if [[ "$CURRENT_BRANCH" == "master" ]]; then
    echo "  You're on 'master'. Don't push straight to master -- use a"
    echo "  feature branch and open a pull request instead, e.g.:"
    echo "    git checkout -b my-change"
    exit 1
fi
if confirm "Run 'git push origin $CURRENT_BRANCH' now?"; then
    git push -u origin "$CURRENT_BRANCH"
else
    echo "  Stopping here."
    exit 0
fi

say "Step 3: open a pull request into master"
if ! command -v gh >/dev/null 2>&1; then
    echo "  'gh' (GitHub CLI) isn't installed, so open the PR manually at:"
    echo "  https://github.com/pateandcognac/Logos/compare/master...$CURRENT_BRANCH"
    exit 0
fi
if confirm "Run 'gh pr create' now (you'll get a title/body prompt)?"; then
    gh pr create --base master --head "$CURRENT_BRANCH"
else
    echo "  No PR opened. Your branch is safely on GitHub -- open one later with:"
    echo "    gh pr create --base master --head $CURRENT_BRANCH"
fi

say "Step 4: after the PR is reviewed and merged on GitHub"
echo "  Nothing to run here yet! Once it's merged in the GitHub UI, pull"
echo "  master down locally so this Logos/ folder matches GitHub again:"
echo ""
echo "    git checkout master"
echo "    git pull origin master"
