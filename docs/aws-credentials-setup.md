# AWS Credentials Setup for <project-name> Development

This guide walks you through setting up **secure temporary AWS credentials with MFA** for local <project-name> development. This replaces the old approach of using long-lived static IAM keys.

## Why Temporary Credentials?

**Security benefits:**
- **Time-limited access**: Credentials expire after 12 hours by default (configurable down to 1 hour)
- **MFA protection**: Leaked access keys alone are useless without your MFA device
- **Reduced blast radius**: Even if credentials leak, they auto-expire quickly
- **Audit trail**: All AssumeRole operations are logged in AWS CloudTrail

**Old approach (insecure):**
```
~/.aws/credentials containing static keys
  Never expire
  No MFA requirement
  High risk if leaked
```

**New approach (secure):**
```
1. Minimal IAM user with only sts:AssumeRole permission
2. Virtual MFA device (authenticator app)
3. Helper script to get temporary credentials
4. Credentials expire automatically
```

---

## Prerequisites

- AWS CLI installed (`aws --version` should work)
- Python 3 installed (already required for backend development)
- An authenticator app on your phone (Google Authenticator, Authy, 1Password, etc.)

---

## Setup Steps

### 1. Configure Your IAM User Credentials

You need a minimal IAM user with permission to assume the `<project-name>-Developer` role.

**If you already have IAM credentials configured:**
```bash
aws sts get-caller-identity
```

If this works, you're good — your IAM user should already have the necessary permissions.

**If you don't have credentials configured:**

Ask the team lead for:
- AWS Access Key ID
- AWS Secret Access Key

Then run:
```bash
aws configure
# AWS Access Key ID: AKIA................
# AWS Secret Access Key: ................
# Default region name: eu-west-1
# Default output format: json
```

### 2. Set Up Virtual MFA Device

**Why?** The `<project-name>-Developer` role requires MFA to assume it. Without MFA, you cannot get temporary credentials.

#### Steps:

1. **Open the AWS Console:**
   - Go to: https://console.aws.amazon.com/iam
   - Sign in with your IAM user credentials

2. **Navigate to MFA settings:**
   - Click your username in the top-right corner
   - Select: **Security credentials**
   - Scroll to: **Multi-factor authentication (MFA)**
   - Click: **Assign MFA device**

3. **Choose device type:**
   - Select: **Authenticator app**
   - Click: **Next**

4. **Scan QR code:**
   - Open your authenticator app (Google Authenticator, Authy, 1Password, etc.)
   - Scan the QR code shown in the AWS Console
   - Your app will start generating 6-digit codes that refresh every 30 seconds

5. **Verify MFA device:**
   - Enter two consecutive MFA codes from your app
   - Click: **Add MFA**

6. **Verify it worked:**
   ```bash
   aws iam list-mfa-devices
   ```

   You should see output like:
   ```json
   {
     "MFADevices": [
       {
         "UserName": "<iam-username>",
         "SerialNumber": "arn:aws:iam::<ACCOUNT_ID>:mfa/<iam-username>",
         "EnableDate": "2026-02-10T12:00:00Z"
       }
     ]
   }
   ```

MFA setup complete!

---

## Using Temporary Credentials

### Quick Start

Every time you want to deploy or use AWS, run:

```bash
source tools/assume-deploy-role.sh
```

**What happens:**
1. Script finds your MFA device automatically
2. Prompts you for a 6-digit MFA token
3. Calls `aws sts assume-role` to get temporary credentials
4. Exports credentials as environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`)
5. Prints expiration time

**Example session:**
```bash
$ source tools/assume-deploy-role.sh
Fetching MFA device...
MFA device found: arn:aws:iam::<ACCOUNT_ID>:mfa/<iam-username>

Enter MFA token: 123456
Assuming role arn:aws:iam::<ACCOUNT_ID>:role/<project-name>-Developer...

Successfully assumed role: <project-name>-Developer
Session expires: 2026-02-10T14:30:00+00:00

Temporary credentials have been exported to your shell environment.
You can now run AWS commands (aws, cdk, etc.) and they will use these credentials.

Examples:
  aws sts get-caller-identity                    # Verify you're using the role
  cd infra && npx cdk deploy --all               # Deploy with temp credentials
  ./branch_deploy.sh ../worktrees/my-feature     # Branch deploy with temp creds

