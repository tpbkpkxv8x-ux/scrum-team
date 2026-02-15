# Static IAM Key Permanent Deletion Runbook

**PERMANENT DELETION - NO UNDO**

This runbook covers permanently deleting static IAM access keys after a grace period of using assume-role flow successfully.

## Prerequisites

**ALL MUST BE COMPLETED:**

- IAM stack deployed
- Virtual MFA device configured
- Assume-role flow verified working
- Static key deactivated
- **Grace period elapsed (recommendation: 1 week minimum)**
- **Team has been using assume-role successfully with NO issues**
- **No rollbacks were needed during grace period**

**DO NOT PROCEED** if any issues occurred during the grace period.

## Pre-Deletion Checklist

### Step 1: Verify Grace Period Requirements

**Timeline verification:**
```bash
# Check when key was deactivated
aws iam list-access-keys --user-name <iam-username>
```

Look at the `CreateDate` and compare with your deactivation date. Ensure at least 1 week has passed since deactivation.

**Team verification:**
- [ ] All team members successfully using assume-role
- [ ] No deployment failures related to credentials
- [ ] No rollbacks to static keys were needed
- [ ] All automated systems transitioned (GitHub Actions, etc.)

### Step 2: Current Key Status

```bash
# Check current status
./tools/check_key_status.sh
```

**Expected output:**
```
Access Key ID: AKIA...............
  Status: Inactive
  Created: 2026-02-10T17:54:52Z
```

If status is still `Active`, the deactivation step was not completed. **STOP** and complete the deactivation runbook first.

### Step 3: Verify Assume-Role Is Working

```bash
# Test the assume-role flow
source tools/assume-deploy-role.sh

# Enter MFA token

# Verify identity
aws sts get-caller-identity
```

**Must show:** `assumed-role/<project-name>-Developer` in ARN.

```bash
# Test a deployment
cd infra
npx cdk deploy <stack-name> --require-approval never
```

**Must succeed** without errors.

### Step 4: Backup Access Key Details

Before deletion, record the key information for audit purposes:

```bash
# Save to a secure note/document
echo "Access Key Deleted: AKIA..............."
echo "User: <iam-username>"
echo "Deletion Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Deleted By: $(whoami)"
```

## Permanent Deletion Procedure

### Step 5: Delete Access Key

**PERMANENT DELETION - NO UNDO**

```bash
aws iam delete-access-key \
  --user-name <iam-username> \
  --access-key-id AKIA...............
```

**Expected output:** No output = success

### Step 6: Verify Deletion

```bash
# List keys - should return empty or not include the deleted key
aws iam list-access-keys --user-name <iam-username>
```

**Expected:**
```json
{
    "AccessKeyMetadata": []
}
```

OR if other keys exist, the deleted key should not be in the list.

### Step 7: Verify Assume-Role Still Works

```bash
# Assume role again
source tools/assume-deploy-role.sh

# Enter MFA token

# Test operations
aws sts get-caller-identity
cd infra && npx cdk deploy <stack-name> --require-approval never
```

Both should succeed.

## Optional: Clean Up Old IAM User

If the IAM user `<iam-username>` is no longer needed (only used for assume-role), you can optionally replace it with a more restrictive user.

### Option A: Keep Current User (Recommended)

The current user works fine for assume-role. It has a scoped policy which is already restrictive. **No action needed.**

### Option B: Create Minimal Assume-Only User

If you want a user with ONLY `sts:AssumeRole` permission:

#### 1. Create new minimal policy

Create `infra/iam/assume-only-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/<project-name>-Developer"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:ListMFADevices",
        "iam:GetUser"
      ],
      "Resource": "arn:aws:iam::<ACCOUNT_ID>:user/${aws:username}"
    }
  ]
}
```

#### 2. Add to IAM Stack

Update your IAM stack to create the minimal user:

```typescript
// Minimal IAM user for assume-role only
const assumeOnlyUser = new iam.User(this, 'AssumeOnlyUser', {
  userName: `${prefix}-AssumeOnly`,
});

const assumeOnlyPolicy = new iam.Policy(this, 'AssumeOnlyPolicy', {
  statements: [
    new iam.PolicyStatement({
      actions: ['sts:AssumeRole'],
      resources: [this.developerRole.roleArn],
    }),
    new iam.PolicyStatement({
      actions: ['iam:ListMFADevices', 'iam:GetUser'],
      resources: [`arn:aws:iam::${this.account}:user/\${aws:username}`],
    }),
  ],
});

assumeOnlyUser.attachInlinePolicy(assumeOnlyPolicy);
```

#### 3. Deploy and create access key

```bash
cd infra
npx cdk deploy <iam-stack-name> --require-approval never

# Create access key for new user
aws iam create-access-key --user-name <project-name>-AssumeOnly
```

#### 4. Update ~/.aws/credentials

Replace the old user credentials with the new minimal user.

#### 5. Set up MFA on new user

Follow the same process to configure virtual MFA on the new user.

#### 6. Delete old user

After verifying the new user works:

```bash
# Delete old user
aws iam delete-user --user-name <iam-username>
```

**Note:** This is optional and adds complexity. The current user is already sufficiently restricted.

## Post-Deletion Verification

### Step 8: Final Security Audit

```bash
# No access keys should exist (or only minimal assume-only keys)
aws iam list-access-keys --user-name <iam-username>

# Verify assume-role is the only way to deploy
aws sts get-caller-identity  # Should show assumed-role, not static user
```

### Step 9: Update Documentation

Update these files to reflect the new authentication method:

- [ ] `DEPLOY.md` - Remove static key references, document assume-role
- [ ] `README.md` - Update quickstart with assume-role setup
- [ ] Onboarding docs - Add MFA setup and assume-role instructions

### Step 10: Notify Team

Send a notification to the team:

```
Subject: Static IAM Keys Deleted - Assume-Role Required

Hi team,

The static IAM access key has been permanently deleted
as part of our IAM security improvements.

All AWS operations now require the assume-role flow with MFA:

1. Run: source tools/assume-deploy-role.sh
2. Enter your MFA token
3. Temporary credentials are valid for 1 hour (renewable up to 12 hours)

See docs/assume-role-verification.md for details.
```

## Rollback

**THERE IS NO ROLLBACK.** The key is permanently deleted.

If you need emergency access:
1. Create a new temporary access key for the IAM user
2. Use it for immediate needs
3. Deactivate it after the emergency
4. Return to assume-role flow

## Acceptance Criteria

- [ ] Grace period (1 week) has elapsed
- [ ] No issues during grace period
- [ ] Access key permanently deleted from IAM
- [ ] Verification that assume-role still works
- [ ] Documentation updated
- [ ] Team notified
