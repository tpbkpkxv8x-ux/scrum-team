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

### branch_deploy.sh
- Fill in the Phase 1/2/3 stubs with your infrastructure-as-code deploy commands
- For AWS CDK: `npx cdk deploy --all --context stageName="$STAGE_NAME"`
- For Terraform: `terraform apply -var="stage=$STAGE_NAME"`
- For CloudFormation: `aws cloudformation deploy --stack-name "MyStack-$STAGE_NAME"`

### branch_teardown.sh
- Fill in stack destruction commands in reverse dependency order
- Match the stacks you deploy in branch_deploy.sh

### .github/workflows/ci.yml
- Customize lint, test, and build commands for your tech stack
- Add or remove jobs based on your project structure

### .github/workflows/deploy.yml
- Set your AWS account ID, region, and OIDC role ARN
- Customize stack names and deploy commands

### tools/assume-deploy-role.sh
- Set the `DEPLOY_ROLE_ARN` environment variable to your IAM role ARN
- Or modify the script to hardcode your role ARN

### tools/check_key_status.sh
- Set default IAM username for your team

### docs/aws-credentials-setup.md
- Replace `<project-name>`, `<ACCOUNT_ID>`, `<iam-username>` placeholders with your values

### notes/*.md
- Add project-specific knowledge below the Key Behaviours sections as your team learns

## Files That Work Out of the Box

No changes needed for these files:

- `scrimmage-team.md` — Team workflow and process definition
- `backlog_db.py` + `test_backlog_db.py` — Product backlog database
- `Backlog-API-guide.md` — Backlog API reference
- `worktree_setup.py` — Git worktree management
- `tools/memory_monitor.sh` — Memory usage monitoring
- `tools/oom_protect.sh` — OOM protection for Claude Code processes
- `tools/generate_sm_state.py` — SM state snapshot generator
- `tools/chat-monitor/` — Team chat monitoring tool
- `tools/scrimmage-board/` — Sprint board display tool
- `tools/cfn_output.py` — CloudFormation output helper (if using AWS)
- `tools/get-aws-creds.sh` — AWS credential wrapper (if using AWS)

## Quick-Start Checklist

1. Fork or copy this template repo
2. Update `CLAUDE.md` with your tech stack, repo structure, and conventions
3. Set up your cloud credentials (see `docs/aws-credentials-setup.md`)
4. Fill in `branch_deploy.sh` Phase 1/2/3 stubs for your IaC tool
5. Fill in `branch_teardown.sh` stack destruction commands
6. Customize `.github/workflows/ci.yml` and `deploy.yml`
7. Create your initial product backlog items
8. Launch the scrimmage master agent

## Non-AWS Projects

If you're using GCP, Azure, or another cloud provider instead of AWS:

- **Replace** `tools/assume-deploy-role.sh` with your cloud's credential helper
- **Replace** `tools/cfn_output.py` with your cloud's output fetcher (e.g., Terraform output)
- **Update** `branch_deploy.sh` and `branch_teardown.sh` with your IaC commands
- **Remove** AWS-specific docs from `docs/` (credential setup, runbooks)
- **Keep** everything else — the workflow, backlog, worktree management, and team tools are cloud-agnostic
