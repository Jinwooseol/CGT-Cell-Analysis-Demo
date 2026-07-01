"""Tests for the headless CLI entry point."""

from __future__ import annotations

from cgt_cell_analysis_demo import cli


def test_parser_builds_and_requires_command(capsys):
    parser = cli.build_parser()
    # No subcommand -> argparse exits with an error.
    try:
        parser.parse_args([])
    except SystemExit as exc:
        assert exc.code != 0
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit for missing command")


def test_info_returns_zero():
    assert cli.main(["info"]) == 0


def test_validate_ok_with_repo_reference_data():
    # Reference data ships in the repo, so default config validates.
    assert cli.main(["validate"]) == 0


def test_validate_requires_model_fails():
    # No model weights are committed, so --require-model fails cleanly.
    assert cli.main(["validate", "--require-model"]) == 1
