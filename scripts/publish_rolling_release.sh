#!/usr/bin/env bash
# Promote a fully verified, commit-qualified rolling product bundle to one fixed tag.
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${SOURCE_RUN_TOKEN:?SOURCE_RUN_TOKEN is required}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${SOURCE_BRANCH:?SOURCE_BRANCH is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${SOURCE_RUN_ID:?SOURCE_RUN_ID is required}"
: "${PRODUCT_PREFIX:?PRODUCT_PREFIX is required}"
: "${ASSET_DIRECTORY:?ASSET_DIRECTORY is required}"
: "${MANIFEST_NAME:?MANIFEST_NAME is required}"

if [[ "$SOURCE_BRANCH" != "main" ]]; then
  echo "Rolling product promotion is only permitted from main; got $SOURCE_BRANCH." >&2
  exit 2
fi
if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be a full lowercase Git commit SHA." >&2
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

api_json() {
  gh api "$@"
}

assert_fresh_main() {
  local current
  current="$(api_json "repos/$REPOSITORY/commits/main" --jq .sha)"
  if [[ "$current" != "$SOURCE_SHA" ]]; then
    echo "Refusing stale rolling run: main is $current, candidate is $SOURCE_SHA." >&2
    return 1
  fi
}

verify_source_run() {
  local run_file="$tmp/source-run.json"
  GH_TOKEN="$SOURCE_RUN_TOKEN" gh api "repos/$REPOSITORY/actions/runs/$SOURCE_RUN_ID" > "$run_file"
  jq -e     --arg repository "$REPOSITORY"     --arg sha "$SOURCE_SHA"     --arg branch "$SOURCE_BRANCH"     '(.event == "push") and
     (.conclusion == "success") and
     (.head_branch == $branch) and
     (.head_sha == $sha) and
     (.repository.full_name == $repository)'     "$run_file" >/dev/null
}

assert_fresh_main
verify_source_run
assert_fresh_main

manifest_path="$ASSET_DIRECTORY/$MANIFEST_NAME"
manifest_sha="$(sha256sum "$manifest_path" | awk '{print $1}')"
[[ -s "$manifest_path" ]]
[[ -s "$manifest_path.sha256" ]]
grep -Fxq "$manifest_sha  $MANIFEST_NAME" "$manifest_path.sha256"

expected_local="$(find "$ASSET_DIRECTORY" -maxdepth 1 -type f -printf '%f\n' | sort)"
if [[ -z "$expected_local" ]]; then
  echo "Rolling asset directory is empty." >&2
  exit 1
fi

# A single Release object backs the fixed 'latest' ref. Create it as a draft on
# first publication; retries reuse the same object and immutable asset names.
release_file="$tmp/release.json"
http_code="$(curl --silent --show-error --output "$release_file" --write-out '%{http_code}' \
  --header "Authorization: Bearer $GH_TOKEN" \
  --header 'Accept: application/vnd.github+json' \
  --header 'X-GitHub-Api-Version: 2022-11-28' \
  "https://api.github.com/repos/$REPOSITORY/releases/tags/latest")"
case "$http_code" in
  200)
    release_id="$(jq -r '.id' "$release_file")"
    ;;
  404)
    initial_body="Rolling product candidate is being staged. This draft is not a published distribution."
    gh api --method POST "repos/$REPOSITORY/releases" \
      -f tag_name=latest \
      -f target_commitish="$SOURCE_SHA" \
      -f name="$PRODUCT_PREFIX rolling development (staging)" \
      -f body="$initial_body" \
      -F draft=true \
      -F prerelease=true > "$release_file"
    release_id="$(jq -r '.id' "$release_file")"
    ;;
  *)
    echo "Could not inspect the existing latest Release (HTTP $http_code)." >&2
    cat "$release_file" >&2
    exit 1
    ;;
esac

if [[ ! "$release_id" =~ ^[0-9]+$ ]]; then
  echo "GitHub returned an invalid rolling Release ID." >&2
  exit 1
fi

