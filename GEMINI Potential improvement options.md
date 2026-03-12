# GEMINI Potential Improvement Options

This document outlines recommended improvements for the MCS-OTEL mapping tool, focusing on OpenTelemetry (OTEL) compliance, architectural robustness, and telemetry richness.

## 1. OpenTelemetry Standards & Compliance

### 1.1 Resource Semantic Conventions
**Current State:** The `service.name` is hardcoded to `copilot-studio`, and other resource attributes are static.
**Recommendation:**
- Extract the Bot Name or Schema Name from the transcript to populate `service.name` dynamically.
- Populate `service.instance.id` with the `conversationId` or `botId` to distinguish instances.
- Add `deployment.environment` (e.g., "production", "test") if available in the transcript metadata.
- **Benefit:** Allows filtering telemetry by specific bots and environments in backend systems.

### 1.2 Span Status Mapping
**Current State:** Errors (like `ErrorTraceData`) are logged as events, but the containing Span's status is not explicitly set to `ERROR`.
**Recommendation:**
- Update `converter.py` to listen for specific error events or properties (e.g., `outcome="Failure"`).
- When an error is detected, set the OTEL Span `status.code` to `ERROR` and `status.message` to the error description.
- **Benefit:** APM tools will correctly highlight failed conversations and turns.

### 1.3 Trace Context Propagation
**Current State:** Each transcript starts a new root trace.
**Recommendation:**
- Check for standard trace headers (e.g., `traceparent`, `tracestate`) in the transcript's initial metadata or headers.
- If found, use them as the parent context for the `session_root` span.
- **Benefit:** Connects the Copilot conversation trace to the upstream client (e.g., a web app hosting the bot) for full end-to-end distributed tracing.

## 2. Richer Telemetry & Data Mapping

### 2.1 Enriched Event Attributes
**Current State:** Several event types (e.g., `VariableAssignment`, `UnknownIntent`) are mapped as generic events with **empty attribute lists**.
**Recommendation:**
- **VariableAssignment:** Map `variable_name`, `new_value`, and `previous_value` as attributes on the event.
- **Topic Start/End:** Capture `topic.id` and `trigger.type` on these events.
- **Latencies:** Calculate and attach `duration_ms` to events that represent point-in-time markers if duration data is available nearby.

### 2.2 Structured Attribute Handling
**Current State:** Complex nested objects (like search results or tool outputs) are often flattened into comma-separated strings or simple text representations.
**Recommendation:**
- Use **JSON-stringified values** for complex attributes (e.g., `gen_ai.tool.call.arguments`, `gen_ai.retrieval.documents`).
- This allows backend analysis tools to parse and query the structured data, rather than treating it as a blob of text.

### 2.3 Fix Data Inconsistencies
**Current State:** There is a mismatch where `DynamicPlanReceived` uses `planIdentifier` but `DynamicPlanFinished` uses `planId`.
**Recommendation:**
- Standardize on a single attribute key (e.g., `mcs.plan.id`) across all related spans to ensure they can be correlated easily.

## 3. Architectural Improvements

### 3.1 Decouple Mappings from Code
**Current State:** The `generate_default_mapping()` function in `converter.py` contains 500+ lines of hardcoded Python objects.
**Recommendation:**
- Move mapping rules to a separate **YAML or JSON configuration file**.
- Create a loader that reads these rules at startup.
- **Benefit:** Allows users to tweak mappings or add new ones without modifying the application code.

### 3.2 Enhanced Validation & Error Handling
**Current State:** `parsers.py` often falls back to raw dictionary parsing if validation fails, potentially masking schema issues.
**Recommendation:**
- Implement strict Pydantic validation with `try/except` blocks that log warnings when transcript data doesn't match the expected schema.
- Add a "validation report" to the UI/CLI output to warn users about malformed transcript entries.

## 4. New Features & Usability

### 4.1 Batch Conversion CLI
**Current State:** The CLI is primarily for *analysis*, while the UI handles *conversion*.
**Recommendation:**
- Create a `convert_transcripts.py` CLI tool.
- Input: A directory of JSON transcripts.
- Output: A directory of OTLP JSON trace files.
- **Benefit:** Enables CI/CD integration and bulk processing of historical data for backfilling.

### 4.2 PII Redaction
**Current State:** Transcripts are processed as-is.
**Recommendation:**
- Add a middleware step in `parsers.py` to scrub sensitive data (emails, credit cards, phone numbers) before it reaches the mapping logic.
- Allow configuring a "redaction list" of variable names (e.g., `user_email`, `password`) to automatically mask.

### 4.3 Interactive "Debugger" View
**Current State:** The UI is great for visual mapping, but debugging why a specific activity didn't map is hard.
**Recommendation:**
- Add a "Trace Explanation" view in the UI: Click a span to see exactly which logic/rule generated it and which source JSON object it came from.
