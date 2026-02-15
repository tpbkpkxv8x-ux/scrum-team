#!/usr/bin/env python3
"""Fetch a CloudFormation stack output value using boto3.

Usage::

    python3 cfn_output.py <stack-name> <output-key>

Prints the output value to stdout. Exits non-zero if the stack or key
is not found.

This replaces ``aws cloudformation describe-stacks`` calls in shell
scripts, avoiding the need for the AWS CLI binary (which may be the
wrong architecture on ARM containers — see #187).
"""

from __future__ import annotations

import sys

import boto3


def get_stack_output(stack_name: str, output_key: str) -> str:
    """Return a single CloudFormation stack output value."""
    cfn = boto3.client("cloudformation")
    resp = cfn.describe_stacks(StackName=stack_name)
    stacks = resp.get("Stacks", [])
    if not stacks:
        print(f"ERROR: Stack '{stack_name}' not found", file=sys.stderr)
        sys.exit(1)

    outputs = stacks[0].get("Outputs", [])
    for out in outputs:
        if out["OutputKey"] == output_key:
            return out["OutputValue"]

    print(
        f"ERROR: Output '{output_key}' not found in stack '{stack_name}'",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <stack-name> <output-key>", file=sys.stderr)
        sys.exit(1)

    stack_name = sys.argv[1]
    output_key = sys.argv[2]
    value = get_stack_output(stack_name, output_key)
    print(value)


if __name__ == "__main__":
    main()
