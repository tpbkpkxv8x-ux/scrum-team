"""Tests for cfn_output.py — CloudFormation stack output helper."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from cfn_output import get_stack_output


class TestGetStackOutput:
    def test_returns_matching_output_value(self) -> None:
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "Outputs": [
                        {"OutputKey": "ApiUrl", "OutputValue": "https://api.example.com/dev/"},
                        {"OutputKey": "UserPoolId", "OutputValue": "eu-west-1_abc123"},
                    ]
                }
            ]
        }

        with patch("cfn_output.boto3") as mock_boto:
            mock_boto.client.return_value = mock_cfn
            result = get_stack_output("MyStack", "ApiUrl")

        assert result == "https://api.example.com/dev/"

    def test_returns_second_output(self) -> None:
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "Outputs": [
                        {"OutputKey": "ApiUrl", "OutputValue": "https://api.example.com/"},
                        {"OutputKey": "UserPoolId", "OutputValue": "eu-west-1_xyz"},
                    ]
                }
            ]
        }

        with patch("cfn_output.boto3") as mock_boto:
            mock_boto.client.return_value = mock_cfn
            result = get_stack_output("MyStack", "UserPoolId")

        assert result == "eu-west-1_xyz"

    def test_exits_when_stack_not_found(self) -> None:
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {"Stacks": []}

        with patch("cfn_output.boto3") as mock_boto:
            mock_boto.client.return_value = mock_cfn
            with pytest.raises(SystemExit, match="1"):
                get_stack_output("MissingStack", "ApiUrl")

    def test_exits_when_output_key_not_found(self) -> None:
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [
                {
                    "Outputs": [
                        {"OutputKey": "ApiUrl", "OutputValue": "https://api.example.com/"},
                    ]
                }
            ]
        }

        with patch("cfn_output.boto3") as mock_boto:
            mock_boto.client.return_value = mock_cfn
            with pytest.raises(SystemExit, match="1"):
                get_stack_output("MyStack", "NonexistentKey")

    def test_exits_when_no_outputs(self) -> None:
        mock_cfn = MagicMock()
        mock_cfn.describe_stacks.return_value = {
            "Stacks": [{"Outputs": []}]
        }

        with patch("cfn_output.boto3") as mock_boto:
            mock_boto.client.return_value = mock_cfn
            with pytest.raises(SystemExit, match="1"):
                get_stack_output("MyStack", "ApiUrl")


class TestCLI:
    def test_wrong_arg_count_exits(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "cfn_output"],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).parent),
        )
        assert result.returncode != 0
        assert "Usage" in result.stderr
