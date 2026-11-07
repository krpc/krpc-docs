#!/bin/bash
# Run the three builds twice, interleaved, from a clean krpc checkout on the base commit.
# Usage: run.sh <krpc checkout> <output directory>
# Set BAZEL to replace the bazel command, such as BAZEL=true to check the git steps alone.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
bazel=${BAZEL:-bazel}
cd "$repo"
start=$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)

git switch -q --detach
A=$(git rev-parse HEAD)
git apply "$here/ids.patch"
git add -A client tools
git -c user.name=benchmark -c user.email=benchmark@localhost commit -q -m "Call by id"
B=$(git rev-parse HEAD)
git apply "$here/direct-lookup.patch"
git add -A core
git -c user.name=benchmark -c user.email=benchmark@localhost commit -q -m "Direct id lookup"
C=$(git rev-parse HEAD)

for round in 1 2; do
  for build in A B C; do
    git switch -q --detach "${!build}"
    "$bazel" run //tools/benchmarks:clients -- --json "$out/$build$round.json" \
      > "$out/$build$round.log" 2>&1
    echo "done $build$round"
  done
done
git switch -q "$start" 2>/dev/null || git switch -q --detach "$start"
