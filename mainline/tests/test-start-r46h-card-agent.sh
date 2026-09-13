#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
WRAPPER="$REPO_ROOT/mainline/scripts/start-r46h-card-agent.sh"
LEGACY_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-v1.json"
NEW_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json"
RECOVERED_NEW_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-p3-recovery-v1.json"
FAST_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-62534975488-v1.json"

LEGACY_ID=hl-r46h-v22-g92-v1
NEW_CARD_ID=hl-r46h-v22-g92-31719424000-v1
RECOVERED_NEW_CARD_ID=hl-r46h-v22-g92-31719424000-p3-recovery-v1
FAST_CARD_ID=hl-r46h-v22-g92-62534975488-v1
LEGACY_SHA=1c4f0d7116294085d59d5e60e08480c7ac715eddb4d839d0cbdaab605de8beb1
NEW_CARD_SHA=fc14a1f0fefbccc281e0b6887e78986cbaca0a9205ca2167ea338c41e9839a7b
RECOVERED_NEW_CARD_SHA=13a44b40cc68bfd9d172e708c46c3d9758748ff6d6df394a10c5ab2b0358fc24
FAST_CARD_SHA=2066603fad59102ccb9b39851962ef8224d1a45f8a672c097ad5b91d45f4e20b

/bin/bash -n "$WRAPPER"

help=$(/bin/bash "$WRAPPER" --help)
[[ "$help" == *"--profile-id ID"* ]]
[[ "$help" == *"default: $LEGACY_ID"* ]]

failure=
if failure=$(/bin/bash "$WRAPPER" --profile-id unsupported-profile 2>&1); then
  echo "ERROR: unsupported profile unexpectedly passed wrapper parsing" >&2
  exit 1
fi
[[ "$failure" == *"unsupported card profile ID: unsupported-profile"* ]]

[[ "$(/usr/bin/shasum -a 256 "$LEGACY_PROFILE" | /usr/bin/awk '{print $1}')" == "$LEGACY_SHA" ]]
[[ "$(/usr/bin/shasum -a 256 "$NEW_CARD_PROFILE" | /usr/bin/awk '{print $1}')" == "$NEW_CARD_SHA" ]]
[[ "$(/usr/bin/shasum -a 256 "$RECOVERED_NEW_CARD_PROFILE" | /usr/bin/awk '{print $1}')" == "$RECOVERED_NEW_CARD_SHA" ]]
[[ "$(/usr/bin/shasum -a 256 "$FAST_CARD_PROFILE" | /usr/bin/awk '{print $1}')" == "$FAST_CARD_SHA" ]]

/usr/bin/grep -Fqx "DEFAULT_PROFILE_ID=$LEGACY_ID" "$WRAPPER"
/usr/bin/grep -Fqx "PROFILE_ID=\$DEFAULT_PROFILE_ID" "$WRAPPER"
/usr/bin/grep -Fqx "LEGACY_PROFILE_SHA256=$LEGACY_SHA" "$WRAPPER"
/usr/bin/grep -Fqx "NEW_CARD_PROFILE_SHA256=$NEW_CARD_SHA" "$WRAPPER"
/usr/bin/grep -Fqx "RECOVERED_NEW_CARD_PROFILE_SHA256=$RECOVERED_NEW_CARD_SHA" "$WRAPPER"
/usr/bin/grep -Fqx "FAST_CARD_PROFILE_SHA256=$FAST_CARD_SHA" "$WRAPPER"

for profile_id in "$LEGACY_ID" "$NEW_CARD_ID" "$RECOVERED_NEW_CARD_ID" "$FAST_CARD_ID"; do
  [[ "$(/usr/bin/grep -Fc "  $profile_id)" "$WRAPPER")" -eq 1 ]]
done
[[ "$(/usr/bin/grep -Ec '^  [A-Za-z0-9._-]+\)$' "$WRAPPER")" -eq 4 ]]

echo "PASS: Card Agent wrapper defaults to the legacy profile and pins exactly four audited profiles."
