#!/usr/bin/env bash
# Run from a checkout with an authenticated origin. Never rewrites history.
set -euo pipefail
gitclimb_source="$(pwd)/dist"
test -s "$gitclimb_source/climb.svg"
test -s "$gitclimb_source/climb-dark.svg"
gitclimb_worktree="$(mktemp -d)"
rmdir "$gitclimb_worktree"
cleanup() { git worktree remove --force "$gitclimb_worktree" >/dev/null 2>&1 || true; }
trap cleanup EXIT
if git ls-remote --exit-code --heads origin output > /dev/null; then
  git fetch origin output
  git worktree add --detach "$gitclimb_worktree" FETCH_HEAD
else
  gitclimb_status=$?
  if [ "$gitclimb_status" -ne 2 ]; then
    echo "Could not inspect output branch. Stopping without publishing." >&2
    exit "$gitclimb_status"
  fi
  git worktree add --detach "$gitclimb_worktree" HEAD
  git -C "$gitclimb_worktree" switch --orphan gitclimb-output
fi
cp "$gitclimb_source/climb.svg" "$gitclimb_source/climb-dark.svg" "$gitclimb_worktree/"
git -C "$gitclimb_worktree" config user.name "github-actions[bot]"
git -C "$gitclimb_worktree" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git -C "$gitclimb_worktree" add climb.svg climb-dark.svg
if git -C "$gitclimb_worktree" diff --cached --quiet; then
  echo "The wall is already up to date."
  exit 0
fi
git -C "$gitclimb_worktree" commit -m "Refresh GitClimb wall"
git -C "$gitclimb_worktree" push origin HEAD:refs/heads/output
