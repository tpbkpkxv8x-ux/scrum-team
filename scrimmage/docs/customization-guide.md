# Customization Guide

How to apply the Scrimmage Team framework to your specific project.

## Overview

The Scrimmage Team framework provides a complete parallel agent workflow out of the box. Some files work as-is, while others need customization for your project's tech stack, cloud provider, and deployment pipeline.

## Files That Need Customization

### CLAUDE.md
- **Tech Stack** — Update to match your project (language, framework, database, cloud provider)
- **Repo Structure** — Update directory layout
- **Worktree Config** — Update symlinks and per-worktree dependency install commands
- **Environment** — Add project-specific environment details (AWS credentials, API keys, etc.)

### scrimmage/branch_deploy.sh
- Fill in the Phase 1/2/3 stubs with your infrastructure-as-code deploy commands
- For AWS CDK: `npx cdk deploy --all --context stageName="$STAGE_NAME"`
- For Terraform: `terraform apply -var="stage=$STAGE_NAME"`
- For CloudFormation: `aws cloudformation deploy --stack-name "MyStack-$STAGE_NAME"`

### scrimmage/branch_teardown.sh
- Fill in stack destruction commands in reverse dependency order
- Match the stacks you deploy in scrimmage/branch_deploy.sh

### .github/workflows/ci.yml
- Customize lint, test, and build commands for your tech stack
- Add or remove jobs based on your project structure

### .github/workflows/deploy.yml
- Set your AWS account ID, region, and OIDC role ARN
- Customize stack names and deploy commands

### scrimmage/tools/assume-deploy-role.sh
- Set the `DEPLOY_ROLE_ARN` environment variable to your IAM role ARN
- Or modify the script to hardcode your role ARN

### scrimmage/tools/check_key_status.sh
- Set default IAM username for your team

### scrimmage/docs/aws-credentials-setup.md
- Replace `<project-name>`, `<ACCOUNT_ID>`, `<iam-username>` placeholders with your values

### scrimmage/notes/*.md
- Add project-specific knowledge below the Key Behaviours sections as your team learns

## Files That Work Out of the Box

No changes needed for these files:

- `scrimmage/scrimmage-team.md` — Team workflow and process definition
- `scrimmage/backlog_db.py` + `scrimmage/test_backlog_db.py` — Product backlog database
- `scrimmage/Backlog-API-guide.md` — Backlog API reference
- `scrimmage/worktree_setup.py` — Git worktree management
- `scrimmage/tools/memory_monitor.sh` — Memory usage monitoring
- `scrimmage/tools/oom_protect.sh` — OOM protection for Claude Code processes
- `scrimmage/tools/generate_sm_state.py` — SM state snapshot generator
- `scrimmage/tools/chat-monitor/` — Team chat monitoring tool
- `scrimmage/tools/scrimmage-board/` — Sprint board display tool
- `scrimmage/tools/cfn_output.py` — CloudFormation output helper (if using AWS)
- `scrimmage/tools/get-aws-creds.sh` — AWS credential wrapper (if using AWS)

## Quick-Start Checklist

1. Fork or copy this template repo
2. Update `CLAUDE.md` with your tech stack, repo structure, and conventions
3. Set up your cloud credentials (see `scrimmage/docs/aws-credentials-setup.md`)
4. Fill in `scrimmage/branch_deploy.sh` Phase 1/2/3 stubs for your IaC tool
5. Fill in `scrimmage/branch_teardown.sh` stack destruction commands
6. Customize `.github/workflows/ci.yml` and `deploy.yml`
7. Create your initial product backlog items
8. Launch the scrimmage master agent

## Non-AWS Projects

If you're using GCP, Azure, or another cloud provider instead of AWS:

- **Replace** `scrimmage/tools/assume-deploy-role.sh` with your cloud's credential helper
- **Replace** `scrimmage/tools/cfn_output.py` with your cloud's output fetcher (e.g., Terraform output)
- **Update** `scrimmage/branch_deploy.sh` and `scrimmage/branch_teardown.sh` with your IaC commands
- **Remove** AWS-specific docs from `scrimmage/docs/` (credential setup, runbooks)
- **Keep** everything else — the workflow, backlog, worktree management, and team tools are cloud-agnostic