Remember: These credentials expire in 12 hours!
```

### Verify It Worked

Check that you're using the assumed role (not your IAM user):

```bash
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AROA...:dev-yourname-1234567890",
    "Account": "<ACCOUNT_ID>",
    "Arn": "arn:aws:sts::<ACCOUNT_ID>:assumed-role/<project-name>-Developer/dev-yourname-1234567890"
}
```

Notice the ARN contains `assumed-role/<project-name>-Developer` — this confirms you're using temporary credentials!

### Common Workflows

#### Deploy CDK stacks:
```bash
source tools/assume-deploy-role.sh
cd infra
npx cdk deploy --all
```

#### Branch deploy:
```bash
source tools/assume-deploy-role.sh
./branch_deploy.sh ../worktrees/my-feature
```

#### Shorter session (1 hour):
```bash
source tools/assume-deploy-role.sh 3600
```

The script accepts an optional duration argument (in seconds):
- Default: `43200` (12 hours)
- Maximum: `43200` (12 hours)

**Trade-off:** Shorter sessions (e.g., 1 hour) reduce the window if credentials leak, but require more frequent re-authentication. The default 12 hours balances convenience with security for typical development workflows.

---

## Integration with `branch_deploy.sh`

The `branch_deploy.sh` script now checks your AWS credentials at startup:

**If using temporary credentials (recommended):**
```
[INFO] Checking AWS credentials...
[OK] Using temporary credentials (AWS_SESSION_TOKEN present)
[INFO]   Session: dev-yourname-1234567890
```

**If using static keys (deprecated):**
```
[FAIL] ERROR: Static IAM credentials are not allowed

[FAIL] This deployment requires temporary credentials with MFA.

Static access keys are no longer permitted because:
  They never expire (leaked keys = indefinite access)
  No MFA protection (leaked keys alone grant full access)
  Higher blast radius if credentials are compromised

To deploy, obtain temporary credentials with:

  source tools/assume-deploy-role.sh

Then re-run this script.

[WARN] Emergency override: Set <PROJECT_NAME>_ALLOW_STATIC=1 to bypass this check
[WARN] (use only in exceptional circumstances with approval)
```

The script will **exit immediately** unless you run `source tools/assume-deploy-role.sh` first.

> **Note:** Static credentials are blocked by default. The IAM user has assume-only permissions and cannot deploy infrastructure directly.

---

## Troubleshooting

### "No MFA device configured"

**Problem:**
```
ERROR: No MFA device configured.
```

**Solution:**
You haven't set up a virtual MFA device. Follow the [Set Up Virtual MFA Device](#2-set-up-virtual-mfa-device) section above.

---

### "AccessDenied: User is not authorized to perform: sts:AssumeRole"

**Problem:**
```
An error occurred (AccessDenied) when calling the AssumeRole operation:
User: arn:aws:iam::<ACCOUNT_ID>:user/<iam-username> is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::<ACCOUNT_ID>:role/<project-name>-Developer
```

**Solution:**
Your IAM user doesn't have permission to assume the `<project-name>-Developer` role. Ask the team lead to:
1. Verify the IAM role exists (`<project-name>-Developer`)
2. Grant your IAM user the `sts:AssumeRole` permission for that role

---

### "Invalid MFA token"

**Problem:**
```
An error occurred (InvalidMFACode) when calling the AssumeRole operation:
MultiFactorAuthentication failed with invalid MFA one time pass code.
```

**Causes:**
- **Typo in MFA token**: MFA codes are time-sensitive and easy to mistype
- **Token expired**: MFA tokens refresh every 30 seconds — if you wait too long, the token becomes invalid
- **Token already used**: You can't reuse the same MFA token twice in a row

**Solution:**
- Wait for the next token to appear in your authenticator app
- Enter the new 6-digit code
- Run the script again

---

### "Credentials expired"

**Problem:**
After 1 hour (or your chosen duration), AWS commands fail:
```
An error occurred (ExpiredToken) when calling the ... operation:
The security token included in the request is expired
```

**Solution:**
Your temporary credentials have expired. Re-run the helper script:
```bash
source tools/assume-deploy-role.sh
```

---

### "Session not found in environment"

**Problem:**
You ran the script but AWS commands still fail or use the wrong credentials.

**Causes:**
- You ran the script without `source` (e.g., `./tools/assume-deploy-role.sh`)
- Environment variables didn't propagate to the current shell

**Solution:**
Always use `source` or `.` to run the script:
```bash
source tools/assume-deploy-role.sh   # Correct
./tools/assume-deploy-role.sh        # Wrong (runs in subshell)
```

The `source` keyword ensures environment variables are set in your **current** shell, not a subshell.

---

### Script fails with "jq: command not found"

**This should NOT happen** — the script uses `python3` for JSON parsing, not `jq`.

If you see this error, you may be running an older version of the script. Pull the latest version from master:
```bash
git pull origin master
```

---

## Advanced: Manual AssumeRole (Without Helper Script)

If you prefer to understand the underlying AWS commands, here's what the helper script does under the hood:

```bash
# 1. Get your MFA device ARN
MFA_SERIAL=$(aws iam list-mfa-devices --query 'MFADevices[0].SerialNumber' --output text)

