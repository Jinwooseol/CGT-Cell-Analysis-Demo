# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Headless CLI** (`cgt-cli`) that drives the full four-stage pipeline or any single stage without
  a display, plus `validate` and `info` commands.
- **Typed configuration** (`AppConfig`) with JSON load/save, project-root path resolution, and
  validation of referenced resources.
- **Reusable CSV I/O layer** (`io/csv_io.py`) for the instrument two-row-header format, now shared by
  the merge worker.
- **Standard-library logging** helpers (`configure_logging`, `get_logger`) alongside the existing
  `log_format`.
- **Test suite** (`pytest`, 38 tests) covering geometry, configuration, I/O, the CLI, and an
  end-to-end worker run.
- **Continuous integration** (GitHub Actions): `ruff` lint + format check and tests on Python
  3.10–3.12.
- Project scaffolding: `LICENSE` (MIT), `CONTRIBUTING.md`, `.editorconfig`, `.gitattributes`,
  `.pre-commit-config.yaml`, and packaging metadata with console entry points.

### Changed
- Overhauled `pyproject.toml`: full metadata, dependency groups (`ai`, `train`, `build`, `dev`),
  console scripts, and tooling configuration.
- Translated all in-code comments and docstrings to English.
- Replaced scattered debug `print()` calls with proper `logging`.
- Normalised formatting and resolved lint findings across the codebase.
- Added missing `__init__.py` files so every subpackage is importable and packageable.

### Fixed
- `TestJob.job_id` now generates a unique id per instance (was shared across instances).

## [1.0.0]
- Initial desktop application: optical well indexing, AI cell counting, PCR well indexing, result
  merging, optional training workflow, and PyInstaller packaging.
