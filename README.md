# MCS-OTEL

Converts Microsoft Copilot Studio conversation transcripts into OpenTelemetry-compatible traces and spans for observability. Upload a transcript JSON, visually map MCS entities to OTEL attributes, preview the span tree, and export OTLP JSON.

## Features

- Upload MCS transcript JSON or Dataverse CSV (dialog.json / Dataverse export / Rex format)
- Visual ETL mapping UI (React Flow) — drag-and-drop MCS entities to OTEL targets
- 28 default mapping rules covering 26 event types
- 104 OTEL attribute definitions across 10 categories
- Full OTLP compliance (Client SpanKind for root, UNSET status codes)
- Deep support for MCP, AI Builder, and Knowledge Retrieval tracing
- Live span tree preview with OTLP JSON export
- Self-learning improvement engine (`improve.py`) for auto-discovering mappings

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
├── parsers.py               # Transcript parsing, entity extraction, enrichment
├── converter.py             # Entity → OTEL span mapping, OTLP JSON export
├── otel_registry.py         # 104 OTEL attribute definitions across 10 categories
├── analyze_transcripts.py   # CLI: transcript coverage analysis
├── improve.py               # Self-learning mapper improvement engine
├── pyproject.toml           # Project config and dependencies
├── web/
│   ├── web.py               # Reflex frontend layout + /improve route
│   ├── components/          # UI components (upload, mapping editor, span tree, export, improve dashboard)
│   └── state/               # Reflex state managers (upload, mapping, preview, improve)
├── tests/
│   ├── test_parsers.py      # Parser unit tests
│   ├── test_models.py       # Model unit tests
│   ├── test_converter.py    # Converter unit tests
│   ├── test_enrichment.py   # Entity enrichment tests
│   ├── test_improve.py      # Improvement engine tests
│   └── fixtures/            # Sample transcript JSON + CSV files
└── docs/
    ├── gap-analysis.md            # Capability gap analysis (42 capabilities)
    └── transcript_analysis.md     # Generated: valueType coverage report
```

## Transcript Analysis CLI

Scans all available transcripts, cross-references every `valueType` against `TRACKED_EVENT_TYPES` and `generate_default_mapping()` rules, and produces a markdown report with coverage gaps and suggested mapping code.

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
- **Untracked ValueTypes** — sample payload + suggested `SpanMappingRule` Python snippet
- **Attribute Mapping Gaps** — per tracked type: available vs mapped vs unmapped properties with suggested `AttributeMapping` snippets
- **Tracked Types Missing Rules** — types in `TRACKED_EVENT_TYPES` without a mapping rule

### Acting on Findings

1. Copy suggested `SpanMappingRule` snippets into `converter.py` → `generate_default_mapping()`
2. Add new valueTypes to `TRACKED_EVENT_TYPES` in `parsers.py`
3. Add enrichment logic to `_enrich_entity_properties()` in `parsers.py` if nested flattening is needed

## Mapping Architecture

MCS transcript entities are mapped to OTEL spans through `SpanMappingRule` objects:

```
MCS Activity (valueType) → Entity Extraction → SpanMappingRule → OTEL Span
```

**Entity types:** `trace_event` (from activity valueTypes), `turn` (user-bot message pairs)

**OTEL operations:** `agent.turn`, `gen_ai.chat`, `tool.execute`, `knowledge.retrieval`, `chain`, `text_completion`, `create_agent`, `topic_classification`

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

Uses hundreds of real transcripts as a training corpus to iteratively improve the mapper. Auto-fixes obvious gaps, presents ambiguous ones for human review.

### Quick Start (CLI)

```bash
# Point at a directory of JSON files
uv run python improve.py /path/to/transcripts/

# Point at a Dataverse CSV export (one transcript per row in 'content' column)
uv run python improve.py /path/to/conversationtranscripts.csv

# Point directly at the samples directory
uv run python improve.py samples/
```

### CLI Flags

- `-n` / `--max-iterations` — max improvement iterations (default: 5)
- `--min-files` — min file count for auto-fix threshold (default: 3)
- `-o` / `--output` — output directory for results (default: `improve_runs/`)
- `-v` / `--verbose` — enable verbose logging

### Web Dashboard

```bash
uv run reflex run
# Navigate to http://localhost:3000/improve
```

The dashboard provides:
- **Controls** — set input directory, max iterations, min files threshold
- **Iteration timeline** — cards showing coverage%, fill rate, auto-fixes per iteration
- **Coverage chart** — line chart showing improvement across iterations
- **Pending review** — findings needing human decision with accept/reject buttons
- **Code export** — generated code changes per target file
- **Apply to source** — writes accepted changes directly to `parsers.py`, `converter.py`, `otel_registry.py`

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
| `parsers.py` | New types in `TRACKED_EVENT_TYPES`, new enrichment blocks |
| `converter.py` | New `SpanMappingRule` entries, new `AttributeMapping` entries |
| `otel_registry.py` | New `OTELAttribute` entries in `MCS_CUSTOM_ATTRIBUTES` |

### Output

Results are saved to `improve_runs/`:
- `iter_N_<hash>.json` — per-iteration metrics and findings
- `code_export.py` — all code changes ready to copy into source files
- `improved_mapping.json` — the final improved mapping specification

## Next Steps

- **Gather more transcripts** — export from Copilot Studio Analytics, Dataverse `conversationtranscript` table (CSV with `content` column), or Test Canvas
- **Run the improvement loop** to auto-discover and fix mapping gaps
- **Run the analysis CLI** after adding new transcripts to find gaps
- **Review `docs/transcript_analysis.md`** for suggested mapping updates
- **Implement suggested mappings** in `converter.py` and `parsers.py`
- **Future:** live OTEL collector integration, token accounting, PII redaction

## Tech Stack

Python 3.14, UV, Reflex, Pydantic, React Flow
