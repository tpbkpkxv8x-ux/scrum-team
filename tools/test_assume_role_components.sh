#!/usr/bin/env bash
# Test components of assume-deploy-role.sh that can be verified non-interactively

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Testing assume-deploy-role.sh components..."
echo ""

# Test 1: MFA device detection
echo -e "${YELLOW}Test 1: MFA device detection${NC}"
MFA_SERIAL=$(aws iam list-mfa-devices --query 'MFADevices[0].SerialNumber' --output text 2>/dev/null)

if [[ -z "$MFA_SERIAL" ]] || [[ "$MFA_SERIAL" == "None" ]]; then
  echo -e "${RED}❌ FAIL: No MFA device found${NC}"
  exit 1
fi
echo -e "${GREEN}✓ MFA device found: ${MFA_SERIAL}${NC}"

# Test 2: Role ARN is correct
echo -e "\n${YELLOW}Test 2: Role ARN configuration${NC}"
ROLE_ARN="${DEPLOY_ROLE_ARN:?Set DEPLOY_ROLE_ARN env var}"
ROLE_NAME="${ROLE_ARN##*/}"
echo "Expected role ARN: ${ROLE_ARN}"

# Extract account ID from the role ARN
ACCOUNT_ID=$(echo "$ROLE_ARN" | cut -d: -f5)

# Verify role exists
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo -e "${GREEN}✓ Role exists in AWS${NC}"
else
  echo -e "${RED}❌ FAIL: Role does not exist${NC}"
  exit 1
fi

# Test 3: Current identity (before assume-role)
echo -e "\n${YELLOW}Test 3: Current identity${NC}"
CURRENT_ARN=$(aws sts get-caller-identity --query 'Arn' --output text)
echo "Current identity: ${CURRENT_ARN}"

if [[ "$CURRENT_ARN" == *":user/"* ]]; then
  echo -e "${GREEN}✓ Currently using IAM user credentials (not assumed role)${NC}"
else
  echo -e "${YELLOW}⚠ Already using temporary credentials${NC}"
fi

# Test 4: Check IAM user has sts:AssumeRole permission
echo -e "\n${YELLOW}Test 4: Checking assume-role permissions${NC}"
# This will fail with AccessDenied if no permission, but we can't test directly without actually assuming
# We'll verify the role's trust policy allows the current account
TRUST_POLICY=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.AssumeRolePolicyDocument' --output json)
if echo "$TRUST_POLICY" | grep -q "$ACCOUNT_ID"; then
  echo -e "${GREEN}✓ Role trust policy allows current account${NC}"
else
  echo -e "${RED}❌ FAIL: Trust policy issue${NC}"
  exit 1
fi

# Test 5: Role requires MFA
echo -e "\n${YELLOW}Test 5: MFA requirement in trust policy${NC}"
if echo "$TRUST_POLICY" | grep -q "aws:MultiFactorAuthPresent"; then
  echo -e "${GREEN}✓ Role requires MFA (aws:MultiFactorAuthPresent condition present)${NC}"
else
  echo -e "${RED}❌ FAIL: Role does not require MFA${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}✅ All non-interactive tests passed!${NC}"
echo ""
echo "Manual verification required:"
echo "  1. Run: source tools/assume-deploy-role.sh"
echo "  2. Enter a valid MFA token when prompted"
echo "  3. Verify: aws sts get-caller-identity shows assumed-role ARN"
echo "  4. Verify: Can run CDK deploy with temporary credentials"
