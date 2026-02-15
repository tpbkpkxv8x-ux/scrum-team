# Static IAM Key Deactivation Runbook

**CRITICAL SAFETY PROCEDURE**

This runbook covers deactivating static IAM access keys after verifying the assume-role flow works. Follow each step carefully and verify success before proceeding.

## Prerequisites

**MUST BE COMPLETED FIRST:**

- IAM stack deployed
- Virtual MFA device configured
- **Assume-role flow verified working**
  - You have successfully run `source scrimmage/tools/assume-deploy-role.sh`
  - You have verified `aws sts get-caller-identity` shows assumed-role ARN
  - You have tested CDK deploy with temporary credentials
  - You have tested scrimmage/branch_deploy.sh with temporary credentials

**DO NOT PROCEED** if assume-role flow has not been verified end-to-end by a human.

## Current State Documentation

### Step 1: Document Current Access Keys

```bash
# List current access keys
aws iam list-access-keys --user-name <iam-username>
```

**Expected output:**
```json
{
    "AccessKeyMetadata": [
        {
            "UserName": "<iam-username>",
            "AccessKeyId": "AKIA...............",
            "Status": "Active",
            "CreateDate": "..."
        }
    ]
}
```

**Record this information:**
- Access Key ID: (from output above)
- Current Status: `Active`
- Create Date: (from output above)

### Step 2: Verify Current Credentials in Use

```bash
# Check current identity (should be IAM user with static creds)
aws sts get-caller-identity
```

**Expected:**
```json
{
    "Arn": "arn:aws:iam::<ACCOUNT_ID>:user/<iam-username>",
    ...
}
```

If you see `assumed-role` in the ARN, you're already using temporary credentials. That's fine - the static key is still active in IAM and needs to be deactivated.

## Deactivation Procedure

### Step 3: Deactivate Static Key

**POINT OF NO RETURN**

After running this command, the static access key will no longer work. Ensure assume-role flow is working first.

```bash
aws iam update-access-key \
  --user-name <iam-username> \
  --access-key-id AKIA............... \
  --status Inactive
```

**Expected output:** No output = success

### Step 4: Verify Deactivation

```bash
# List access keys - should show Inactive
aws iam list-access-keys --user-name <iam-username>
```

**Expected:**
```json
{
    "AccessKeyMetadata": [
        {
            "UserName": "<iam-username>",
            "AccessKeyId": "AKIA...............",
            "Status": "Inactive",
            "CreateDate": "..."
        }
    ]
}
```

## Post-Deactivation Verification

### Step 5: Test Static Key No Longer Works

If you're currently using static credentials in your shell, try an AWS command:

```bash
# This should FAIL with authentication error
aws sts get-caller-identity
```

**Expected error:**
```
An error occurred (InvalidClientTokenId) when calling the GetCallerIdentity operation:
The security token included in the request is invalid.
```

If you see this error, the static key is successfully deactivated.

### Step 6: Test Assume-Role Flow Still Works

```bash
# Assume the developer role
source scrimmage/tools/assume-deploy-role.sh

# Enter MFA token when prompted

# Verify identity
aws sts get-caller-identity
```

**Expected:**
```json
{
    "Arn": "arn:aws:sts::<ACCOUNT_ID>:assumed-role/<project-name>-Developer/...",
    ...
}
```

### Step 7: Test Deployment Operations

```bash
# Test CDK deploy
cd infra
npx cdk deploy <stack-name> --require-approval never
```

**Expected:** Deployment succeeds (or "No changes").

```bash
# Test branch deploy (can Ctrl-C after it starts)
./scrimmage/branch_deploy.sh ../worktrees/test-feature
```

**Expected:** Script proceeds without static key warning.

## Optional: Update ~/.aws/credentials

The static key is already deactivated server-side, but you may want to clean up your local config:

```bash
# Backup first
cp ~/.aws/credentials ~/.aws/credentials.backup

# Edit ~/.aws/credentials
nano ~/.aws/credentials
```

**Option 1:** Comment out the static key:
```ini
[default]
# aws_access_key_id = AKIA...............
# aws_secret_access_key = ********
# These are deactivated - use assume-role instead
```

**Option 2:** Remove the static key entirely (more secure):
```ini
[default]
# No static credentials - use scrimmage/tools/assume-deploy-role.sh
```

## Rollback Procedure

If something goes wrong and you need to re-enable static keys:

```bash
# Reactivate the key
aws iam update-access-key \
  --user-name <iam-username> \
  --access-key-id AKIA............... \
  --status Active

# Verify
aws iam list-access-keys --user-name <iam-username>
```

**When to rollback:**
- Assume-role flow fails unexpectedly
- Critical deployment blocked
- MFA device lost/unavailable
- Need immediate access for emergency

**Note:** After rollback, fix the underlying issue before attempting deactivation again.

## Post-Deployment Updates

After successful deactivation, update deployment scripts to use assume-role by default:

1. **GitHub Actions:** Update `.github/workflows/deploy.yml` to use OIDC or assume-role
2. **Documentation:** Update DEPLOY.md to mention assume-role as the standard method
3. **Onboarding:** Add assume-role setup to developer onboarding docs

## Grace Period

The deactivated key will remain in IAM for a grace period (recommendation: 1 week) before permanent deletion. This allows time to:
- Verify no unexpected issues
- Ensure all team members have transitioned
- Confirm no automated systems depend on the static key

## Acceptance Criteria

- [ ] Static key deactivated in IAM (Status = Inactive)
- [ ] Static key no longer works (authentication fails)
- [ ] Assume-role flow works correctly
- [ ] CDK deploy works with temporary credentials
- [ ] Branch deploy works with temporary credentials
- [ ] Access key ID documented for rollback reference
- [ ] Team notified of the change
