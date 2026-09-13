#!/usr/bin/env bash
# Verify that Kconfig preserved every request in r46h.fragment.

set -euo pipefail

usage() {
	printf 'usage: %s <final-.config>\n' "${0##*/}" >&2
}

if [[ $# -ne 1 ]]; then
	usage
	exit 2
fi

config=$1
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
fragment="$script_dir/r46h.fragment"

if [[ ! -f "$config" ]]; then
	printf 'error: final kernel config not found: %s\n' "$config" >&2
	exit 2
fi

if [[ ! -f "$fragment" ]]; then
	printf 'error: fragment not found: %s\n' "$fragment" >&2
	exit 2
fi

checked=0
failed=0

while IFS= read -r expected || [[ -n "$expected" ]]; do
	case "$expected" in
		CONFIG_*=*)
			symbol=${expected%%=*}
			;;
		'# CONFIG_'*' is not set')
			symbol=${expected#\# }
			symbol=${symbol% is not set}
			;;
		*)
			continue
			;;
	esac

	checked=$((checked + 1))
	if grep -Fqx "$expected" "$config"; then
		continue
	fi

	failed=$((failed + 1))
	printf 'mismatch: %s\n' "$symbol" >&2
	printf '  requested: %s\n' "$expected" >&2
	actual=$(grep -E "^${symbol}=|^# ${symbol} is not set$" "$config" || true)
	if [[ -n "$actual" ]]; then
		printf '  actual:    %s\n' "$actual" >&2
	else
		printf '  actual:    <symbol absent from final config>\n' >&2
	fi
done < "$fragment"

if (( failed != 0 )); then
	printf 'R46H config validation failed: %d of %d requests mismatch.\n' \
		"$failed" "$checked" >&2
	exit 1
fi

printf 'R46H config validation passed: %d requests match.\n' "$checked"
