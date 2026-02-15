"""Tests for tmux_launch.py — the tmux window launcher for Claude Code agents."""

from __future__ import annotations

import os
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tmux_launch import (
    AGENT_ENV,
    CLAUDE_BIN,
    AgentConfig,
    _sanitize_window_name,
    build_claude_command,
    build_tmux_command,
    launch_agent,
    main,
)


@pytest.fixture()
def sample_config() -> AgentConfig:
    return AgentConfig(
        agent_name="Pierre_Peer_Reviewer",
        team_name="mypy-ignore-fixes",
        agent_color="yellow",
        parent_session_id="1ad512d5-b247-40fc-bbe9-5ed21cf848d3",
        agent_type="general-purpose",
        model="opus",
        work_dir="/tmp/test-project",
    )


# ── AgentConfig ──────────────────────────────────────────────────────────


class TestAgentConfig:
    def test_frozen(self, sample_config: AgentConfig) -> None:
        with pytest.raises(AttributeError):
            sample_config.agent_name = "nope"  # type: ignore[misc]

    def test_fields(self, sample_config: AgentConfig) -> None:
        assert sample_config.agent_name == "Pierre_Peer_Reviewer"
        assert sample_config.team_name == "mypy-ignore-fixes"
        assert sample_config.agent_color == "yellow"
        assert sample_config.parent_session_id == "1ad512d5-b247-40fc-bbe9-5ed21cf848d3"
        assert sample_config.agent_type == "general-purpose"
        assert sample_config.model == "opus"
        assert sample_config.work_dir == "/tmp/test-project"

    def test_work_dir_defaults_to_cwd(self) -> None:
        cfg = AgentConfig(
            agent_name="Test",
            team_name="team",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
        )
        assert cfg.work_dir == os.getcwd()


# ── build_claude_command ─────────────────────────────────────────────────


class TestBuildClaudeCommand:
    def test_contains_claude_binary(self, sample_config: AgentConfig) -> None:
        cmd = build_claude_command(sample_config)
        assert cmd[0] == CLAUDE_BIN

    def test_agent_id_format(self, sample_config: AgentConfig) -> None:
        cmd = build_claude_command(sample_config)
        idx = cmd.index("--agent-id")
        assert cmd[idx + 1] == "Pierre_Peer_Reviewer@mypy-ignore-fixes"

    def test_all_flags_present(self, sample_config: AgentConfig) -> None:
        cmd = build_claude_command(sample_config)
        expected_flags = [
            "--agent-id",
            "--agent-name",
            "--team-name",
            "--agent-color",
            "--parent-session-id",
            "--agent-type",
            "--dangerously-skip-permissions",
            "--model",
        ]
        for flag in expected_flags:
            assert flag in cmd, f"Missing flag: {flag}"

    def test_flag_values(self, sample_config: AgentConfig) -> None:
        cmd = build_claude_command(sample_config)
        pairs: dict[str, str] = {cmd[i]: cmd[i + 1] for i in range(len(cmd) - 1)}
        assert pairs["--agent-name"] == "Pierre_Peer_Reviewer"
        assert pairs["--team-name"] == "mypy-ignore-fixes"
        assert pairs["--agent-color"] == "yellow"
        assert pairs["--parent-session-id"] == "1ad512d5-b247-40fc-bbe9-5ed21cf848d3"
        assert pairs["--agent-type"] == "general-purpose"
        assert pairs["--model"] == "opus"

    def test_dangerously_skip_permissions_is_standalone(self, sample_config: AgentConfig) -> None:
        cmd = build_claude_command(sample_config)
        assert "--dangerously-skip-permissions" in cmd


# ── build_tmux_command ───────────────────────────────────────────────────


