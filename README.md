# MCS-OTEL

Converts Microsoft Copilot Studio conversation transcripts into OpenTelemetry-compatible traces and spans for observability. Multi-tab dashboard for uploading transcripts, visually mapping MCS entities to OTEL attributes, previewing span trees, browsing sessions and entities, inspecting rule hierarchies, and exporting OTLP JSON.

## Features

**Overview tab** — upload MCS transcript JSON or Dataverse CSV, visual ETL mapping (React Flow), live span tree preview with clickable inspector, error correlation, and OTLP JSON export

**Session tab** — session dashboard with conversation chat view

**Entities tab** — entity browser for exploring extracted MCS entities

**Rule Graph tab** — rule hierarchy visualization with per-attribute fill rate bars and per-rule match stats

**Registry tab** — event registry with attribute mappings visible on rule cards

**Improve page** (`/improve`) — self-learning improvement engine with guided apply workflow and diff preview

**Core:**
- Config-driven mapping — all rules, attributes, and descriptions in `config/default_mapping.json`
- 28 default mapping rules covering 26 event types
- Full OTLP compliance (Client SpanKind for root, UNSET status codes)
- Deep support for MCP, AI Builder, and Knowledge Retrieval tracing

## Quick Start

```bash
uv sync
uv run reflex run
```

Open `http://localhost:3000`.

## Project Structure

```
MCS_OTEL/
├── main.py                  # Reflex app entry point
├── rxconfig.py              # Reflex configuration (ports, env)
├── models.py                # Data models: MCSActivity, OTELSpan, SpanMappingRule, etc.
├── parsers.py               # Transcript parsing and entity extraction (config-driven)
├── converter.py             # Entity → OTEL span mapping, OTLP JSON export (config-driven)
├── otel_registry.py         # OTEL attribute definitions across 10 categories
├── config_loader.py         # Loads and validates mapping config from JSON
├── log.py                   # Shared loguru logging configuration
├── utils.py                 # Shared utility functions
├── analyze_transcripts.py   # CLI: transcript coverage analysis
├── improve.py               # Self-learning improvement engine (outputs config updates)
├── pyproject.toml           # Project config and dependencies
├── web/
│   ├── web.py               # Reflex frontend layout + /improve route
│   ├── components/          # UI: upload, mapping_editor, react_flow, span_tree, export,
│   │                        #   session_dashboard, conversation_view, entity_browser,
│   │                        #   rule_hierarchy, event_registry, connection_view,
│   │                        #   navbar, improve_dashboard
│   └── state/               # Reflex state managers (upload, mapping, preview, improve)
├── config/
│   └── default_mapping.json # Single source of truth for all mapping rules, attributes, and metadata
├── tests/
│   ├── test_parsers.py            # Parser unit tests
│   ├── test_models.py             # Model unit tests
│   ├── test_converter.py          # Converter unit tests
│   ├── test_enrichment.py         # Entity enrichment tests
│   ├── test_improve.py            # Improvement engine tests
│   ├── test_config_loader.py      # Config loader unit tests
│   ├── test_analyze_transcripts.py # Transcript analysis CLI tests
│   └── fixtures/                  # Sample transcript JSON + CSV files
└── docs/
    ├── gap-analysis.md            # Capability gap analysis (42 capabilities)
    └── transcript_analysis.md     # Generated: valueType coverage report
```

## Transcript Analysis CLI

Scans all available transcripts, cross-references every `valueType` against tracked event types and mapping rules in `config/default_mapping.json`, and produces a markdown report with coverage gaps and suggested config additions.

### Usage

```bash
# Default: scan tests/fixtures/ and Agent_analyser/ directories
uv run python analyze_transcripts.py

# Scan specific directory (JSON + CSV files)
uv run python analyze_transcripts.py tests/fixtures/

# Scan a Dataverse CSV export directly
uv run python analyze_transcripts.py samples/conversationtranscripts.csv

# Custom output path with verbose logging
uv run python analyze_transcripts.py -o custom_report.md -v

# Scan multiple paths
uv run python analyze_transcripts.py tests/fixtures/ samples/
```

### Output Report

The generated `docs/transcript_analysis.md` contains:

- **Summary** — files analyzed, total activities, unique valueTypes, coverage stats
- **All ValueTypes** — table with count, tracked status, mapping rule status, property coverage
- **Untracked ValueTypes** — sample payload + suggested JSON config snippet for `default_mapping.json`
- **Attribute Mapping Gaps** — per tracked type: available vs mapped vs unmapped properties with suggested attribute mapping JSON
- **Tracked Types Missing Rules** — types in tracked event types without a mapping rule

### Acting on Findings

1. Add suggested mapping rules and attribute mappings to `config/default_mapping.json`
2. Add new valueTypes to `tracked_event_types` in `config/default_mapping.json`
3. Or use the improvement cycle (`improve.py run`) which outputs a `proposed_mapping.json` with all changes

