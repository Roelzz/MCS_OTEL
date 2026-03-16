# Model GPT five three codecs — Potential improvement options

## Goal alignment summary

This project already has strong foundations: transcript parsing across multiple shapes, a mapping spec model, OTLP export, a visual mapping UI, and broad test coverage.

To better achieve the stated goal (rich, standards-aligned OTEL telemetry from Copilot Studio transcripts), the highest-value improvements are below.

---

## Option 1 — Fix mapping correctness edge cases (highest priority)

### Why

There is matching logic that can incorrectly map one entity to the wrong rule when value type names overlap (example: `DynamicPlanReceived` and `DynamicPlanReceivedDebug`).

### Recommended changes

- Store raw `value_type` on each extracted trace entity.
- Change rule matching to strict equality against that `value_type` (not substring checks on `entity_id`).
- Improve parent selection logic for both spans and events to choose the nearest valid parent by timestamp.

### Expected outcome

Cleaner trace trees, fewer false spans/events, and more trustworthy analytics.

---

## Option 2 — Standardize attribute namespace and semantic conventions

### Why

The codebase currently mixes prefixes (for example, `mcs.*` and `copilot_studio.*`), making dashboards and governance harder.

### Recommended changes

- Pick one canonical custom namespace (`copilot_studio.*` recommended).
- Add a compatibility layer for legacy keys during transition.
- Align operation names and target lists consistently across:
  - `models.OTELOperationName`
  - `converter.generate_default_mapping()`
  - React Flow OTEL targets in `web/state/_mapping.py`

### Expected outcome

Stable schema contracts, easier KQL queries, and fewer UI/edge mismatches.

---

## Option 3 — Emit typed OTLP attributes/events instead of string-only values

### Why

`to_otlp_json()` currently serializes all attributes as `stringValue`, reducing query quality for numeric/boolean analytics.

### Recommended changes

- Infer and emit OTLP value types (`stringValue`, `boolValue`, `intValue`, `doubleValue`, arrays).
- Preserve type for event attributes too.
- Add tests for typed serialization and KQL-friendly numeric filtering.

### Expected outcome

Much better downstream analytics (percentiles, thresholds, aggregations).

---

## Option 4 — Preserve temporal precision and chronology

### Why

Timestamps are normalized to integer seconds early, which can flatten event order and step-level durations.

### Recommended changes

- Preserve original precision as epoch milliseconds or nanoseconds in parser models.
- Keep original source timestamp string in attributes for auditability.
- Use stable time-based parent matching and ordering for events.

### Expected outcome

Higher-fidelity spans, better latency analytics, improved causality reconstruction.

---

## Option 5 — Make GenAI message attributes JSON-safe and spec-friendly

### Why

Current template replacement can produce invalid JSON when message text includes quotes/newlines.

### Recommended changes

- Build message arrays as Python structures, then `json.dumps`.
- Optionally include role/content metadata as events for richer replay.
- Add tests for escaped content and multiline messages.

### Expected outcome

Reliable `gen_ai.input.messages` / `gen_ai.output.messages` values in every transcript.

---

## Option 6 — Expand mapping richness from discovered transcript properties

### Why

`analyze_transcripts.py` already identifies unmapped properties per valueType, but conversion still leaves useful fields on the table.

### Recommended changes

- Prioritize high-value missing mappings:
  - `DynamicPlanStepTriggered`: `stepId`, `state`, `planIdentifier`
  - `DynamicPlanStepFinished`: `executionTime`, `planIdentifier`, `stepId`
  - `DialogRedirect`: `targetDialogType`
  - `ProtocolInfo`: endpoint-related fields
- Introduce a `mapping profile` concept:
  - `strict_otel`
  - `balanced`
  - `rich_custom`

### Expected outcome

Richer observability without sacrificing standards discipline.

---

## Option 7 — Improve mapping authoring UX (major usability win)

### Why

The connection view is strong, but rule editing is still limited and error-prone for non-developers.

### Recommended changes

- Add a full attribute-mapping editor in the UI:
  - mcs property picker
  - otel attribute picker (from registry)
  - transform type/value editor
- Add inline validation:
  - invalid parent rule IDs
  - multiple roots
  - unknown OTEL keys
  - duplicate rule IDs
- Add “Apply recommendations from transcript analysis” workflow.

### Expected outcome

A genuinely user-friendly mapping tool for product teams and analysts, not only engineers.

---

## Option 8 — Replace silent failures with explicit, guided errors

### Why

Several paths swallow exceptions (`except Exception: pass` / empty fallback), which hides actionable failures.

### Recommended changes

- Replace broad catches with typed exceptions and user-facing error messages.
- Surface parse/mapping/preview failures in UI with remediation hints.
- Log structured diagnostics (input type, rule ID, entity ID, stage).

### Expected outcome

Faster debugging and better trust in tool outputs.

---

## Option 9 — Add privacy controls (PII redaction modes)

### Why

Raw transcript text can contain sensitive data; currently there is no redaction pipeline.

### Recommended changes

- Add optional redaction stage before preview/export:
  - `off`
  - `mask`
  - `hash`
- Redact both message attributes and selected custom fields.
- Emit metadata flags (`copilot_studio.redaction.applied`, policy name, version).

### Expected outcome

Safer production use and easier enterprise adoption.

---

## Option 10 — Productionize export path (App Insights / Collector)

### Why

Current output is downloadable JSON. Teams still need manual steps to ingest it.

### Recommended changes

- Add optional direct export targets:
  - OTLP HTTP endpoint
  - OpenTelemetry Collector
  - Azure Monitor/App Insights endpoint
- Add retry/backoff and export status reporting.

### Expected outcome

Shorter path from transcript analysis to operational dashboards.

---

## Option 11 — Test and CI hardening for portability

### Why

Some tests use absolute local paths, reducing portability across environments.

### Recommended changes

- Replace absolute transcript paths with repository fixtures only.
- Add regression tests for:
  - overlapping value type names
  - JSON escaping in message templates
  - typed OTLP value emission
- Add CI checks for tests + lint on PR.

### Expected outcome

More reliable collaboration and fewer “works on my machine” failures.

---

## Option 12 — Keep documentation synchronized with code automatically

### Why

Current documentation contains drift (for example rule counts and references to non-existent files).

### Recommended changes

- Auto-generate mapping inventory docs from live code (`generate_default_mapping()` + registry).
- Add a docs validation check in CI to detect stale references.
- Publish a “current coverage” dashboard artifact per run.

### Expected outcome

Docs that stay trustworthy as mapping logic evolves.

---

## Suggested implementation order

1. **Correctness first:** Options 1, 4, 5, 8  
2. **Standards/data quality:** Options 2, 3, 6  
3. **User experience:** Option 7  
4. **Production readiness:** Options 9, 10, 11, 12

