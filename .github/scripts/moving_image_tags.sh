#!/usr/bin/env bash
# Lets this run move <service>-latest and the <major>.<minor> tags only when it
# holds the newest build, so a run finishing after a newer one cannot move them
# back. It must run inside the merge job's concurrency group, because the check
# and the push are only safe together. Writes MOVE_LATEST/MOVE_MINOR to GITHUB_ENV.
set -euo pipefail

image="$1"
service="$2"

move_minor=false
if [[ "${RELEASE_VERSION:-}" =~ ^([0-9]+)\.([0-9]+)\.[0-9]+$ ]]; then
  series="${BASH_REMATCH[1]}\.${BASH_REMATCH[2]}"
  newest=$(
    {
      gh api "repos/${GITHUB_REPOSITORY}/git/matching-refs/tags/" --jq '.[].ref' |
        sed -nE "s#^refs/tags/(.+-)?v(${series}\.[0-9]+)\$#\2#p"
      echo "$RELEASE_VERSION"
    } | sort -V | tail -n 1
  )
  if [ "$newest" = "$RELEASE_VERSION" ]; then
    move_minor=true
  else
    echo "::notice::${newest} is already released, so ${RELEASE_VERSION} leaves the minor tags alone"
  fi
fi

move_latest=true
err=$(mktemp)
if raw=$(docker buildx imagetools inspect --raw "${image}:${service}-latest" 2>&1); then
  current=$(jq -r '.annotations["org.opencontainers.image.revision"] // empty' <<<"$raw")
elif grep -q ': not found$' <<<"$raw"; then
  current=""
else
  echo "$raw" >&2
  exit 1
fi

if [ -n "$current" ] && [ "$current" != "$GITHUB_SHA" ]; then
  if status=$(gh api "repos/${GITHUB_REPOSITORY}/compare/${current}...${GITHUB_SHA}" --jq .status 2>"$err"); then
    if [ "$status" = "behind" ]; then
      move_latest=false
      echo "::notice::${service}-latest is on ${current}, which is newer than ${GITHUB_SHA}, so it stays"
    fi
  elif grep -qE 'HTTP (404|422)' "$err"; then
    echo "::warning::${current} on ${service}-latest is not in this repository, moving it anyway"
  else
    cat "$err" >&2
    exit 1
  fi
fi

{
  echo "MOVE_LATEST=${move_latest}"
  echo "MOVE_MINOR=${move_minor}"
} >>"$GITHUB_ENV"
