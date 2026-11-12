#!/usr/bin/env bash
# Promote a fully verified, commit-qualified rolling product bundle to one fixed tag.
# The reusable workflow invokes this file explicitly with Bash; it need not be executable.
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${SOURCE_RUN_TOKEN:?SOURCE_RUN_TOKEN is required}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${SOURCE_BRANCH:?SOURCE_BRANCH is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${SOURCE_RUN_ID:?SOURCE_RUN_ID is required}"
: "${SOURCE_WORKFLOW_PATH:?SOURCE_WORKFLOW_PATH is required}"
: "${PRODUCT_PREFIX:?PRODUCT_PREFIX is required}"
: "${ASSET_DIRECTORY:?ASSET_DIRECTORY is required}"
: "${MANIFEST_NAME:?MANIFEST_NAME is required}"
: "${EXPECTED_TARGET_PROFILES:?EXPECTED_TARGET_PROFILES is required}"

if [[ "$SOURCE_BRANCH" != "main" ]]; then
  echo "Rolling product promotion is only permitted from main; got $SOURCE_BRANCH." >&2
  exit 2
fi
if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be a full lowercase 40-character commit SHA." >&2
  exit 2
fi
if [[ ! "$SOURCE_RUN_ID" =~ ^[1-9][0-9]*$ ]]; then
  echo "SOURCE_RUN_ID must be a positive decimal integer." >&2
  exit 2
fi
if [[ ! "$PRODUCT_PREFIX" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$ ]]; then
  echo "PRODUCT_PREFIX is not a safe asset namespace." >&2
  exit 2
fi

export GH_TOKEN
tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

assert_fresh_main() {
  local current
  current="$(gh api "repos/$REPOSITORY/commits/main" --jq .sha)"
  if [[ "$current" != "$SOURCE_SHA" ]]; then
    echo "Refusing stale rolling run: main is $current, candidate is $SOURCE_SHA." >&2
    return 1
  fi
}

verify_source_run() {
  local run_file="$tmp/source-run.json"
  GH_TOKEN="$SOURCE_RUN_TOKEN" gh api "repos/$REPOSITORY/actions/runs/$SOURCE_RUN_ID" > "$run_file"
  jq -e \
    --arg repository "$REPOSITORY" \
    --arg sha "$SOURCE_SHA" \
    --arg branch "$SOURCE_BRANCH" \
    --arg workflow "$SOURCE_WORKFLOW_PATH" \
    '(.event == "push") and
     (.conclusion == "success") and
     (.path == $workflow) and
     (.head_branch == $branch) and
     (.head_sha == $sha) and
     (.repository.full_name == $repository) and
     (.run_attempt | type == "number" and . > 0)' \
    "$run_file" >/dev/null
}

assert_safe_asset_name() {
  local name="$1"
  if [[ ! "$name" =~ ^[A-Za-z0-9._+-]+$ ]]; then
    echo "Unsafe rolling asset filename: $name" >&2
    return 1
  fi
}

load_remote_inventory() {
  local output="$1"
  gh api --paginate "repos/$REPOSITORY/releases/$RELEASE_ID/assets?per_page=100" \
    --jq '.[] | [.name, (.size | tostring), (.digest // ""), (.id | tostring)] | @tsv' > "$output"
}

# Exit non-zero on duplicate names, different bytes under an immutable name,
# malformed rows, or a non-regular local file. Print "present" or "missing".
remote_asset_state() {
  local inventory="$1"
  local name="$2"
  local local_path="$3"
  python - "$inventory" "$name" "$local_path" <<'PY'
import hashlib
import sys
from pathlib import Path

inventory_path, name, local_name = sys.argv[1:]
local_path = Path(local_name)
if not local_path.is_file() or local_path.is_symlink():
    raise SystemExit(f"candidate asset is missing or unsafe: {local_path}")
expected_size = local_path.stat().st_size
digest = hashlib.sha256()
with local_path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
expected_digest = digest.hexdigest()
matches = []
for line in Path(inventory_path).read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if len(fields) != 4:
        raise SystemExit("GitHub returned a malformed release-asset inventory row")
    if fields[0] == name:
        matches.append(fields)
if len(matches) > 1:
    raise SystemExit(f"GitHub returned duplicate Release assets named {name}")
if not matches:
    print("missing")
    raise SystemExit(0)
_, remote_size, remote_digest, _ = matches[0]
if remote_size != str(expected_size) or remote_digest != f"sha256:{expected_digest}":
    raise SystemExit(f"immutable rolling asset collision for {name}; refusing to replace it")
print("present")
PY
}

assert_fresh_main
verify_source_run
assert_fresh_main

# Re-validate the complete local manifest immediately before touching GitHub.
PYTHONPATH=".pipeline/src:src${PYTHONPATH:+:$PYTHONPATH}" python -m pipeline.release.rolling verify \
  --output-directory "$ASSET_DIRECTORY" \
  --manifest-name "$MANIFEST_NAME" \
  --source-sha "$SOURCE_SHA" \
  --repository "$REPOSITORY" \
  --expected-target-profiles "$EXPECTED_TARGET_PROFILES" > "$tmp/local-verification.json"

manifest_path="$ASSET_DIRECTORY/$MANIFEST_NAME"
manifest_sha="$(sha256sum "$manifest_path" | awk '{print $1}')"
[[ -s "$manifest_path" && -s "$manifest_path.sha256" ]]
grep -Fxq "$manifest_sha  $MANIFEST_NAME" "$manifest_path.sha256"

# The local asset directory must contain only safe regular files.
expected_local="$tmp/expected-assets.txt"
find "$ASSET_DIRECTORY" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | sort > "$expected_local"
if [[ ! -s "$expected_local" ]]; then
  echo "Rolling asset directory is empty." >&2
  exit 1
fi
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  assert_safe_asset_name "$name"
done < "$expected_local"

# Locate a published or draft Release by ID. The tag lookup endpoint does
# not reliably expose drafts, so listing releases is required for partial retries.
release_file="$tmp/release.json"
release_ids="$(gh api --paginate "repos/$REPOSITORY/releases?per_page=100" \
  --jq '.[] | select(.tag_name == "latest") | .id')"
if [[ -n "$release_ids" ]]; then
  mapfile -t found_release_ids <<< "$release_ids"
  if (( ${#found_release_ids[@]} != 1 )); then
    echo "Expected exactly one Release for tag latest; found ${#found_release_ids[@]}." >&2
    exit 1
  fi
  RELEASE_ID="${found_release_ids[0]}"
  gh api "repos/$REPOSITORY/releases/$RELEASE_ID" > "$release_file"
else
  initial_body="Rolling product candidate is being staged. This draft is not a published distribution."
  gh api --method POST "repos/$REPOSITORY/releases" \
    -f tag_name=latest \
    -f target_commitish="$SOURCE_SHA" \
    -f name="$PRODUCT_PREFIX rolling development (staging)" \
    -f body="$initial_body" \
    -F draft=true \
    -F prerelease=true > "$release_file"
  RELEASE_ID="$(jq -r '.id' "$release_file")"
fi
if [[ ! "$RELEASE_ID" =~ ^[1-9][0-9]*$ ]]; then
  echo "GitHub returned an invalid rolling Release ID." >&2
  exit 1
fi
export RELEASE_ID

jq -e --argjson release_id "$RELEASE_ID" '
  (.id == $release_id) and
  (.tag_name == "latest") and
  (.prerelease == true) and
  (.upload_url | type == "string")
' "$release_file" >/dev/null
upload_url_template="$(jq -r '.upload_url // empty' "$release_file")"
upload_url="${upload_url_template%%\{*}"
expected_upload_url="https://uploads.github.com/repos/$REPOSITORY/releases/$RELEASE_ID/assets"
if [[ "$upload_url" != "$expected_upload_url" ]]; then
  echo "GitHub returned an unexpected Release asset upload URL." >&2
  exit 1
fi

upload_release_asset() {
  local asset_path="$1"
  local name encoded_name
  name="$(basename "$asset_path")"
  assert_safe_asset_name "$name"
  encoded_name="$(python -c 'from urllib.parse import quote; import sys; print(quote(sys.argv[1], safe=""))' "$name")"
  curl --fail --silent --show-error \
    --header "Authorization: Bearer $GH_TOKEN" \
    --header 'Accept: application/vnd.github+json' \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    --header 'Content-Type: application/octet-stream' \
    --data-binary "@$asset_path" \
    "$upload_url?name=$encoded_name" > "$tmp/upload-response.json"
  jq -e --arg name "$name" '.name == $name' "$tmp/upload-response.json" >/dev/null
}

inventory="$tmp/remote-assets.tsv"
load_remote_inventory "$inventory"

# Upload commit-qualified package assets first. A retry reuses exact matching
# bytes only; no existing same-name asset is deleted or overwritten.
while IFS= read -r name; do
  [[ -n "$name" ]] || continue
  [[ "$name" == "$MANIFEST_NAME" || "$name" == "$MANIFEST_NAME.sha256" ]] && continue
  asset_path="$ASSET_DIRECTORY/$name"
  state="$(remote_asset_state "$inventory" "$name" "$asset_path")"
  if [[ "$state" == "present" ]]; then
    continue
  fi
  upload_release_asset "$asset_path"
  load_remote_inventory "$inventory"
done < "$expected_local"

# Upload the authoritative manifest and its checksum only after package assets.
for name in "$MANIFEST_NAME" "$MANIFEST_NAME.sha256"; do
  asset_path="$ASSET_DIRECTORY/$name"
  state="$(remote_asset_state "$inventory" "$name" "$asset_path")"
  if [[ "$state" == "present" ]]; then
    continue
  fi
  upload_release_asset "$asset_path"
  load_remote_inventory "$inventory"
done

# Compare every local package/checksum/manifest byte with GitHub's full,
# paginated inventory. Python parses TSV rows, avoiding shell IFS and jq injection.
python - "$inventory" "$ASSET_DIRECTORY" "$expected_local" <<'PY'
import hashlib
import sys
from pathlib import Path

inventory_path, directory_name, names_path = sys.argv[1:]
remote = {}
for line in Path(inventory_path).read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if len(fields) != 4:
        raise SystemExit("GitHub returned a malformed release-asset inventory row")
    name, size, digest, asset_id = fields
    if name in remote:
        raise SystemExit(f"GitHub Release contains duplicate asset name: {name}")
    remote[name] = (size, digest, asset_id)

root = Path(directory_name)
names = [line for line in Path(names_path).read_text(encoding="utf-8").splitlines() if line]
for name in names:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"local candidate is missing or unsafe: {name}")
    if name not in remote:
        raise SystemExit(f"GitHub Release is missing candidate asset: {name}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    remote_size, remote_digest, _ = remote[name]
    if remote_size != str(path.stat().st_size) or remote_digest != f"sha256:{digest.hexdigest()}":
        raise SystemExit(f"GitHub Release size/digest mismatch for {name}")
print(f"Verified {len(names)} candidate Release assets against GitHub.")
PY

# Recheck source identity immediately before moving the mutable tag.
assert_fresh_main
verify_source_run
assert_fresh_main

ref_file="$tmp/latest-ref.json"
ref_code="$(curl --silent --show-error --output "$ref_file" --write-out '%{http_code}' \
  --header "Authorization: Bearer $GH_TOKEN" \
  --header 'Accept: application/vnd.github+json' \
  --header 'X-GitHub-Api-Version: 2022-11-28' \
  "https://api.github.com/repos/$REPOSITORY/git/ref/tags/latest")"
case "$ref_code" in
  200)
    current_ref_sha="$(jq -r '.object.sha' "$ref_file")"
    current_ref_type="$(jq -r '.object.type' "$ref_file")"
    if [[ "$current_ref_sha" != "$SOURCE_SHA" || "$current_ref_type" != "commit" ]]; then
      gh api --method PATCH "repos/$REPOSITORY/git/refs/tags/latest" \
        -f "sha=$SOURCE_SHA" -F force=true >/dev/null
    fi
    ;;
  404)
    gh api --method POST "repos/$REPOSITORY/git/refs" \
      -f ref=refs/tags/latest -f "sha=$SOURCE_SHA" >/dev/null
    ;;
  *)
    echo "Could not inspect latest Git ref (HTTP $ref_code)." >&2
    cat "$ref_file" >&2
    exit 1
    ;;
esac

resolved_ref="$(gh api "repos/$REPOSITORY/git/ref/tags/latest" --jq '.object.sha')"
if [[ "$resolved_ref" != "$SOURCE_SHA" ]]; then
  echo "latest tag did not resolve to the verified source commit." >&2
  exit 1
fi

manifest_url="https://github.com/$REPOSITORY/releases/download/latest/$MANIFEST_NAME"
release_body="$(cat <<EOF
## Rolling development build

- **Channel:** `latest` (prerelease)
- **Source commit:** `$SOURCE_SHA`
- **Verified CI run:** [$SOURCE_RUN_ID](https://github.com/$REPOSITORY/actions/runs/$SOURCE_RUN_ID)
- **Target/profile packages:** $(jq '.target_profiles | length' "$manifest_path")
- **Authoritative inventory:** [$MANIFEST_NAME]($manifest_url)
- **Manifest SHA-256:** `$manifest_sha`

Only assets listed in the commit-bound manifest are part of this rolling build. Older rolling assets are retained until this manifest and the `latest` ref have both been verified.
EOF
)"

gh api --method PATCH "repos/$REPOSITORY/releases/$RELEASE_ID" \
  -f name="$PRODUCT_PREFIX rolling development ($SOURCE_SHA)" \
  -f body="$release_body" \
  -F prerelease=true \
  -F draft=false > "$release_file"

jq -e '(.draft == false) and (.prerelease == true) and (.tag_name == "latest")' "$release_file" >/dev/null
resolved_ref="$(gh api "repos/$REPOSITORY/git/ref/tags/latest" --jq '.object.sha')"
if [[ "$resolved_ref" != "$SOURCE_SHA" ]]; then
  echo "latest tag changed unexpectedly during Release publication." >&2
  exit 1
fi

# Prune old assets only after the new inventory and prerelease are published.
# If main advanced, leave old assets; the next successful run can retry pruning.
# Re-fetch immediately before computing deletions. The per-repository concurrency
# group serializes callers; the source SHA guard also retains same-commit assets.
assert_fresh_main
load_remote_inventory "$inventory"
python - "$inventory" "$expected_local" "$PRODUCT_PREFIX" "$SOURCE_SHA" <<'PY' > "$tmp/obsolete-asset-ids.txt"
import sys
from pathlib import Path

inventory_path, names_path, product, source_sha = sys.argv[1:]
current = set(Path(names_path).read_text(encoding="utf-8").splitlines())
prefix = f"rolling-{product}-"
for line in Path(inventory_path).read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if len(fields) != 4:
        raise SystemExit("GitHub returned a malformed release-asset inventory row")
    name, _size, _digest, asset_id = fields
    if name.startswith(prefix) and name not in current and source_sha not in name:
        if not asset_id.isdigit() or int(asset_id) <= 0:
            raise SystemExit(f"invalid GitHub asset ID for {name}")
        print(asset_id)
PY
while IFS= read -r asset_id; do
  [[ -n "$asset_id" ]] || continue
  gh api --method DELETE "repos/$REPOSITORY/releases/assets/$asset_id" >/dev/null
done < "$tmp/obsolete-asset-ids.txt"

echo "Published verified rolling prerelease: $REPOSITORY/releases/tag/latest"
echo "Source commit: $SOURCE_SHA"
echo "Manifest: $MANIFEST_NAME ($manifest_sha)"
