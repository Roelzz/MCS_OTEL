# MCS-OTEL

Converts Microsoft Copilot Studio conversation transcripts into OpenTelemetry-compatible traces and spans for observability. Upload a transcript JSON, visually map MCS entities to OTEL attributes, preview the span tree, and export OTLP JSON.

## Features

- Upload MCS transcript JSON (dialog.json / Dataverse export / Rex format)
- Visual ETL mapping UI (React Flow) — drag-and-drop MCS entities to OTEL targets
- 19 default mapping rules covering 18 event types
- Live span tree preview with OTLP JSON export
- Transcript analysis CLI for discovering unmapped events

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
├── otel_registry.py         # 56 OTEL attribute definitions across 10 categories
├── analyze_transcripts.py   # CLI: transcript coverage analysis
├── pyproject.toml           # Project config and dependencies
├── web/
│   ├── web.py               # Reflex frontend layout
│   ├── components/          # UI components (upload, mapping editor, span tree, export)
│   └── state/               # Reflex state managers (upload, mapping, preview)
├── tests/
│   ├── test_parsers.py      # Parser unit tests
│   ├── test_models.py       # Model unit tests
│   ├── test_converter.py    # Converter unit tests
│   ├── test_enrichment.py   # Entity enrichment tests
│   └── fixtures/            # Sample transcript JSON files
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

# Scan specific directory
uv run python analyze_transcripts.py tests/fixtures/

# Custom output path with verbose logging
uv run python analyze_transcripts.py -o custom_report.md -v

# Scan multiple paths
uv run python analyze_transcripts.py tests/fixtures/ /path/to/more/transcripts/
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

## Next Steps

- **Gather more transcripts** — export from Copilot Studio Analytics, Dataverse `conversationtranscript` table, or Test Canvas
- **Run the analysis CLI** after adding new transcripts to find gaps
- **Review `docs/transcript_analysis.md`** for suggested mapping updates
- **Implement suggested mappings** in `converter.py` and `parsers.py`
- **Future:** live OTEL collector integration, token accounting, PII redaction

## Tech Stack

Python 3.12, UV, Reflex, Pydantic, React Flow
