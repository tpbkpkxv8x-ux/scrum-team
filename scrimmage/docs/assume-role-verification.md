# Assume-Role Flow Verification Guide

**IAM Security**

This document provides manual verification steps for the assume-role flow with MFA. The automated tests in this repo verify the non-interactive components; this guide covers the interactive TOTP authentication flow.

## Prerequisites

- IAM stack deployed (`<project-name>-Developer` role exists)
- Virtual MFA device configured on IAM user
- `scrimmage/tools/assume-deploy-role.sh` script present

## Automated Pre-Checks

Run the automated component tests first:

```bash
# Test non-interactive components
bash scrimmage/tools/test_assume_role_components.sh
```

Expected output: All 5 tests pass (MFA detection, role exists, current identity, trust policy, MFA requirement).

## Manual Verification Steps

### Step 1: Test Assume-Role Flow

```bash
# Source the script (must use 'source' to set env vars in current shell)
source scrimmage/tools/assume-deploy-role.sh
```

**Expected behavior:**
1. Script detects MFA device: `MFA device found: arn:aws:iam::<ACCOUNT_ID>:mfa/<iam-username>`
2. Prompts: `Enter MFA token: `
3. Enter 6-digit TOTP code from authenticator app
4. Script calls `aws sts assume-role` with MFA
5. Exports temporary credentials to shell

**Success output:**
```
Successfully assumed role: <project-name>-Developer
Session expires: 2026-02-10T22:45:00Z

Temporary credentials have been exported to your shell environment.
```

### Step 2: Verify Identity

```bash
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AROAVLQSGNIZ...:dev-{user}-{timestamp}",
    "Account": "<ACCOUNT_ID>",
    "Arn": "arn:aws:sts::<ACCOUNT_ID>:assumed-role/<project-name>-Developer/dev-{user}-{timestamp}"
}
```

**Key indicator:** ARN contains `assumed-role/<project-name>-Developer`, not `user/<iam-username>`.

### Step 3: Test CDK Deploy with Temp Credentials

```bash
cd infra
npx cdk deploy <role-name> --require-approval never
```

**Expected behavior:**
- CDK synthesizes successfully
- CloudFormation deployment starts
- No permission errors
- Deployment completes (or shows "No changes")

**Note:** The scoped policy should be sufficient for all CDK operations. If you get permission errors, the policy may need adjustment.

### Step 4: Test Branch Deploy Script

```bash
# Just verify it starts (can Ctrl-C after it begins)
./scrimmage/branch_deploy.sh ../worktrees/test-feature
```

**Expected behavior:**
- Script detects temporary credentials
- Does NOT show warning: "Using static IAM credentials"
- Proceeds with deployment steps

### Step 5: Verify Credential Expiry

```bash
# Check the expiry time (set when you ran assume-deploy-role.sh)
echo $AWS_SESSION_TOKEN | cut -c1-20  # Should be set

# After expiry (default 1 hour), try AWS command
aws sts get-caller-identity
```

**Expected after expiry:** `ExpiredToken` error, requiring re-running `assume-deploy-role.sh`.

## Acceptance Criteria Checklist

- [ ] `aws sts get-caller-identity` shows `assumed-role/<project-name>-Developer` ARN
- [ ] CDK deploy succeeds with temporary credentials
- [ ] scrimmage/branch_deploy.sh works with temporary credentials (no static key warning)
- [ ] Credentials expire after the configured duration
- [ ] No AdministratorAccess required (scoped policy is sufficient)

## Troubleshooting

### Invalid MFA Token

**Error:** `An error occurred (AccessDenied) when calling the AssumeRole operation: MultiFactorAuthentication failed with invalid MFA one time pass code.`

**Causes:**
- Token expired (TOTP codes change every 30 seconds)
- Token already used (can't reuse the same code)
- Clock skew between device and AWS

**Solution:** Wait for next TOTP code and try again.

### No MFA Device

**Error:** `ERROR: No MFA device configured.`

**Solution:** Set up virtual MFA in AWS Console (see the MFA setup backlog item).

### Permission Denied

**Error:** `User: arn:aws:iam::<ACCOUNT_ID>:user/<iam-username> is not authorized to perform: sts:AssumeRole`

**Solution:** Verify the IAM user has `sts:AssumeRole` permission for the `<project-name>-Developer` role.

### Session Duration Too Long

**Error:** `DurationSeconds exceeds the MaxSessionDuration`

**Solution:** The role's `MaxSessionDuration` is 12 hours (43200 seconds). Don't request longer sessions.
