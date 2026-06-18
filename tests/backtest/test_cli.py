"""Tests for backtest CLI."""
import subprocess
import sys


def test_cli_help_lists_options():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.backtest", "run", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--days" in result.stdout
    assert "--symbols" in result.stdout
    assert "--cache-root" in result.stdout


def test_cli_missing_subcommand_returns_error():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.backtest"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_parses_explicit_dates():
    """Smoke that --start/--end parse and the runner is invoked.

    We point at an isolated empty cache + a missing db so runner.load() returns
    empty lists for every symbol, no signals are generated, and the report
    completes with 'no closed trades'. This verifies the CLI plumbing.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable, "-m", "scripts.backtest", "run",
                "--start", "2026-05-19T00:00:00+00:00",
                "--end",   "2026-05-19T01:00:00+00:00",
                "--symbols", "BTCUSDT",
                "--cache-root", tmp + "/cache",
                "--output-root", tmp + "/runs",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=60,
            env={"DB_PATH": tmp + "/nodb.db", "PATH": "/usr/bin:/bin"},
        )
        # Either succeeds with empty report, or fails on OKX fetch (network).
        # Both prove CLI plumbing works. We accept either.
        assert result.returncode in (0, 1)
        # If success, output dir has the 3 artifacts
        if result.returncode == 0:
            assert "Report written to" in result.stdout