## Mapping Architecture

MCS transcript entities are mapped to OTEL spans through `SpanMappingRule` objects:

```
MCS Activity (valueType) → Entity Extraction → SpanMappingRule → OTEL Span
```

**Entity types:** `trace_event` (from activity valueTypes), `turn` (user-bot message pairs)

**OTEL operations:** `agent.turn`, `gen_ai.chat`, `tool.execute`, `knowledge.retrieval`, `chain`, `text_completion`, `create_agent`, `topic_classification`

### Config File (`config/default_mapping.json`)

The config file is the single source of truth for all mapping definitions:

- **`mapping_rules`** — all span mapping rules with descriptions, event metadata, and attribute mappings
- **`tracked_event_types`** — which MCS valueTypes to process
- **`otel_attributes`** — attribute definitions across 10 categories
- **`session_info_extraction`** — config-driven field extraction from SessionInfo/ConversationInfo
- **`derived_session_fields`** — config-driven environment derivation (e.g. channel, locale)
- **`changelog`** — version history with changes per version

**Span hierarchy:**
```
session_root (agent.turn)
└── user_turn (gen_ai.chat)
    ├── dynamic_plan (chain)
    │   ├── plan_step_triggered (chain)
    │   ├── plan_step_bind (chain)
    │   ├── plan_step_finished (tool.execute)
    │   └── plan_finished (chain)
    ├── knowledge_search (knowledge.retrieval)
    ├── topic_classification (topic_classification)
    ├── dialog_tracing (chain)
    └── mcp_server_init (create_agent)
        └── mcp_server_init_confirmation (create_agent)
```

## Self-Learning Improvement Loop

Uses hundreds of real transcripts as a training corpus to iteratively improve the mapping config. Auto-fixes obvious gaps, presents ambiguous ones for human review.

### Quick Start (CLI)

```bash
# Point at a directory of JSON files
uv run python improve.py run /path/to/transcripts/

# Point at a Dataverse CSV export (one transcript per row in 'content' column)
uv run python improve.py run /path/to/conversationtranscripts.csv

# Point directly at the samples directory
uv run python improve.py run samples/
```

### Workflow

```bash
uv run python improve.py run samples/       # Run analysis, produce proposed_mapping.json
uv run python improve.py diff               # Review differences
uv run python improve.py approve            # Apply with version bump
```

### CLI Flags

- `-n` / `--max-iterations` — max improvement iterations (default: 5)
- `--min-files` — min conversations for auto-fix threshold (default: 3, lower = more aggressive)
- `-o` / `--output` — output directory for results (default: `improve_runs/`)
- `-v` / `--verbose` — enable verbose logging

### Web Dashboard

```bash
uv run reflex run
# Navigate to http://localhost:3000/improve
```

The dashboard (accessible via the "Improve Mapping" navbar button) provides a guided 5-step workflow:

1. **Configure** — set input directory, max iterations, min conversations threshold
2. **Analyze** — iteration timeline, coverage chart, auto-applied vs needs-review summary
3. **Review & Approve** — accept/reject each finding with code preview
4. **Preview & Apply** — diff preview of proposed config changes before applying to `config/default_mapping.json`
5. **Verify** — re-run to confirm improvements with before/after comparison

### How It Works

1. **Scan** — discover all `.json` and `.csv` files in the input directory (CSV: each row with a `content` column yields one transcript; handles Dataverse BOM encoding)
2. **Analyze** — process each transcript through the full pipeline, collect unknown types, unmapped properties, empty spans, coverage metrics
3. **Classify** — sort findings into auto-fix (type in >= 3 files) vs needs-review (nested structures, rare types)
4. **Apply** — auto-fixes modify the in-memory mapping spec; needs-review items presented as suggestions
5. **Re-analyze** — run again with improved mapping, measure delta
6. **Report** — per-iteration summary + code export with all changes

### What Gets Improved

| File | Improvements |
|------|-------------|
| `config/default_mapping.json` | New mapping rules, event metadata, attribute mappings, tracked event types |

### Output

Results are saved to `improve_runs/`:
- `iter_N_<hash>.json` — per-iteration metrics and findings
- `proposed_mapping.json` — the proposed config changes ready for review

## Next Steps

- **Gather more transcripts** — export from Copilot Studio Analytics, Dataverse `conversationtranscript` table (CSV with `content` column), or Test Canvas
- **Run the improvement loop** to auto-discover and fix mapping gaps
- **Run the analysis CLI** after adding new transcripts to find gaps
- **Review `docs/transcript_analysis.md`** for suggested config updates
- **Add suggested mappings** to `config/default_mapping.json`
- **Future:** live OTEL collector integration, token accounting, PII redaction

## Tech Stack

Python 3.12, UV, Reflex, Pydantic, React Flow
