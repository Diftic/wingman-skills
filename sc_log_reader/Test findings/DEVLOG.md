# SC Game.log Parser - Development Log

**Project:** SC Game.log Parser  
**Location:** `sc_log_parser/`  
**Developer:** Mallachi  
**Current Version:** v1.1.0  
**Development Period:** February 4, 2026 - Present

---

## Project Overview

Standalone Python script that parses Star Citizen Game.log files into structured Excel spreadsheets. Reads all `.log` files in its own directory, extracts timestamped entries with optional event types, and outputs a formatted `.xlsx` with per-file sheets and a combined "All Logs" view.

---

## Core Features

- Parses SC Game.log timestamp format: `<YYYY-MM-DDTHH:MM:SS.mmmZ>`
- Extracts event type brackets `[Type]` when present
- Extracts event sub-type angle brackets `<SubType>` when present
- Appends continuation lines (no timestamp) to previous entry
- Sanitizes illegal XML/Excel characters from binary log artifacts
- Individual sheet per log file + combined "All Logs" sheet (when multiple files)
- Auto-filter and frozen headers on all sheets
- Timestamped output filenames to avoid overwrites

---

## Development Timeline

### Phase 1: Project Inception [February 4, 2026]

**Initial Concept:**
Parse 10 Game.log files from multiple SC players (Mallachi, Xul, JaymMatthew, Teddybear) into a single structured Excel workbook for analysis. Originated from broader Game.log research for signature scanner and mining optimization tools.

**Key Decisions:**
- Chose openpyxl over pandas for output because formatting control (headers, column widths, auto-filter, freeze panes) matters more than data manipulation here. Pandas `to_excel` gives minimal formatting control.
- Regex-based line parsing rather than state machine — log format is simple enough that a two-regex approach (timestamp + event type) handles all observed patterns.
- Output filename includes timestamp (`GameLogs_Parsed_YYYYMMDD_HHMMSS.xlsx`) to prevent accidental overwrites when re-running.
- Combined "All Logs" sheet placed first (index=0) since cross-file filtering is the primary use case.

**Files Created:**
```
sc_log_parser/
├── sc_log_parser.py    # Main parser script
├── clean.py            # Build artifact cleanup
└── DEVLOG.md           # This file
```

---

## Version History

### v1.1.0 [February 4, 2026]
- Added Sub-Type column: extracts `<SubType>` angle brackets after event type
- Parse chain now: Timestamp → `[EventType]` → `<SubType>` → Content
- Removed auto-filter/table formatting (caused Excel errors on large datasets)
- Removed row borders (cleaner output, smaller file)
- 4-column layout: Timestamp | Event Type | Sub-Type | Content (5-column on combined sheet with Source)

### v1.0.0 [February 4, 2026]
- Initial release
- Parses all .log files in script directory
- Excel output with per-file sheets + combined sheet
- Character sanitization for binary log artifacts
- Auto-filter, frozen headers, styled output

---

## Technical Decisions Log

| Decision | Rationale |
|----------|-----------|
| Three-stage parse: `[Type]` then `<SubType>` | CryEngine log format uses square brackets for severity/category and angle brackets for component/function identifiers. Separating them enables filtering on either axis independently. |
| No auto-filter/table formatting | openpyxl auto-filter on 256k+ rows causes Excel repair prompts on open. Plain data with frozen headers works reliably. |
| openpyxl over pandas | Need header styling, freeze panes, column widths. Pandas to_excel gives flat data dumps. |
| Regex parsing over line.split() | Timestamps contain colons/brackets that conflict with naive splitting. Regex cleanly handles `<...>` and `[...]` patterns. |
| Continuation line appending | Some log entries span multiple lines (e.g. batch state dumps). Lines without timestamps belong to the previous entry. |
| Sanitize with `[\x00-\x08\x0b\x0c\x0e-\x1f]` regex | Game.log contains occasional binary/corrupt characters from CryEngine internals. openpyxl raises IllegalCharacterError on these. |
| 32,767 char cell truncation | Excel hard limit per cell. A few entries with massive URLs (Cedar/Elastic links) can approach this. |

---

## Known Issues / Future Work

### Deferred to Future Releases
- [ ] Optional CSV output mode for non-Excel workflows
- [ ] Command-line arguments for input/output paths
- [ ] Event type statistics summary sheet
- [ ] Timestamp parsing to proper Excel datetime (currently stored as string for exact fidelity)

### Known Bugs
- None yet

---

## External Dependencies

| Dependency | Purpose | License |
|------------|---------|---------|
| openpyxl | Excel file creation and formatting | MIT |

---

## Current Status / Next Steps

**Status:** v1.1.0 - Release

**Immediate priorities:**
1. Validate against additional Game.log samples
2. Consider event type filtering/statistics

**Blocking issues:** None

**Ready for:** Production use

---

## Credits

- **Developer:** Mallachi
- **Data Sources:** Star Citizen Game.log (CIG/RSI CryEngine diagnostic output)
- **Dependencies:** openpyxl

---

*Document created: February 4, 2026*  
*Last updated: February 4, 2026 (v1.1.0)*