# Upload all commit-qualified assets except the top-level manifest first.
# Existing same-name assets are reusable only when both size and digest match;
# different bytes under one immutable source-SHA name are never overwritten.
while IFS= read -r asset; do
  [[ -n "$asset" ]] || continue
  name="$asset"
  asset_path="$ASSET_DIRECTORY/$asset"
  [[ "$name" == "$MANIFEST_NAME" || "$name" == "$MANIFEST_NAME.sha256" ]] && continue
  expected_sha="$(sha256sum "$asset_path" | awk '{print $1}')"
  expected_size="$(stat -c '%s' "$asset_path")"
  found="$(gh api --paginate "repos/$REPOSITORY/releases/$release_id/assets?per_page=100" \
    --jq ".[] | select(.name == \"$name\") | [.id, .size, .digest] | @tsv" | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    IFS=$'\t' read -r asset_id remote_size remote_digest <<< "$found"
    if [[ "$remote_size" != "$expected_size" || "$remote_digest" != "sha256:$expected_sha" ]]; then
      echo "Immutable rolling asset collision for $name; refusing to replace it." >&2
      exit 1
    fi
    continue
  fi
  gh release upload latest "$asset_path" --repo "$REPOSITORY"
done <<< "$expected_local"

# The manifest and its sidecar are uploaded only after all package assets.
for asset in "$manifest_path" "$manifest_path.sha256"; do
  name="$(basename "$asset")"
  asset_path="$asset"
  expected_sha="$(sha256sum "$asset_path" | awk '{print $1}')"
  expected_size="$(stat -c '%s' "$asset_path")"
  found="$(gh api --paginate "repos/$REPOSITORY/releases/$release_id/assets?per_page=100" \
    --jq ".[] | select(.name == \"$name\") | [.id, .size, .digest] | @tsv" | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    IFS=$'\t' read -r asset_id remote_size remote_digest <<< "$found"
    if [[ "$remote_size" != "$expected_size" || "$remote_digest" != "sha256:$expected_sha" ]]; then
      echo "Immutable rolling manifest collision for $name; refusing to replace it." >&2
      exit 1
    fi
    continue
  fi
  gh release upload latest "$asset" --repo "$REPOSITORY"
done

# Re-read the Release inventory from GitHub and require every candidate asset
# to be present with the exact byte count and SHA-256 digest before promotion.
inventory="$tmp/remote-assets.tsv"
gh api --paginate "repos/$REPOSITORY/releases/$release_id/assets?per_page=100" \
  --jq '.[] | [.name, (.size | tostring), (.digest // "")] | @tsv' > "$inventory"
while IFS= read -r asset; do
  [[ -n "$asset" ]] || continue
  name="$(basename "$asset")"
  expected_sha="$(sha256sum "$asset" | awk '{print $1}')"
  expected_size="$(stat -c '%s' "$asset")"
  row="$(awk -F '\t' -v name="$name" '$1 == name { print; exit }' "$inventory")"
  if [[ -z "$row" ]]; then
    echo "GitHub Release is missing candidate asset $name." >&2
    exit 1
  fi
  IFS=$'\t' read -r remote_name remote_size remote_digest <<< "$row"
  if [[ "$remote_size" != "$expected_size" || "$remote_digest" != "sha256:$expected_sha" ]]; then
    echo "GitHub Release has a digest/size mismatch for $name." >&2
    exit 1
  fi
done <<< "$expected_local"

# Recheck immediately before moving the mutable ref. A newer main push makes
# this run stale; uploaded assets remain unreferenced and are safe to retry/prune.
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

gh api --method PATCH "repos/$REPOSITORY/releases/$release_id" \
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

# Do not prune if main advanced while the Release was being finalized. The next
# successful run can safely remove these older assets after its own promotion.
assert_fresh_main
current_names="$tmp/current-assets.txt"
printf '%s\n' "$expected_local" > "$current_names"
while IFS=$'\t' read -r name size digest; do
  [[ "$name" == "rolling-$PRODUCT_PREFIX-"* ]] || continue
  if ! grep -Fxq "$name" "$current_names"; then
    asset_id="$(gh api --paginate "repos/$REPOSITORY/releases/$release_id/assets?per_page=100" \
      --jq ".[] | select(.name == \"$name\") | .id" | head -n 1)"
    if [[ "$asset_id" =~ ^[0-9]+$ ]]; then
      gh api --method DELETE "repos/$REPOSITORY/releases/assets/$asset_id" >/dev/null
    fi
  fi
done < "$inventory"

echo "Published verified rolling prerelease: $REPOSITORY/releases/tag/latest"
echo "Source commit: $SOURCE_SHA"
echo "Manifest: $MANIFEST_NAME ($manifest_sha)"
