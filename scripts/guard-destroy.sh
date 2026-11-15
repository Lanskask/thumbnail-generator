#!/usr/bin/env bash
# Guarded "delete from the old provider" helper.
#
# Usage: guard-destroy.sh <provider> <resource-name> <command>...
#   provider        must differ from $DEPLOY_TARGET (never delete the live target)
#   resource-name   you must type it back to confirm
#   command...      each argument is one shell command, run in order
#
# Default is a DRY RUN: the commands are printed and nothing is executed.
# Set APPLY=1 to execute. The Cloudflare copy must answer (CLOUDFLARE_URL)
# unless FORCE=1.
set -euo pipefail

provider="${1:?provider}"; resource="${2:?resource name}"; shift 2

if [[ "${DEPLOY_TARGET:-}" == "$provider" ]]; then
  echo "Refusing: DEPLOY_TARGET=$provider is the active target. Switch DEPLOY_TARGET first." >&2
  exit 1
fi

if [[ "${FORCE:-0}" != "1" ]]; then
  if [[ -z "${CLOUDFLARE_URL:-}" ]]; then
    echo "Refusing: set CLOUDFLARE_URL=https://... so I can check the Cloudflare copy first (or FORCE=1)." >&2
    exit 1
  fi
  if ! curl -fsS -o /dev/null --max-time 15 "$CLOUDFLARE_URL"; then
    echo "Refusing: $CLOUDFLARE_URL did not answer 2xx. Fix the Cloudflare deploy first (or FORCE=1)." >&2
    exit 1
  fi
  echo "OK: $CLOUDFLARE_URL is serving."
fi

echo "Would delete '$resource' from $provider by running:"
for c in "$@"; do echo "  \$ $c"; done

if [[ "${APPLY:-0}" != "1" ]]; then
  echo "Dry run only. Re-run with APPLY=1 to execute."
  exit 0
fi

read -r -p "Type the name '$resource' to confirm deletion: " typed
if [[ "$typed" != "$resource" ]]; then echo "Name did not match. Aborted." >&2; exit 1; fi

for c in "$@"; do echo "\$ $c"; bash -c "$c"; done