class TestBuildTmuxCommand:
    def test_starts_with_tmux_new_window(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        assert cmd[0] == "tmux"
        assert cmd[1] == "new-window"

    def test_detached_flag(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        assert "-d" in cmd

    def test_window_name(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "Pierre_Peer_Reviewer"

    def test_shell_cmd_contains_cd_to_work_dir(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        shell_cmd = cmd[-1]
        assert "cd /tmp/test-project" in shell_cmd

    def test_custom_work_dir(self) -> None:
        cfg = AgentConfig(
            agent_name="Test",
            team_name="team",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
            work_dir="/custom/path",
        )
        cmd = build_tmux_command(cfg)
        shell_cmd = cmd[-1]
        assert "cd /custom/path" in shell_cmd

    def test_shell_cmd_exports_env_vars(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        shell_cmd = cmd[-1]
        for key, value in AGENT_ENV.items():
            assert f"export {key}={value}" in shell_cmd

    def test_shell_cmd_contains_claude_binary(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        shell_cmd = cmd[-1]
        assert CLAUDE_BIN in shell_cmd

    def test_shell_cmd_contains_agent_id(self, sample_config: AgentConfig) -> None:
        cmd = build_tmux_command(sample_config)
        shell_cmd = cmd[-1]
        assert "Pierre_Peer_Reviewer@mypy-ignore-fixes" in shell_cmd

    def test_shell_cmd_parts_chained(self, sample_config: AgentConfig) -> None:
        """Verify parts are joined with '&&' so failure stops the chain."""
        cmd = build_tmux_command(sample_config)
        shell_cmd = cmd[-1]
        assert " && " in shell_cmd

    def test_different_agent_name_changes_window(self) -> None:
        cfg = AgentConfig(
            agent_name="Cindy_Cloud_Engineer",
            team_name="sprint-7",
            agent_color="green",
            parent_session_id="abc-123",
            agent_type="general-purpose",
            model="sonnet",
            work_dir="/tmp",
        )
        cmd = build_tmux_command(cfg)
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "Cindy_Cloud_Engineer"


# ── launch_agent ─────────────────────────────────────────────────────────


class TestLaunchAgent:
    @patch("tmux_launch.subprocess.run")
    def test_calls_subprocess_run(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_agent(sample_config)
        mock_run.assert_called_once()

    @patch("tmux_launch.subprocess.run")
    def test_passes_check_true(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_agent(sample_config)
        _args, kwargs = mock_run.call_args
        assert kwargs["check"] is True

    @patch("tmux_launch.subprocess.run")
    def test_captures_output(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_agent(sample_config)
        _args, kwargs = mock_run.call_args
        assert kwargs["capture_output"] is True

    @patch("tmux_launch.subprocess.run")
    def test_returns_completed_process(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        expected: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(args=[], returncode=0)
        mock_run.return_value = expected
        result = launch_agent(sample_config)
        assert result is expected

    @patch("tmux_launch.subprocess.run")
    def test_command_starts_with_tmux(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_agent(sample_config)
        cmd: list[Any] = mock_run.call_args[0][0]
        assert cmd[0] == "tmux"

    @patch("tmux_launch.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux"))
    def test_raises_on_tmux_failure(
        self,
        mock_run: MagicMock,
        sample_config: AgentConfig,
    ) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            launch_agent(sample_config)


# ── CLI (main / _parse_args) ────────────────────────────────────────────


class TestCLI:
    @patch("tmux_launch.launch_agent")
    def test_main_parses_and_launches(self, mock_launch: MagicMock) -> None:
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main([
            "--agent-name",
            "Pierre_Peer_Reviewer",
            "--team-name",
            "mypy-ignore-fixes",
            "--agent-color",
            "yellow",
            "--parent-session-id",
            "abc-123",
            "--agent-type",
            "general-purpose",
            "--model",
            "opus",
        ])
        mock_launch.assert_called_once()
        cfg: AgentConfig = mock_launch.call_args[0][0]
        assert isinstance(cfg, AgentConfig)
        assert cfg.agent_name == "Pierre_Peer_Reviewer"
        assert cfg.model == "opus"

    def test_missing_required_arg_exits(self) -> None:
        with pytest.raises(SystemExit):
            main(["--agent-name", "Test"])

    @patch("tmux_launch.launch_agent")
    def test_all_args_forwarded(self, mock_launch: MagicMock) -> None:
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main([
            "--agent-name",
            "Cindy",
            "--team-name",
            "sprint-7",
            "--agent-color",
            "green",
            "--parent-session-id",
            "sess-456",
            "--agent-type",
            "general-purpose",
            "--model",
            "sonnet",
            "--work-dir",
            "/my/project",
        ])
        cfg: AgentConfig = mock_launch.call_args[0][0]
        assert cfg.agent_name == "Cindy"
        assert cfg.team_name == "sprint-7"
        assert cfg.agent_color == "green"
        assert cfg.parent_session_id == "sess-456"
        assert cfg.agent_type == "general-purpose"
        assert cfg.model == "sonnet"
        assert cfg.work_dir == "/my/project"

    @patch("tmux_launch.launch_agent")
    def test_work_dir_defaults_to_cwd(self, mock_launch: MagicMock) -> None:
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main([
            "--agent-name",
            "Test",
            "--team-name",
            "team",
            "--agent-color",
            "red",
            "--parent-session-id",
            "id",
            "--agent-type",
            "general-purpose",
            "--model",
            "opus",
        ])
        cfg: AgentConfig = mock_launch.call_args[0][0]
        assert cfg.work_dir == os.getcwd()


# ── Shell-safety edge cases ─────────────────────────────────────────────


class TestShellSafety:
    def test_special_chars_in_agent_name(self) -> None:
        """Names with spaces or special chars are properly quoted in the shell command."""
        cfg = AgentConfig(
            agent_name="Agent With Spaces",
            team_name="team",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
            work_dir="/tmp",
        )
        cmd = build_tmux_command(cfg)
        shell_cmd = cmd[-1]
        assert "'Agent With Spaces'" in shell_cmd or '"Agent With Spaces"' in shell_cmd

    def test_semicolon_in_team_name(self) -> None:
        """A semicolon in a parameter must not break out of the command."""
        cfg = AgentConfig(
            agent_name="Evil",
            team_name="team;rm -rf /",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
            work_dir="/tmp",
        )
        cmd = build_tmux_command(cfg)
        shell_cmd = cmd[-1]
        assert ";rm -rf /" not in shell_cmd.split("'")[0]

    def test_work_dir_with_spaces(self) -> None:
        """Work dir with spaces must be properly quoted."""
        cfg = AgentConfig(
            agent_name="Test",
            team_name="team",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
            work_dir="/path/with spaces/project",
        )
        cmd = build_tmux_command(cfg)
        shell_cmd = cmd[-1]
        assert "'/path/with spaces/project'" in shell_cmd or '"/path/with spaces/project"' in shell_cmd


# ── _sanitize_window_name ─────────────────────────────────────────────


class TestSanitizeWindowName:
    def test_clean_name_unchanged(self) -> None:
        assert _sanitize_window_name("Pierre_Peer_Reviewer") == "Pierre_Peer_Reviewer"

    def test_strips_dots(self) -> None:
        assert _sanitize_window_name("agent.name") == "agentname"

    def test_strips_colons(self) -> None:
        assert _sanitize_window_name("session:window") == "sessionwindow"

    def test_strips_exclamation(self) -> None:
        assert _sanitize_window_name("hey!") == "hey"

    def test_strips_hash(self) -> None:
        assert _sanitize_window_name("#agent") == "agent"

    def test_preserves_hyphens(self) -> None:
        assert _sanitize_window_name("my-agent") == "my-agent"

    def test_strips_spaces(self) -> None:
        assert _sanitize_window_name("Agent Name") == "AgentName"

    def test_empty_after_strip_returns_default(self) -> None:
        assert _sanitize_window_name(".:!") == "agent"

    def test_empty_input_returns_default(self) -> None:
        assert _sanitize_window_name("") == "agent"

    def test_typical_agent_name(self) -> None:
        assert _sanitize_window_name("Barry_Backend_Engineer") == "Barry_Backend_Engineer"

    def test_window_name_sanitized_in_tmux_command(self) -> None:
        """Verify build_tmux_command applies sanitization to the window name."""
        cfg = AgentConfig(
            agent_name="Agent.With:Special!Chars",
            team_name="team",
            agent_color="red",
            parent_session_id="id",
            agent_type="general-purpose",
            model="opus",
            work_dir="/tmp",
        )
        cmd = build_tmux_command(cfg)
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "AgentWithSpecialChars"
