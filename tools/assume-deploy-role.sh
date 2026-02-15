#!/usr/bin/env bash
# =============================================================================
# Assume Deploy Role with MFA
# =============================================================================
#
# This script helps developers obtain temporary AWS credentials by assuming
# the deploy role with MFA authentication. The resulting credentials
# expire after 12 hours (configurable) and require MFA, improving security over
# long-lived static keys.
#
# Usage:
#   source tools/assume-deploy-role.sh              # 12 hour session (default)
#   source tools/assume-deploy-role.sh 3600         # 1 hour session
#
# After sourcing this script, your shell will have temporary credentials set
# as environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN).
#
# Requirements:
#   - AWS CLI installed
#   - IAM user with sts:AssumeRole permission for the deploy role
#   - MFA device configured on your IAM user
#
# =============================================================================

# NOTE: We don't use 'set -euo pipefail' because this script is intended to be
# sourced, and setting those options would affect the caller's shell environment.
# Instead, we handle errors explicitly.

# ─── Configuration ────────────────────────────────────────────────────────────
ROLE_ARN="${DEPLOY_ROLE_ARN:?Set DEPLOY_ROLE_ARN env var to your IAM role ARN (e.g. arn:aws:iam::123456789012:role/MyProject-Developer)}"
SESSION_NAME="deploy-$(whoami)-$(date +%s)"
DURATION="${1:-43200}"  # Default: 12 hours (43200s), max: 12 hours (43200s)

# ─── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No color

# ─── Get MFA device ARN ───────────────────────────────────────────────────────
echo -e "${YELLOW}Fetching MFA device...${NC}"
MFA_SERIAL=$(aws iam list-mfa-devices --query 'MFADevices[0].SerialNumber' --output text 2>/dev/null)

if [[ -z "$MFA_SERIAL" ]] || [[ "$MFA_SERIAL" == "None" ]]; then
  echo -e "${RED}ERROR: No MFA device configured.${NC}" >&2
  echo "" >&2
  echo "Please set up a virtual MFA device:" >&2
  echo "  1. Go to: https://console.aws.amazon.com/iam" >&2
  echo "  2. Navigate to: Your Security Credentials → Multi-factor authentication (MFA)" >&2
  echo "  3. Click: Assign MFA device" >&2
  echo "  4. Choose: Authenticator app" >&2
  echo "  5. Scan the QR code with your authenticator app (e.g., Google Authenticator, Authy)" >&2
  echo "" >&2
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

echo -e "${GREEN}✓ MFA device found: ${MFA_SERIAL}${NC}"

# ─── Prompt for MFA token ─────────────────────────────────────────────────────
echo ""
read -r -p "Enter MFA token: " MFA_TOKEN

if [[ -z "$MFA_TOKEN" ]]; then
  echo -e "${RED}ERROR: MFA token cannot be empty${NC}" >&2
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

# ─── Assume role ──────────────────────────────────────────────────────────────
echo -e "${YELLOW}Assuming role ${ROLE_ARN}...${NC}"

if ! CREDS=$(aws sts assume-role \
  --role-arn "$ROLE_ARN" \
  --role-session-name "$SESSION_NAME" \
  --serial-number "$MFA_SERIAL" \
  --token-code "$MFA_TOKEN" \
  --duration-seconds "$DURATION" \
  --output json 2>&1); then
  echo -e "${RED}ERROR: Failed to assume role${NC}" >&2
  echo "" >&2
  echo "AWS CLI output:" >&2
  echo "$CREDS" >&2
  echo "" >&2
  echo "Common issues:" >&2
  echo "  - Invalid MFA token (they expire after ~30 seconds)" >&2
  echo "  - MFA token already used (wait for next token)" >&2
  echo "  - IAM user lacks sts:AssumeRole permission" >&2
  echo "  - Role trust policy doesn't allow your IAM user" >&2
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

# ─── Extract credentials using python ─────────────────────────────────────────
# NOTE: We use python3 instead of jq because jq may not be installed in all
# environments. Python3 is already a dependency for our backend.

AWS_ACCESS_KEY_ID=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['AccessKeyId'])" 2>/dev/null)
AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['SecretAccessKey'])" 2>/dev/null)
AWS_SESSION_TOKEN=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['SessionToken'])" 2>/dev/null)
EXPIRATION=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['Expiration'])" 2>/dev/null)

if [[ -z "$AWS_ACCESS_KEY_ID" ]] || [[ -z "$AWS_SECRET_ACCESS_KEY" ]] || [[ -z "$AWS_SESSION_TOKEN" ]]; then
  echo -e "${RED}ERROR: Failed to extract credentials from AWS response${NC}" >&2
  echo "This is unexpected — please check the script." >&2
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

# ─── Export credentials ───────────────────────────────────────────────────────
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN

# ─── Success message ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✓ Successfully assumed role: ${ROLE_ARN##*/}${NC}"
echo -e "${GREEN}✓ Session expires: ${EXPIRATION}${NC}"
echo ""
echo "Temporary credentials have been exported to your shell environment."
echo "You can now run AWS commands (aws, cdk, etc.) and they will use these credentials."
echo ""
echo "Examples:"
echo "  aws sts get-caller-identity                    # Verify you're using the role"
echo "  cd infra && npx cdk deploy --all               # Deploy with temp credentials"
echo "  ./branch_deploy.sh ../worktrees/my-feature     # Branch deploy with temp creds"
echo ""
# Display expiration time in a human-friendly format
if [[ $DURATION -ge 3600 ]]; then
  HOURS=$(( DURATION / 3600 ))
  REMAINING_SECONDS=$(( DURATION % 3600 ))
  MINUTES=$(( REMAINING_SECONDS / 60 ))

  if [[ $MINUTES -eq 0 ]]; then
    # Whole hours (e.g., 12 hours)
    if [[ $HOURS -eq 1 ]]; then
      echo -e "${YELLOW}Remember: These credentials expire in 1 hour!${NC}"
    else
      echo -e "${YELLOW}Remember: These credentials expire in ${HOURS} hours!${NC}"
    fi
  else
    # Hours + minutes (e.g., 1 hour 30 minutes)
    if [[ $HOURS -eq 1 ]]; then
      echo -e "${YELLOW}Remember: These credentials expire in 1 hour ${MINUTES} minutes!${NC}"
    else
      echo -e "${YELLOW}Remember: These credentials expire in ${HOURS} hours ${MINUTES} minutes!${NC}"
    fi
  fi
else
  # Less than 1 hour, show in minutes
  echo -e "${YELLOW}Remember: These credentials expire in $(( DURATION / 60 )) minutes!${NC}"
fi
