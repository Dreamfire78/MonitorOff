# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-08

### Added

- Tray icon: left-click turns all monitors off (`SC_MONITORPOWER`), the PC keeps running.
- Configurable global hotkey with a recording dialog; detects combinations already in use.
- Command line option `--off`.
- "Start with Windows" option.
- English and German translations; follows the Windows display language, selectable in the tray menu;
  additional languages can be dropped into a `lang` folder next to the exe.
- Tray icon adapts to light/dark taskbar.
- Single-instance protection; tray icon is restored after an Explorer restart.

[1.0.0]: https://github.com/Dreamfire78/MonitorOff/releases/tag/v1.0.0
