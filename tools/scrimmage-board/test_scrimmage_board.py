"""Tests for scrimmage_board.py — terminal scrimmage board information radiator."""

from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from scrimmage_board import (
    ANSI_DIM,
    BoardData,
    BoardItem,
    ColourAssigner,
    _format_item,
    _pad_ansi,
    _shorten_agent_name,
    _truncate,
    _visible_length,
    _word_wrap,
    build_tmux_command,
    get_memory_stats,
    launch_board,
    main,
    monitor_board,
    render_board_data,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def sample_items() -> list[BoardItem]:
    return [
        BoardItem(item_id=101, title="Add login", status="backlog", assigned_to=""),
        BoardItem(item_id=102, title="Fix bug", status="ready", assigned_to="Barry_Backend_Engineer"),
        BoardItem(item_id=103, title="Hashtag search", status="in_progress", assigned_to="Barry_Backend_Engineer"),
        BoardItem(item_id=104, title="CDK stack", status="review", assigned_to="Cindy_Cloud_Engineer"),
        BoardItem(item_id=105, title="Dark mode", status="done", assigned_to="Fred_Frontend_Engineer"),
        BoardItem(item_id=106, title="DMs backend", status="merged", assigned_to="Bonnie_Backend_Engineer"),
    ]


@pytest.fixture()
def sample_board(sample_items: list[BoardItem]) -> BoardData:
    return BoardData(
        todo=[sample_items[0], sample_items[1]],
        in_progress=[sample_items[2]],
        review=[sample_items[3]],
        merged=[sample_items[5]],
        done=[sample_items[4]],
    )


# ── _truncate ─────────────────────────────────────────────────────────────


class TestTruncate:
    def test_short_string_unchanged(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_exact_width_unchanged(self) -> None:
        assert _truncate("12345", 5) == "12345"

    def test_long_string_truncated(self) -> None:
        result = _truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("…")

    def test_very_short_width(self) -> None:
        result = _truncate("hello", 3)
        assert len(result) == 3


# ── _word_wrap ───────────────────────────────────────────────────────────


class TestWordWrap:
    def test_short_text_single_line(self) -> None:
        assert _word_wrap("hello", 20) == ["hello"]

    def test_wraps_at_word_boundary(self) -> None:
        result = _word_wrap("hello world", 8)
        assert result == ["hello", "world"]

    def test_respects_max_lines(self) -> None:
        result = _word_wrap("one two three four five six", 8, max_lines=2)
        assert len(result) == 2
        assert result[-1].endswith("…")

    def test_long_single_word_truncated(self) -> None:
        result = _word_wrap("supercalifragilistic", 10)
        assert len(result) == 1
        assert len(result[0]) == 10
        assert result[0].endswith("…")

    def test_empty_text(self) -> None:
        assert _word_wrap("", 20) == [""]

    def test_exact_fit_no_wrap(self) -> None:
        assert _word_wrap("fits here", 9) == ["fits here"]


# ── _visible_length ──────────────────────────────────────────────────────


class TestVisibleLength:
    def test_plain_text(self) -> None:
        assert _visible_length("hello") == 5

    def test_with_ansi(self) -> None:
        assert _visible_length("\033[1mhello\033[0m") == 5

    def test_multiple_ansi(self) -> None:
        s = "\033[92m\033[1mhi\033[0m there"
        assert _visible_length(s) == 8

    def test_empty(self) -> None:
        assert _visible_length("") == 0


# ── _pad_ansi ────────────────────────────────────────────────────────────


class TestPadAnsi:
    def test_pads_to_width(self) -> None:
        result = _pad_ansi("hi", 5)
        assert _visible_length(result) == 5

    def test_no_padding_if_already_wide(self) -> None:
        result = _pad_ansi("hello", 3)
        assert result == "hello"

    def test_pads_ansi_string(self) -> None:
        s = "\033[1mhi\033[0m"
        result = _pad_ansi(s, 10)
        assert _visible_length(result) == 10


# ── _shorten_agent_name ──────────────────────────────────────────────────


class TestShortenAgentName:
    def test_three_part_name(self) -> None:
        assert _shorten_agent_name("Barry_Backend_Engineer") == "Barry_BE"

    def test_two_part_name(self) -> None:
        assert _shorten_agent_name("team_lead") == "team_lead"

    def test_hyphenated_name(self) -> None:
        assert _shorten_agent_name("team-lead") == "team-lead"

    def test_empty_string(self) -> None:
        assert _shorten_agent_name("") == ""

    def test_four_part_name(self) -> None:
        assert _shorten_agent_name("Sally_Scrimmage_Master_Lead") == "Sally_SML"


# ── ColourAssigner ───────────────────────────────────────────────────────


class TestColourAssigner:
    def test_same_agent_same_colour(self) -> None:
        ca = ColourAssigner()
        c1 = ca.get("Barry")
        c2 = ca.get("Barry")
        assert c1 == c2

    def test_different_agents_different_colours(self) -> None:
        ca = ColourAssigner()
        c1 = ca.get("Barry")
        c2 = ca.get("Cindy")
        assert c1 != c2

    def test_empty_agent_gets_dim(self) -> None:
        ca = ColourAssigner()
        assert ca.get("") == ANSI_DIM

    def test_wraps_around_palette(self) -> None:
        ca = ColourAssigner()
        # Assign more agents than palette size
        for i in range(15):
            ca.get(f"agent-{i}")
        # Should not crash
        assert ca.get("agent-14") != ""


# ── _format_item ─────────────────────────────────────────────────────────


class TestFormatItem:
    def test_contains_item_id(self) -> None:
        item = BoardItem(item_id=42, title="Test", status="backlog", assigned_to="Barry")
        lines = _format_item(item, 40, ColourAssigner())
        combined = " ".join(lines)
        assert "#42" in combined

    def test_contains_title(self) -> None:
        item = BoardItem(item_id=1, title="My Title", status="backlog", assigned_to="")
        lines = _format_item(item, 40, ColourAssigner())
        combined = " ".join(lines)
        assert "My Title" in combined

    def test_review_badge_shown(self) -> None:
        item = BoardItem(item_id=1, title="Review me", status="review", assigned_to="Pierre")
        lines = _format_item(item, 40, ColourAssigner())
        combined = " ".join(lines)
        assert "⦿" in combined

    def test_no_review_badge_for_non_review(self) -> None:
        item = BoardItem(item_id=1, title="WIP", status="in_progress", assigned_to="Barry")
        lines = _format_item(item, 40, ColourAssigner())
        combined = " ".join(lines)
        assert "⦿" not in combined

    def test_unassigned_shown(self) -> None:
        item = BoardItem(item_id=1, title="Test", status="backlog", assigned_to="")
        lines = _format_item(item, 40, ColourAssigner())
        combined = " ".join(lines)
        assert "unassigned" in combined

    def test_short_title_returns_two_lines(self) -> None:
        item = BoardItem(item_id=1, title="Test", status="backlog", assigned_to="Agent")
        lines = _format_item(item, 40, ColourAssigner())
        assert len(lines) == 2

    def test_long_title_wraps(self) -> None:
        item = BoardItem(
            item_id=1,
            title="Implement real-time notifications for new followers",
            status="backlog",
            assigned_to="Agent",
        )
        lines = _format_item(item, 25, ColourAssigner())
        # Title should wrap onto multiple lines + 1 assignee line
        assert len(lines) >= 3

    def test_wrapped_title_preserves_all_words(self) -> None:
        item = BoardItem(
            item_id=1,
            title="Add dark mode toggle",
            status="backlog",
            assigned_to="Agent",
        )
        lines = _format_item(item, 20, ColourAssigner())
        combined = " ".join(lines)
        assert "dark" in combined
        assert "mode" in combined
        assert "toggle" in combined


# ── render_board_data ────────────────────────────────────────────────────


class TestRenderBoardData:
    def test_contains_sprint_name(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=120, term_height=40)
        text = output.getvalue()
        assert "sprint-7" in text

    def test_contains_column_headers(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        assert "To Do" in text
        assert "In Progress" in text
        assert "Review" in text
        assert "Merged" in text
        assert "Done" in text

    def test_contains_item_ids(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=160, term_height=40)
        text = output.getvalue()
        assert "#101" in text
        assert "#103" in text
        assert "#105" in text
        assert "#106" in text

    def test_contains_column_counts(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        assert "To Do (2)" in text
        assert "In Progress (1)" in text
        assert "Review (1)" in text
        assert "Merged (1)" in text
        assert "Done (1)" in text

    def test_contains_column_separators(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=160, term_height=40)
        text = output.getvalue()
        assert "│" in text

    def test_review_badge_in_review_column(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        assert "⦿" in text

    def test_review_items_in_review_column(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        # Item 104 (CDK stack) should be in Review column
        assert "#104" in text
        assert "Review (1)" in text

    def test_memory_stats_in_output(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        assert "RAM:" in text

    def test_empty_board(self) -> None:
        output = StringIO()
        data = BoardData(todo=[], in_progress=[], review=[], merged=[], done=[])
        render_board_data(data, "sprint-1", output, term_width=80, term_height=30)
        text = output.getvalue()
        assert "sprint-1" in text
        assert "To Do (0)" in text

    def test_narrow_terminal(self, sample_board: BoardData) -> None:
        output = StringIO()
        # Minimum viable width — 5 columns need more space
        render_board_data(sample_board, "sprint-7", output, term_width=100, term_height=20)
        text = output.getvalue()
        # Should not crash, should still have columns
        assert "│" in text

    def test_returns_rendered_string(self, sample_board: BoardData) -> None:
        output = StringIO()
        result = render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        assert isinstance(result, str)
        assert result == output.getvalue()

    def test_agent_names_shortened(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        assert "Barry_BE" in text
        assert "Cindy_CE" in text
        assert "Fred_FE" in text
        assert "Bonnie_BE" in text

    def test_clears_to_end_of_screen(self, sample_board: BoardData) -> None:
        output = StringIO()
        render_board_data(sample_board, "sprint-7", output, term_width=200, term_height=40)
        text = output.getvalue()
        # ESC[J = clear from cursor to end of screen
        assert "\033[J" in text


# ── get_memory_stats ─────────────────────────────────────────────────────


class TestGetMemoryStats:
    def test_returns_string_with_ram(self) -> None:
        result = get_memory_stats()
        assert "RAM:" in result

    def test_returns_string_with_swap(self) -> None:
        result = get_memory_stats()
        assert "Swap:" in result or "N/A" in result

    def test_graceful_fallback_when_no_proc_meminfo(self) -> None:
        with patch("scrimmage_board.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = get_memory_stats()
            assert "RAM: N/A" in result


# ── monitor_board ────────────────────────────────────────────────────────


class TestMonitorBoard:
    def test_enters_alternate_screen_buffer(self) -> None:
        output = StringIO()
        with patch("scrimmage_board.render_board"):
            with patch("scrimmage_board.time.sleep", side_effect=KeyboardInterrupt):
                monitor_board("sprint-7", output=output)
        text = output.getvalue()
        # ESC[?1049h = enter alternate screen buffer
        assert "\033[?1049h" in text

    def test_exits_alternate_screen_buffer(self) -> None:
        output = StringIO()
        with patch("scrimmage_board.render_board"):
            with patch("scrimmage_board.time.sleep", side_effect=KeyboardInterrupt):
                monitor_board("sprint-7", output=output)
        text = output.getvalue()
        # ESC[?1049l = leave alternate screen buffer
        assert "\033[?1049l" in text

    def test_moves_cursor_home(self) -> None:
        output = StringIO()
        with patch("scrimmage_board.render_board"):
            with patch("scrimmage_board.time.sleep", side_effect=KeyboardInterrupt):
                monitor_board("sprint-7", output=output)
        text = output.getvalue()
        # ESC[H = cursor home
        assert "\033[H" in text

    def test_stops_on_interrupt(self) -> None:
        output = StringIO()
        with patch("scrimmage_board.render_board"):
            with patch("scrimmage_board.time.sleep", side_effect=KeyboardInterrupt):
                monitor_board("sprint-7", output=output)
        text = output.getvalue()
        assert "Board stopped" in text


# ── build_tmux_command ───────────────────────────────────────────────────


class TestBuildTmuxCommand:
    def test_starts_with_tmux(self) -> None:
        cmd = build_tmux_command("sprint-7")
        assert cmd[0] == "tmux"
        assert cmd[1] == "new-window"

    def test_detached(self) -> None:
        cmd = build_tmux_command("sprint-7")
        assert "-d" in cmd

    def test_window_name(self) -> None:
        cmd = build_tmux_command("sprint-7")
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "scrimmage-board"

    def test_shell_cmd_contains_sprint(self) -> None:
        cmd = build_tmux_command("sprint-7")
        shell_cmd = cmd[-1]
        assert "sprint-7" in shell_cmd

    def test_shell_injection_blocked(self) -> None:
        cmd = build_tmux_command("evil;rm -rf /")
        shell_cmd = cmd[-1]
        assert ";rm -rf /" not in shell_cmd.split("'")[0]


# ── launch_board ─────────────────────────────────────────────────────────


class TestLaunchBoard:
    @patch("scrimmage_board.subprocess.run")
    def test_calls_subprocess(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_board("sprint-7")
        mock_run.assert_called_once()

    @patch("scrimmage_board.subprocess.run")
    def test_passes_check_true(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        launch_board("sprint-7")
        _args, kwargs = mock_run.call_args
        assert kwargs["check"] is True

    @patch("scrimmage_board.subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux"))
    def test_raises_on_failure(self, mock_run: MagicMock) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            launch_board("sprint-7")


# ── CLI ──────────────────────────────────────────────────────────────────


class TestCLI:
    @patch("scrimmage_board.monitor_board")
    def test_inline_mode(self, mock_monitor: MagicMock) -> None:
        main(["--sprint", "sprint-7"])
        mock_monitor.assert_called_once_with("sprint-7")

    @patch("scrimmage_board.launch_board")
    def test_tmux_mode(self, mock_launch: MagicMock) -> None:
        mock_launch.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        main(["--sprint", "sprint-7", "--tmux"])
        mock_launch.assert_called_once_with("sprint-7")

    def test_missing_sprint(self) -> None:
        with pytest.raises(SystemExit):
            main([])
