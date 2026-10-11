#!/usr/bin/env bash
# Package Lambda zips and print (or apply) update-function-code commands.
# Default is dry-run. Pass --apply to upload. Never run from CI.
set -euo pipefail

# aws cli dumps full function JSON; pager made --apply look hung on AddItem.
export AWS_PAGER=""

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${AWS_PROFILE:-inventoryiq}"
REGION="${AWS_REGION:-us-east-1}"
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

PYTHON_FNS=(
  Proxy AddItem GetAllItems UpdateItem DeleteItem RestoreItem
  GetCategories DeleteCategory GetTransactions LowItemInsight
  BulkImport BulkImportAsync BarcodeLookup
  DailyAlert CascadeDeleteUser PurgeDeletedItems Orgs OrgMembers OrgInvites
)
NODE_FNS=(Authentication Authorizer)

pack_python() {
  local name="$1"
  local zip="$ROOT/lambda/${name}.zip"
  rm -f "$zip"
  (
    cd "$ROOT/lambda"
    zip -q "$zip" "${name}.py" _logging.py _org.py
    if grep -q 'sentry_sdk\|_logging' "${name}.py" 2>/dev/null; then
      zip -q -r "$zip" python_vendor || true
    fi
  )
  echo "$zip"
}

pack_node() {
  local name="$1"
  local zip="$ROOT/lambda/${name}.zip"
  rm -f "$zip"
  (cd "$ROOT/lambda" && zip -q "$zip" "${name}.mjs")
  echo "$zip"
}

for fn in "${PYTHON_FNS[@]}"; do
  [[ -f "$ROOT/lambda/${fn}.py" ]] || continue
  zip=$(pack_python "$fn")
  cmd=(aws --profile "$PROFILE" --region "$REGION" lambda update-function-code
       --function-name "$fn" --zip-file "fileb://$zip"
       --query '{FunctionName:FunctionName,LastUpdateStatus:LastUpdateStatus}' --output json)
  if [[ "$APPLY" -eq 1 ]]; then
    if ! "${cmd[@]}"; then
      echo "  skip $fn (not in this account or update failed)"
      continue
    fi
    aws --profile "$PROFILE" --region "$REGION" lambda wait function-updated --function-name "$fn"
  else
    printf '%q ' "${cmd[@]}"; echo
  fi
done

for fn in "${NODE_FNS[@]}"; do
  [[ -f "$ROOT/lambda/${fn}.mjs" ]] || continue
  zip=$(pack_node "$fn")
  cmd=(aws --profile "$PROFILE" --region "$REGION" lambda update-function-code
       --function-name "$fn" --zip-file "fileb://$zip"
       --query '{FunctionName:FunctionName,LastUpdateStatus:LastUpdateStatus}' --output json)
  if [[ "$APPLY" -eq 1 ]]; then
    if ! "${cmd[@]}"; then
      echo "  skip $fn (not in this account or update failed)"
      continue
    fi
    aws --profile "$PROFILE" --region "$REGION" lambda wait function-updated --function-name "$fn"
  else
    printf '%q ' "${cmd[@]}"; echo
  fi
done
