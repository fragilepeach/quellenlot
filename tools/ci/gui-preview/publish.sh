#!/usr/bin/env bash
set -euo pipefail

capture_dir=${1:?Pass the directory containing the validated preview artifact}
media_dir=docs/images/generated
images=(desktop.png mobile.png usage.gif parliament.png studies.png studies-mobile.png)

node -e '
  const assert = require("node:assert/strict");
  const fs = require("node:fs");
  const crypto = require("node:crypto");
  const path = require("node:path");
  const [dir, ...images] = process.argv.slice(1);
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  assert.equal(manifest.source_commit, process.env.GITHUB_SHA);
  assert.deepEqual(manifest.media.map(({ file }) => file), images);
  for (const { file, sha256 } of manifest.media) {
    const bytes = fs.readFileSync(path.join(dir, file));
    assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), sha256);
  }
' "$capture_dir" "${images[@]}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3; do
  git fetch --no-tags --depth=1 origin "$GITHUB_REF"
  target=$(git rev-parse FETCH_HEAD)
  if ! git diff --quiet "$GITHUB_SHA" "$target" -- web/ tools/ci/gui-preview/ .github/workflows/gui-previews.yml; then
    echo "Preview inputs changed on the target branch. The newer run will publish its previews."
    exit 0
  fi

  git checkout --quiet --detach "$target"
  changed=false
  for image in "${images[@]}"; do
    if ! cmp -s "$capture_dir/$image" "$media_dir/$image"; then
      changed=true
      break
    fi
  done
  if [[ "$changed" == false ]]; then
    echo "Documentation previews already match the validated capture."
    exit 0
  fi

  mkdir -p "$media_dir"
  for file in "${images[@]}" manifest.json; do
    install -m 0644 "$capture_dir/$file" "$media_dir/$file"
    git add -- "$media_dir/$file"
  done
  git commit -m "docs: refresh Quellenlot GUI previews"
  if git push origin "HEAD:$GITHUB_REF"; then
    exit 0
  fi

  remote=$(git ls-remote origin "$GITHUB_REF")
  if [[ -z "$remote" || "${remote%%$'\t'*}" == "$target" || "$attempt" == 3 ]]; then
    echo "Failed to update documentation previews." >&2
    exit 1
  fi
done
