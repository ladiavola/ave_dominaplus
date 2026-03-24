# Next Release Changelog

## Highlights

### Added
- Discovery logic was improved to include thermostats not present in map data.
- Diagnostics support
- Webserver autodiscovery (zeroconf) and setup flow
- Developer tooling and docs additions:
  - `pyproject.toml`-based lint/format configuration.
  - New development scripts and utilities.
  - Dedicated developer documentation in `/docs/development`.

### Changed
- WebSocket command handling and record serialization/deserialization were refined.
- Additional AVE family constants and handling paths were introduced.
- Entity update strategy moved to non-polling for async-managed entities where applicable.
- CI/workflows updated (hassfest/lint/hacs validation and branch protection aligned).
- Devcontainer and VS Code settings were aligned for local contributor workflows.

### Fixed
- Sensor adoption and startup/reload reliability improvements.
- XML handling hardened by switching to `defusedxml`.
- General cleanup, linting, and formatting fixes across integration and tooling files.
- Thermostats' properties typing, some glaring bugs in update parsing (season)

## Suggested Release Notes (Short Form)
- Thermostats: improved discovery, including devices not present in any map.
- Thermostats: fixed some bugs recovering season and other states for newer models
- Thermostats: (tentative) enable turn on for devices that supports it
- Webserver autodiscovery (zeroconf).
- Diagnostic dump for easier trubleshooting
- Development tools and documentation to help contributors get started
