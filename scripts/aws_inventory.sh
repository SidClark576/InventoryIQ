#!/usr/bin/env bash
# Read-only inventory of the InventoryIQ AWS account via profile `inventoryiq`.
# Does not mutate resources. Writes JSON to stdout.
set -euo pipefail

PROFILE="${AWS_PROFILE:-inventoryiq}"
REGION="${AWS_REGION:-us-east-1}"

echo "Using profile=${PROFILE} region=${REGION}" >&2

aws --profile "$PROFILE" --region "$REGION" sts get-caller-identity
echo "---"
aws --profile "$PROFILE" --region "$REGION" lambda list-functions \
  --query 'Functions[].{name:FunctionName,runtime:Runtime,updated:LastModified}' \
  --output table
echo "---"
aws --profile "$PROFILE" --region "$REGION" dynamodb list-tables --output table
echo "---"
aws --profile "$PROFILE" --region "$REGION" apigateway get-rest-apis \
  --query 'items[].{id:id,name:name}' --output table || true
