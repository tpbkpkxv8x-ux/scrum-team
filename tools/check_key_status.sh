#!/usr/bin/env bash
# =============================================================================
# Check Status of IAM Access Keys
# =============================================================================
#
# This script checks the status of IAM access keys for the specified user.
# Use this to verify key deactivation before and after running the deactivation
# procedure.
#
# Usage:
#   ./tools/check_key_status.sh <iam-username>
#
# =============================================================================

set -euo pipefail

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

USERNAME="${1:?Usage: $0 <iam-username>}"

echo -e "${BLUE}Checking IAM access keys for user: ${USERNAME}${NC}"
echo ""

# Get access keys
KEYS=$(aws iam list-access-keys --user-name "$USERNAME" --output json)

# Parse and display
echo "$KEYS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
keys = data.get('AccessKeyMetadata', [])

if not keys:
    print('No access keys found for this user.')
    sys.exit(0)

for key in keys:
    key_id = key['AccessKeyId']
    status = key['Status']
    created = key['CreateDate']

    # Color based on status
    if status == 'Active':
        status_color = '\033[0;31m'  # Red
        status_symbol = '⚠️ '
    else:
        status_color = '\033[0;32m'  # Green
        status_symbol = '✓ '

    print(f'{status_symbol}Access Key ID: {key_id}')
    print(f'  Status: {status_color}{status}\033[0m')
    print(f'  Created: {created}')
    print()
"

echo ""
echo "Current AWS identity:"
CURRENT_ARN=$(aws sts get-caller-identity --query 'Arn' --output text)
echo "  ${CURRENT_ARN}"

if [[ "$CURRENT_ARN" == *":user/"* ]]; then
    echo -e "  ${YELLOW}(Using static IAM user credentials)${NC}"
elif [[ "$CURRENT_ARN" == *":assumed-role/"* ]]; then
    echo -e "  ${GREEN}(Using temporary assumed-role credentials)${NC}"
else
    echo -e "  ${BLUE}(Unknown credential type)${NC}"
fi

echo ""