# 2. Assume role with MFA token
CREDS=$(aws sts assume-role \
  --role-arn arn:aws:iam::<ACCOUNT_ID>:role/<project-name>-Developer \
  --role-session-name dev-$(whoami)-$(date +%s) \
  --serial-number "$MFA_SERIAL" \
  --token-code 123456 \
  --duration-seconds 3600 \
  --output json)

# 3. Extract credentials
export AWS_ACCESS_KEY_ID=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['AccessKeyId'])")
export AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['SecretAccessKey'])")
export AWS_SESSION_TOKEN=$(echo "$CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['Credentials']['SessionToken'])")

# 4. Verify
aws sts get-caller-identity
```

---

## FAQ

### Q: Do I need to run this every time I open a new terminal?

**Yes.** Environment variables are local to your shell session. If you open a new terminal window or tab, you'll need to run `source tools/assume-deploy-role.sh` again.

**Tip:** Some developers add a shell alias for convenience:
```bash
# Add to ~/.bashrc or ~/.zshrc
alias aws-assume='source <repo-path>/tools/assume-deploy-role.sh'
```

Then you can just run:
```bash
aws-assume
```

---

### Q: Can I use the same MFA device for multiple AWS accounts?

**Yes.** Your authenticator app can store multiple AWS MFA devices. Each account will have its own QR code and generate separate tokens.

---

### Q: What if I lose my MFA device?

**Problem:** You lost your phone or authenticator app, and now you can't get temporary credentials.

**Solution:**
1. **If you still have access to the AWS Console with your IAM user:**
   - Sign in to: https://console.aws.amazon.com/iam
   - Go to: Security credentials → MFA
   - Deactivate the old MFA device
   - Set up a new MFA device

2. **If you can't access the console:**
   - Contact the team lead or AWS account administrator
   - They can deactivate your MFA device and help you set up a new one

**Prevention:** Many authenticator apps support backup/sync (e.g., Authy, 1Password). Consider using one with cloud backup.

---

### Q: Can I skip MFA and just use static credentials?

**No.** The project **requires MFA-protected temporary credentials for all AWS operations**. Deploy scripts (`branch_deploy.sh`, `branch_teardown.sh`) will reject static credentials and exit with an error unless you explicitly override with `<PROJECT_NAME>_ALLOW_STATIC=1` (not recommended).

**Why MFA + temporary credentials are mandatory:**
- If your laptop is stolen, the thief can't access AWS without your MFA device
- If you accidentally commit credentials to Git, they'll expire automatically
- CloudTrail logs all AssumeRole operations, providing an audit trail
- Static IAM keys have been restricted to assume-only permissions (cannot access AWS services directly)

This is a security requirement, not a recommendation.

---

### Q: How do CI/CD pipelines work without MFA?

**GitHub Actions uses AWS OIDC (OpenID Connect):**
- No static credentials stored in GitHub secrets
- Temporary credentials issued per workflow run
- Automated credential rotation
- Role: `GitHubActionsDeployRole`

**OIDC is even more secure than MFA** because there are no long-lived credentials at all — GitHub's identity provider issues temporary tokens directly.

This setup only applies to **local development**. CI/CD already uses best practices.

---

## Summary

**Old workflow:**
```bash
# Static credentials in ~/.aws/credentials (insecure)
./branch_deploy.sh ../worktrees/my-feature
```

**New workflow:**
```bash
# Temporary credentials with MFA (secure)
source tools/assume-deploy-role.sh
./branch_deploy.sh ../worktrees/my-feature
```

**Benefits:**
- Credentials expire automatically (1-12 hours)
- MFA required (leaked keys alone are useless)
- Audit trail in CloudTrail
- Follows AWS security best practices

**Trade-offs:**
- Need to re-run helper script when credentials expire (default: every 12 hours)
- Need to enter MFA token each time

Most developers find this trade-off acceptable for the improved security posture.

---

## Need Help?

- **AWS Documentation:** [AssumeRole with MFA](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_mfa_configure-api-require.html)
- **Team Lead:** Ask your Scrimmage Master or Cloud Engineer for IAM/MFA issues

---

**Happy (secure) deploying!**
