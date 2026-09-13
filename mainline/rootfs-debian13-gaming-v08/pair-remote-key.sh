#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly EXPECTED_UUID=d3130008-46a4-4d56-9001-000000000008
readonly STAGE=/run/r46h-pair-v0.8
readonly SCRIPT=$STAGE/pair-remote-key.sh
readonly PUBLIC_KEY=$STAGE/operator.pub
readonly AUTHORIZED_KEYS=/home/ark/.ssh/authorized_keys
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly RECEIPT=/var/lib/r46h/remote-pair-v0.8
readonly GATEWAY_SHA256=1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da
readonly SUDOERS_SHA256=2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

[[ $# == 4 && $1 == --script-sha256 && $3 == --public-key-sha256 ]] || \
  die 'usage: pair-remote-key.sh --script-sha256 SHA256 --public-key-sha256 SHA256'
script_sha256=$2
public_key_sha256=$4
[[ $script_sha256 =~ ^[0-9a-f]{64}$ && $public_key_sha256 =~ ^[0-9a-f]{64}$ ]] || \
  die 'invalid SHA-256 argument'
(( EUID == 0 )) || die 'root is required'
[[ $(realpath -- "$0") == "$SCRIPT" ]] || die 'run the fixed staged script'
[[ -d $STAGE && ! -L $STAGE && $(stat -c '%u:%g:%a' "$STAGE") == 0:0:700 ]] || \
  die 'unsafe staging directory'
for path in "$SCRIPT" "$PUBLIC_KEY"; do
  [[ -f $path && ! -L $path && $(stat -c '%u:%g:%a:%h' "$path") == 0:0:600:1 ]] || \
    die "unsafe staged file: $path"
done
[[ $(hash_file "$SCRIPT") == "$script_sha256" ]] || die 'staged script digest mismatch'
[[ $(hash_file "$PUBLIC_KEY") == "$public_key_sha256" ]] || die 'public key digest mismatch'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_UUID" ]] || die 'unexpected root filesystem'
[[ -f $GATEWAY && ! -L $GATEWAY && $(hash_file "$GATEWAY") == "$GATEWAY_SHA256" ]] || \
  die 'remote gateway identity mismatch'
[[ -f $SUDOERS && ! -L $SUDOERS && $(hash_file "$SUDOERS") == "$SUDOERS_SHA256" ]] || \
  die 'remote sudo policy identity mismatch'
visudo -cf "$SUDOERS" >/dev/null || die 'remote sudo policy is invalid'

mapfile -t key_lines < "$PUBLIC_KEY"
(( ${#key_lines[@]} == 1 )) || die 'public key must contain exactly one line'
key_line=${key_lines[0]}
read -r key_type key_blob key_comment <<< "$key_line"
[[ $key_type == ssh-ed25519 && $key_blob =~ ^[A-Za-z0-9+/]+={0,2}$ ]] || \
  die 'only one OpenSSH ED25519 public key is accepted'
[[ -n $key_comment && $key_comment != *$'\t'* ]] || die 'public key comment is required'
key_fingerprint=$(ssh-keygen -lf "$PUBLIC_KEY" -E sha256 | awk '{print $2}')
[[ $key_fingerprint == SHA256:* ]] || die 'cannot fingerprint public key'
authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"

if [[ -e $RECEIPT || -L $RECEIPT ]]; then
  [[ -f $RECEIPT && ! -L $RECEIPT && $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || \
    die 'unsafe pairing receipt'
  grep -Fqx "public_key_sha256=$public_key_sha256" "$RECEIPT" || \
    die 'a different key is already paired'
  grep -Fqx -- "$authorized_line" "$AUTHORIZED_KEYS" || die 'paired key line is missing'
  printf 'R46H_REMOTE_PAIR result=pass status=already-paired fingerprint=%s\n' "$key_fingerprint"
  exit 0
fi

if [[ -e /home/ark/.ssh || -L /home/ark/.ssh ]]; then
  [[ -d /home/ark/.ssh && ! -L /home/ark/.ssh && \
     $(stat -c '%u:%g:%a' /home/ark/.ssh) == 1000:1000:700 ]] || die 'unsafe SSH directory'
else
  install -d -o ark -g ark -m 0700 /home/ark/.ssh
fi
stage=$STAGE/.authorized_keys.$$
if [[ -e $AUTHORIZED_KEYS || -L $AUTHORIZED_KEYS ]]; then
  [[ -f $AUTHORIZED_KEYS && ! -L $AUTHORIZED_KEYS && \
     $(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS") == 1000:1000:600:1 ]] || \
    die 'unsafe authorized_keys'
  grep -Fq -- "$key_blob" "$AUTHORIZED_KEYS" && die 'public key already has different authorization'
  install -o ark -g ark -m 0600 "$AUTHORIZED_KEYS" "$stage"
  [[ ! -s $stage || $(tail -c 1 "$stage" | od -An -tu1 | tr -d '[:space:]') == 10 ]] || \
    printf '\n' >> "$stage"
else
  install -o ark -g ark -m 0600 /dev/null "$stage"
fi
printf '%s\n' "$authorized_line" >> "$stage"
mv -f -- "$stage" "$AUTHORIZED_KEYS"

receipt_stage=/var/lib/r46h/.remote-pair-v0.8.$$
printf 'feature_id=r46h-remote-pair-v0.8\npublic_key_sha256=%s\npublic_key_fingerprint=%s\nscript_sha256=%s\n' \
  "$public_key_sha256" "$key_fingerprint" "$script_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
mv -T -- "$receipt_stage" "$RECEIPT"
sync
printf 'R46H_REMOTE_PAIR result=pass status=paired fingerprint=%s\n' "$key_fingerprint"
