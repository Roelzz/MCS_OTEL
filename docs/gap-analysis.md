# MCS Agent Observability — Technical Gap Analysis

**Date:** 2026-03-11
**Scope:** Technical capabilities only — no product roadmap speculation, no licensing advice.
Every claim is backed by a specific MCS property path or OTEL attribute key from the MCS-OTEL Mapper codebase.

**Methodology:** Each capability is rated against two evidence sources:
1. **MCS transcript data** — what properties the Copilot Studio conversation transcript exposes (65 properties in `mcs_schema.py`)
2. **OTEL GenAI semantic conventions** — what attributes the MCS-OTEL Mapper can target (40 attributes in `otel_registry.py`)

**Ratings:**
- **Available** — end-to-end pipeline exists with active mapping rules
- **Partial** — data exists in MCS transcripts or OTEL registry but mapping is incomplete or absent
- **Gap** — no data source in MCS transcripts and no viable workaround in the mapper

**Bridge tool:** The [MCS-OTEL Mapper](../README.md) converts MCS conversation transcripts into OTEL GenAI-compliant traces. It currently has 4 mapping rules producing 9 attribute mappings.

---

## Executive Summary

| # | Section | Available | Partial | Gap | Total |
|---|---------|-----------|---------|-----|-------|
| 1 | Telemetry & Data Ingestion | 3 | 4 | 5 | 12 |
| 2 | Correlation & Context Enrichment | 2 | 3 | 1 | 6 |
| 3 | Storage, Indexing & Dashboards | 1 | 1 | 3 | 5 |
| 4 | Alerts & Anomaly Detection | 0 | 3 | 2 | 5 |
| 5 | Multi-Agent Observability | 0 | 1 | 3 | 4 |
| 6 | Governance, Compliance & Traceability | 1 | 2 | 2 | 5 |
| 7 | Privacy, Redaction & Responsible AI | 0 | 0 | 5 | 5 |
| | **Totals** | **7** | **14** | **21** | **42** |

> 7 capabilities are fully available today (17%). 14 are partially available (33%) — the data exists but mapping rules need to be added. 21 are gaps (50%) driven primarily by MCS transcript limitations.

---

## Section 1: Telemetry & Data Ingestion

### 1.1 Conversation Transcript Capture — Available

**What works:** `parsers.py` `_resolve_activities()` handles all known MCS JSON formats: bare activity arrays, `{"activities": [...]}` wrappers, and Dataverse `content` field nesting. The full transcript-to-entities-to-spans pipeline is operational.

**Evidence:**
- `parsers.py:92-113` — `_resolve_activities()` with three format branches
- `parsers.py:261-310` — `extract_entities()` flattens transcript into typed entities
- 12 tracked event types in `parsers.py:76-89` (`TRACKED_EVENT_TYPES`)

**KQL — Transcript ingestion volume:**
```kql
traces
| where customDimensions["gen_ai.system"] == "copilot_studio"
| summarize SessionCount = dcount(customDimensions["gen_ai.conversation.id"]) by bin(timestamp, 1h)
| render timechart
```

### 1.2 Session Lifecycle Telemetry — Available

**What works:** Full session lifecycle properties are captured and mapped. The `session_root` rule maps `SessionInfo` trace events to `invoke_agent` spans.

**Evidence:**
- `mcs_schema.py:58-69` — `trace.SessionInfo.*`: outcome, turnCount, startTimeUtc, endTimeUtc, impliedSuccess, outcomeReason, type, lastUserIntentId
- `converter.py:284-307` — `session_root` rule maps to `invoke_agent` span with 3 attribute mappings
- Active mappings: `outcome` → `copilot_studio.session_outcome`, `bot_name` → `gen_ai.agent.name`, `conversation_id` → `gen_ai.conversation.id`

**KQL — Session outcome distribution:**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend outcome = tostring(customDimensions["copilot_studio.session_outcome"])
| summarize Count = count() by outcome
| render piechart
```

**KQL — Turn count analysis:**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend turnCount = toint(customDimensions["copilot_studio.turn_count"])
| summarize avg(turnCount), percentile(turnCount, 50), percentile(turnCount, 95)
```

### 1.3 Turn-Level Message Capture — Available

**What works:** User-bot turn pairs are extracted and mapped to `chat` spans with message content in OTEL GenAI format.

**Evidence:**
- `parsers.py:217-258` — `_extract_turns()` groups activities into user-initiated turns
- `converter.py:308-333` — `user_turn` rule maps to `chat` span
- Active mappings: `user_msg` → `gen_ai.input.messages` (template transform wrapping in JSON), `bot_msg` → `gen_ai.output.messages` (template transform), `topic_name` → `copilot_studio.topic_name`

**KQL — Message content search:**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "chat"
| extend userMsg = tostring(customDimensions["gen_ai.input.messages"])
| extend botMsg = tostring(customDimensions["gen_ai.output.messages"])
| project timestamp, userMsg, botMsg
| take 100
```

### 1.4 OTEL GenAI Semantic Convention Compliance — Partial

**What works:** 40 attributes defined in `otel_registry.py` across 9 categories. 9 attributes are actively mapped by the 4 default rules. The output conforms to OTLP JSON format.

**What's missing:** 31 defined attributes have no active mapping rule. Key unmapped attributes:
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` — defined but MCS has no token data
- `gen_ai.request.model` — defined but MCS doesn't expose model identity
- `gen_ai.response.id` — defined but MCS doesn't provide response IDs
- `gen_ai.system_instructions` — defined but MCS doesn't include system prompts

**Evidence:**
- `otel_registry.py:291-301` — `ALL_ATTRIBUTES` combines all 9 category lists (40 total)
- `converter.py:277-371` — 4 rules × 9 attribute mappings active

### 1.5 Tool/Action Invocation Telemetry — Partial

**What works:** `UniversalSearchToolTraceData` events are mapped to `execute_tool` spans via the `knowledge_search` rule.

**What's missing:** Only knowledge search tool calls are captured. Connector calls, HTTP actions, Power Automate flow invocations, and custom plugin executions are absent from MCS transcripts.

**Evidence:**
- `mcs_schema.py:146-170` — `event.UniversalSearchToolTraceData.*`: toolId, knowledgeSources, outputKnowledgeSources, fullResults, filteredResults
- `converter.py:334-354` — `knowledge_search` rule: `toolId` → `gen_ai.tool.name`, constant `"datastore"` → `gen_ai.tool.type`
- `otel_registry.py:93-130` — 6 tool attributes defined (name, type, description, call.id, call.arguments, call.result)

**KQL — Tool execution frequency:**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "execute_tool"
| extend toolName = tostring(customDimensions["gen_ai.tool.name"])
| summarize ExecutionCount = count() by toolName
| order by ExecutionCount desc
```

### 1.6 Orchestrator Plan Visibility — Partial

**What works:** All `DynamicPlan*` event types are tracked and the `dynamic_plan` rule maps `DynamicPlanReceived` to `chain` spans with `planIdentifier`.

**What's missing:** Rich orchestrator data exists in the schema but is unmapped:
- `event.DynamicPlanStepTriggered.thought` — LLM reasoning (chain-of-thought)
- `event.DynamicPlanStepFinished.executionTime` — step execution duration
- `event.DynamicPlanStepTriggered.state` — step state codes
- `event.DynamicPlanStepBindUpdate.arguments.*` — search queries and keywords

**Evidence:**
- `mcs_schema.py:84-202` — 8 DynamicPlan event types with 30+ properties
- `converter.py:355-371` — `dynamic_plan` rule: only `planIdentifier` → `copilot_studio.plan_identifier` mapped
- `otel_registry.py:246-276` — `copilot_studio.thought`, `copilot_studio.execution_time`, `copilot_studio.step_id` defined but unmapped

### 1.7 Token/Cost Accounting — Gap

**What exists:** `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are defined in the OTEL registry.

**Why it's a gap:** MCS conversation transcripts contain zero token usage data. The underlying LLM token consumption is not exposed by Copilot Studio in any transcript format.

**Evidence:**
- `otel_registry.py:78-91` — `USAGE_ATTRIBUTES`: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- No corresponding MCS schema property exists

**Workaround:** None available from transcript data. Would require a separate Azure AI Foundry or Azure OpenAI metrics pipeline.

### 1.8 Model Identification — Gap

**What exists:** `gen_ai.request.model` is defined in the OTEL registry.

**Why it's a gap:** MCS does not expose which LLM model backs a copilot agent. The model selection is abstracted away by the platform.

**Evidence:**
- `otel_registry.py:159-165` — `gen_ai.request.model` defined
- No corresponding MCS schema property exists

**Workaround:** Hardcode as a constant mapping if the model is known per environment (e.g., `"gpt-4o"` for production copilots).

### 1.9 System Prompt Capture — Gap

**What exists:** `gen_ai.system_instructions` is defined in the OTEL registry.

**Why it's a gap:** MCS transcripts do not include system prompts or custom instructions configured in the copilot. These are platform-internal.

**Evidence:**
- `otel_registry.py:152-157` — `gen_ai.system_instructions` defined
- No corresponding MCS schema property exists

### 1.10 Agent Runtime Hooks (Live OTEL) — Gap

**Why it's a gap:** The MCS-OTEL Mapper performs post-hoc transcript analysis. There is no live OTEL SDK integration for the Copilot Studio runtime — telemetry is generated after the conversation ends, not during execution.

**Impact:** No real-time span emission, no live dashboards, no in-flight trace correlation with downstream services.

### 1.11 Variable State Tracking — Partial

**What exists in MCS:** `trace.VariableAssignment` with name, id, newValue, and type (global/local scope).

**What exists in OTEL:** `copilot_studio.variable_name` and `copilot_studio.variable_value` are defined.

**What's missing:** No default mapping rule connects them. Requires adding a new `SpanMappingRule`.

**Evidence:**
- `mcs_schema.py:45-50` — `trace.VariableAssignment.*`: name, id, newValue, type
- `otel_registry.py:259-270` — `copilot_studio.variable_name`, `copilot_studio.variable_value`
- `parsers.py:86` — `"VariableAssignment"` in `TRACKED_EVENT_TYPES`

### 1.12 Error/Failure Capture — Partial

**What exists in MCS:** `ErrorTraceData` and `ErrorCode` are tracked event types.

**What's missing:** No mapping rule exists for error events. Error properties are not defined in `mcs_schema.py` beyond the type name.

**Evidence:**
- `parsers.py:87-88` — `"ErrorTraceData"` and `"ErrorCode"` in `TRACKED_EVENT_TYPES`
- No `mcs_schema.py` entry beyond the type name (properties vary by error)
- No mapping rule in `converter.py`

### Section 1 — Telemetry Attribute Matrix

Cross-reference of key telemetry attributes against MCS source availability and OTEL target mapping:

| Attribute | MCS Source | OTEL Target | Status | Notes |
|-----------|-----------|-------------|--------|-------|
| trace_id | Auto-generated from `conversation_id` | Span model (`trace_id`) | Available | MD5-based deterministic generation in `converter.py:143` |
| session_id / conversation_id | `conversation.id` from first activity | `gen_ai.conversation.id` | Available | Mapped via `session_root` rule |
| session_outcome | `trace.SessionInfo.outcome` | `copilot_studio.session_outcome` | Available | Mapped via `session_root` rule |
| agent_name | Bot `from.name` in first bot message | `gen_ai.agent.name` | Available | Mapped via `session_root` rule |
| agent_id | Bot `from.id` in first bot message | `gen_ai.agent.id` | Partial | Defined in registry, not mapped |
| user_message | `message.user.text` via `_extract_turns()` | `gen_ai.input.messages` | Available | Template transform wraps in JSON array |
| bot_response | `message.bot.text` via `_extract_turns()` | `gen_ai.output.messages` | Available | Template transform wraps in JSON array |
| topic_name | `DynamicPlanStepTriggered.taskDialogId` | `copilot_studio.topic_name` | Available | Mapped via `user_turn` rule |
| tool_name | `UniversalSearchToolTraceData.toolId` | `gen_ai.tool.name` | Available | Mapped via `knowledge_search` rule |
| tool_type | Constant `"datastore"` | `gen_ai.tool.type` | Available | Constant transform |
| plan_identifier | `DynamicPlanReceived.planIdentifier` | `copilot_studio.plan_identifier` | Available | Mapped via `dynamic_plan` rule |
| turn_count | `trace.SessionInfo.turnCount` | — | Partial | In MCS schema, no OTEL mapping |
| start_time | `trace.SessionInfo.startTimeUtc` | Span `start_time_ns` | Partial | Used for span timing, not as attribute |
| end_time | `trace.SessionInfo.endTimeUtc` | Span `end_time_ns` | Partial | Used for span timing, not as attribute |
| implied_success | `trace.SessionInfo.impliedSuccess` | — | Partial | In MCS schema, no OTEL mapping |
| outcome_reason | `trace.SessionInfo.outcomeReason` | — | Partial | In MCS schema, no OTEL mapping |
| user_id | `message.user.from.id` | — | Partial | In MCS schema, no OTEL mapping |
| aad_object_id | `message.user.from.aadObjectId` | — | Partial | In MCS schema, no OTEL mapping |
| channel_id | `message.user.channelId` | — | Partial | In MCS schema, no OTEL mapping |
| is_design_mode | `trace.ConversationInfo.isDesignMode` | — | Partial | In MCS schema, no OTEL mapping |
| locale | `trace.ConversationInfo.locale` | — | Partial | In MCS schema, no OTEL mapping |
| variable_name | `trace.VariableAssignment.name` | `copilot_studio.variable_name` | Partial | Both sides defined, no rule |
| variable_value | `trace.VariableAssignment.newValue` | `copilot_studio.variable_value` | Partial | Both sides defined, no rule |
| thought | `DynamicPlanStepTriggered.thought` | `copilot_studio.thought` | Partial | Both sides defined, no rule |
| execution_time | `DynamicPlanStepFinished.executionTime` | `copilot_studio.execution_time` | Partial | Both sides defined, no rule |
| step_id | `DynamicPlanStepTriggered.stepId` | `copilot_studio.step_id` | Partial | Both sides defined, no rule |
| step_type | `DynamicPlanStepTriggered.type` | `copilot_studio.step_type` | Partial | Both sides defined, no rule |
| task_dialog_id | `DynamicPlanStepTriggered.taskDialogId` | `copilot_studio.task_dialog_id` | Partial | Both sides defined, no rule |
| search_query | `DynamicPlanStepBindUpdate.arguments.search_query` | `gen_ai.retrieval.query.text` | Partial | Both sides defined, no rule |
| unknown_intent_query | `trace.UnknownIntent.userQuery` | — | Partial | In MCS schema, no OTEL target |
| skill_name | `trace.SkillInfo.skillName` | — | Partial | In MCS schema, no OTEL target |
| skill_id | `trace.SkillInfo.skillId` | — | Partial | In MCS schema, no OTEL target |
| input_tokens | — | `gen_ai.usage.input_tokens` | Gap | No MCS source |
| output_tokens | — | `gen_ai.usage.output_tokens` | Gap | No MCS source |
| request_model | — | `gen_ai.request.model` | Gap | No MCS source |
| response_id | — | `gen_ai.response.id` | Gap | No MCS source |
| system_instructions | — | `gen_ai.system_instructions` | Gap | No MCS source |
| temperature | — | `gen_ai.request.temperature` | Gap | No MCS source |
| max_tokens | — | `gen_ai.request.max_tokens` | Gap | No MCS source |

---

## Section 2: Correlation & Context Enrichment

### 2.1 Trace ID Propagation — Partial

**What works:** `converter.py:143` generates a deterministic `trace_id` from `conversation_id` via MD5 hashing. All spans within a conversation share the same trace ID.

**What's missing:** No W3C `traceparent` header propagation from MCS runtime. The trace ID is mapper-generated, not propagated from the original request chain. Cross-service correlation requires manual join on `conversation_id`.

**Evidence:**
- `converter.py:42-44` — `_md5_hex()` deterministic ID generation
- `converter.py:139-143` — trace_id derived from first entity's `conversation_id`

### 2.2 Span Parent-Child Hierarchy — Available

**What works:** Full parent-child span tree is built in Phase 2 of `apply_mapping()`. The hierarchy is:

```
invoke_agent (session_root)
├── chat turn:1 (user_turn)
│   ├── execute_tool search (knowledge_search)
│   └── chain plan (dynamic_plan)
├── chat turn:2 (user_turn)
│   └── ...
```

**Evidence:**
- `converter.py:202-226` — Phase 2 builds parent-child relationships using `parent_rule_id`
- `converter.py:243-247` — orphan spans attached to root
- `converter.py:249-256` — root span timing adjusted to cover all children
- Rule hierarchy: `session_root` ← `user_turn` ← `knowledge_search` / `dynamic_plan`

### 2.3 User Identity Context — Partial

**What exists:** `message.user.from.id` and `message.user.from.aadObjectId` are in the MCS schema.

**What's missing:** No OTEL attribute target defined. No mapping rule extracts user identity into spans.

**Evidence:**
- `mcs_schema.py:211-212` — `message.user.from.id`, `message.user.from.aadObjectId`

**Workaround:** Add a custom OTEL attribute (e.g., `enduser.id`) and a mapping rule targeting `message.user.from.aadObjectId`.

### 2.4 Channel/Environment Enrichment — Partial

**What exists:** `channelId` on both user and bot messages, plus `isDesignMode` flag in `ConversationInfo`.

**What's missing:** No OTEL target attributes defined. No mapping rules.

**Evidence:**
- `mcs_schema.py:210` — `message.user.channelId`
- `mcs_schema.py:42` — `trace.ConversationInfo.isDesignMode`

### 2.5 Decision Path / Reasoning — Partial

**What exists:** `DynamicPlanStepTriggered.thought` captures LLM chain-of-thought reasoning. `copilot_studio.thought` is defined as an OTEL target.

**What's missing:** No default mapping rule connects them. The `dynamic_plan` rule only maps `planIdentifier`.

**Evidence:**
- `mcs_schema.py:111` — `event.DynamicPlanStepTriggered.thought`
- `otel_registry.py:248-252` — `copilot_studio.thought` defined
- `converter.py:355-371` — `dynamic_plan` rule maps only `planIdentifier`

### 2.6 Temporal Ordering — Available

**What works:** Activities are sorted by timestamp in `_extract_turns()`. Spans receive `start_time_ns` and `end_time_ns` with nanosecond precision. Timestamp normalization handles seconds, milliseconds, microseconds, and ISO 8601 strings.

**Evidence:**
- `parsers.py:219` — `sorted(activities, key=lambda a: a.timestamp)`
- `converter.py:79-101` — `_extract_timestamps()` with nanosecond conversion
- `converter.py:104-116` — `_to_nanoseconds()` handles multiple timestamp formats

**ID propagation flow:**

```
MCS Transcript
  └─ conversation.id (from first activity)
       └─ MD5 hash → trace_id (32 hex chars)
            ├─ MD5(trace_id:rule_id:entity_id) → span_id (16 hex chars)
            └─ parent_span_id set via parent_rule_id linking
```

---

## Section 3: Storage, Indexing & Dashboards

### 3.1 OTLP Export Format — Available

**What works:** `converter.py` `to_otlp_json()` produces valid OTLP JSON with `resourceSpans` → `scopeSpans` → `spans` hierarchy. Includes `service.name` resource attribute, scope metadata, and all span attributes.

**Evidence:**
- `converter.py:400-428` — `to_otlp_json()` full OTLP serialization
- `converter.py:382-397` — `_span_to_otlp()` per-span serialization with traceId, spanId, parentSpanId, name, kind, timestamps, attributes, status

### 3.2 Application Insights Integration — Partial

**What works:** The OTLP JSON output is compatible with Azure Monitor's OTLP ingestion endpoint. Span attributes land in `customDimensions`.

**What's missing:** No built-in exporter. The OTLP JSON must be sent to App Insights via:
1. Manual HTTP POST to the OTLP endpoint
2. An OpenTelemetry Collector with Azure Monitor exporter
3. Direct SDK integration

**Workaround:** Use the Azure Monitor OpenTelemetry Distro or configure an OTEL Collector with the `azuremonitor` exporter.

### 3.3 Pre-Built Dashboards — Gap

No dashboard templates are included. Below are recommended KQL queries for building dashboards:

**Session health overview:**
```kql
traces
| where customDimensions["gen_ai.system"] == "copilot_studio"
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend outcome = tostring(customDimensions["copilot_studio.session_outcome"])
| summarize
    TotalSessions = count(),
    Resolved = countif(outcome == "Resolved"),
    Escalated = countif(outcome == "Escalated"),
    Abandoned = countif(outcome == "Abandoned")
    by bin(timestamp, 1d)
```

**Turn depth distribution:**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "chat"
| extend conversationId = tostring(customDimensions["gen_ai.conversation.id"])
| summarize TurnCount = count() by conversationId
| summarize avg(TurnCount), percentile(TurnCount, 50), percentile(TurnCount, 90), percentile(TurnCount, 99)
```

### 3.4 Retention Policy — Gap

**Why it's a gap:** Retention depends entirely on the downstream storage target. The mapper is stateless and does not persist data.

**Recommendations:**
- **Application Insights:** Default 90-day retention, configurable up to 730 days
- **Log Analytics workspace:** 30-day free retention, up to 730 days paid
- **Microsoft Sentinel:** Same as Log Analytics with additional long-term archive (up to 12 years)
- **Fabric lakehouse:** Unlimited retention via OneLake, manual lifecycle management

### 3.5 Search/Indexing Strategy — Gap

**Why it's a gap:** No indexing configuration is provided. Performance depends on downstream storage.

**Recommendations for App Insights / Log Analytics:**
- Index `customDimensions["gen_ai.conversation.id"]` for session lookups
- Index `customDimensions["gen_ai.operation.name"]` for operation filtering
- Index `customDimensions["copilot_studio.session_outcome"]` for outcome queries
- Use `summarize` with `dcount()` for high-cardinality fields

**Storage comparison:**

| Target | Strengths | Weaknesses | Best For |
|--------|-----------|------------|----------|
| Application Insights | Native OTLP, KQL, alerting | 730d max retention, cost at scale | Real-time monitoring |
| Log Analytics | Flexible schema, cross-workspace queries | Query cost at high volume | Operational analytics |
| Microsoft Sentinel | Security analytics, UEBA, incident management | Premium pricing | Security-focused observability |
| Fabric Lakehouse | Unlimited scale, SQL + Spark | No native OTLP ingestion | Long-term analytics, ML |

---

## Section 4: Alerts & Anomaly Detection

### 4.1 Session Outcome Alerting — Partial

**What exists:** `copilot_studio.session_outcome` is actively mapped. KQL can detect abandonment spikes.

**What's missing:** No pre-built alert rules. Requires manual configuration in Azure Monitor or Sentinel.

**KQL alert — Abandonment spike (>30% in 1 hour):**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| where timestamp > ago(1h)
| extend outcome = tostring(customDimensions["copilot_studio.session_outcome"])
| summarize
    Total = count(),
    Abandoned = countif(outcome == "Abandoned")
| extend AbandonRate = round(100.0 * Abandoned / Total, 1)
| where AbandonRate > 30
```

### 4.2 Error Rate Detection — Gap

**What exists:** `ErrorTraceData` and `ErrorCode` are tracked event types in `parsers.py:87-88`.

**Why it's a gap:** No mapping rule exists for error events. Error properties are not defined in the schema beyond the type name. No OTEL error attribute mapping.

**Workaround:** Add a mapping rule for `ErrorTraceData` → error span with `otel.status_code = ERROR` and `otel.status_description` from error properties.

### 4.3 Latency Anomaly Detection — Partial

**What exists:** `event.DynamicPlanStepFinished.executionTime` is in the MCS schema. `copilot_studio.execution_time` is defined in the OTEL registry.

**What's missing:** No mapping rule connects them. Without mapped execution times, latency-based alerting requires manual span duration calculation.

**KQL alert — Slow sessions (>30s span duration):**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "invoke_agent"
| extend startNs = tolong(customDimensions["startTimeUnixNano"])
| extend endNs = tolong(customDimensions["endTimeUnixNano"])
| extend durationMs = (endNs - startNs) / 1000000
| where durationMs > 30000
| project timestamp, customDimensions["gen_ai.conversation.id"], durationMs
```

### 4.4 Unknown Intent Spike — Partial

**What exists:** `trace.UnknownIntent.userQuery` captures unrecognized user queries in the MCS schema.

**What's missing:** No OTEL target attribute defined. No mapping rule. `UnknownIntent` is not in `TRACKED_EVENT_TYPES`.

**KQL alert — Unknown intent spike (>20% in 1 hour, requires mapping):**
```kql
traces
| where customDimensions["gen_ai.operation.name"] == "chat"
| where timestamp > ago(1h)
| extend hasUnknownIntent = isnotempty(customDimensions["copilot_studio.unknown_intent_query"])
| summarize
    Total = count(),
    Unknown = countif(hasUnknownIntent)
| extend UnknownRate = round(100.0 * Unknown / Total, 1)
| where UnknownRate > 20
```

### 4.5 Token Budget Exhaustion — Gap

**Why it's a gap:** No token data is available from MCS transcripts. Cannot alert on token consumption or budget limits.

**Evidence:** See capability 1.7.

---

## Section 5: Multi-Agent Observability

### 5.1 Cross-Agent Call Graphs — Gap

**Why it's a gap:** MCS conversation transcripts are single-agent scope. Each transcript represents one copilot's conversation. There is no inter-agent trace propagation or cross-agent span linking.

**Future direction:** The A2A (Agent-to-Agent) protocol and Microsoft Agents SDK support multi-agent communication. When MCS supports A2A, cross-agent trace context propagation would enable call graph construction.

### 5.2 Skill/Sub-Agent Invocation — Partial

**What exists:** `trace.SkillInfo` with `action`, `skillId`, and `skillName` is defined in the MCS schema.

**What's missing:** No OTEL target attributes for skill invocations. No mapping rule. Skills are essentially sub-agent calls within MCS.

**Evidence:**
- `mcs_schema.py:74-78` — `trace.SkillInfo.*`: action, skillId, skillName

**Workaround:** Add a mapping rule: `SkillInfo` → `execute_tool` span with `gen_ai.tool.name` = `skillName`.

### 5.3 Multi-Agent Failure Correlation — Gap

**Why it's a gap:** Single-agent transcript scope. Cannot correlate failures across copilots or between a copilot and its downstream skill agents.

### 5.4 System-Level Health — Gap

**Why it's a gap:** Requires aggregation across multiple copilot instances, environments, and channels. The mapper processes individual transcripts; fleet-level health monitoring requires a separate aggregation layer.

**Workaround:** Use Azure Monitor workbooks or Grafana dashboards to aggregate across multiple `gen_ai.agent.name` values:

```kql
traces
| where customDimensions["gen_ai.system"] == "copilot_studio"
| extend agentName = tostring(customDimensions["gen_ai.agent.name"])
| extend outcome = tostring(customDimensions["copilot_studio.session_outcome"])
| summarize
    Sessions = count(),
    SuccessRate = round(100.0 * countif(outcome == "Resolved") / count(), 1)
    by agentName
```

---

## Section 6: Governance, Compliance & Traceability

### 6.1 Full Conversation Provenance — Available

**What works:** The complete pipeline preserves all data: raw JSON transcript → parsed activities → typed entities → OTEL spans. No information is dropped during conversion. The OTLP JSON output contains the full span tree with all mapped attributes.

**Evidence:**
- `parsers.py:169-214` — `parse_transcript()` preserves all activities
- `parsers.py:261-310` — `extract_entities()` creates entities from all tracked event types
- `converter.py:134-274` — `apply_mapping()` builds complete trace tree

### 6.2 Audit Trail (Who/What/When) — Partial

**What exists:**
- **Who:** `message.user.from.id`, `message.user.from.aadObjectId` (user identity); bot identity via `from.name` and `from.id`
- **What:** Full message content, tool invocations, orchestrator plan steps
- **When:** Timestamps on all activities, span timing in nanoseconds

**What's missing:** User identity fields are not mapped to OTEL attributes. No formal audit event schema beyond the conversation content.

### 6.3 Decision Lineage / Replay — Partial

**What exists:** Orchestrator plan steps (`DynamicPlanReceived` → `DynamicPlanStepTriggered` → `DynamicPlanStepFinished`) provide partial decision lineage. The `thought` field captures LLM reasoning.

**What's missing:** No formal replay mechanism. Lineage is limited to what the orchestrator exposes — internal model reasoning, retrieval ranking decisions, and response generation logic are opaque.

### 6.4 Immutable Trace Records — Gap

**Why it's a gap:** The mapper itself is stateless and produces JSON output. Immutability depends on the downstream storage target:
- **App Insights:** Append-only by design (data cannot be modified after ingestion)
- **Log Analytics:** Same append-only model
- **Blob storage:** Immutable with WORM policies

### 6.5 Data Classification Labels — Gap

**Why it's a gap:** MCS transcripts do not expose Microsoft Information Protection (MIP) sensitivity labels or data classification metadata. The mapper cannot inject labels it doesn't have.

---

## Section 7: Privacy, Redaction & Responsible AI

### 7.1 PII Redaction Pipeline — Gap

**Why it's a gap:** The mapper passes raw message text through to `gen_ai.input.messages` and `gen_ai.output.messages` without any redaction. User messages may contain PII (names, emails, account numbers).

**Workaround:** Integrate [Microsoft Presidio](https://github.com/microsoft/presidio) as a pre-processing step before OTLP export. Presidio can detect and redact PII in message content:
- Apply to `gen_ai.input.messages` and `gen_ai.output.messages` attribute values
- Configure entity types: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, etc.

### 7.2 Content Safety Signals — Gap

**Why it's a gap:** MCS conversation transcripts do not include content safety or moderation signals. There are no events indicating blocked content, safety filter triggers, or content policy violations.

**Workaround:** Integrate [Azure AI Content Safety](https://learn.microsoft.com/azure/ai-services/content-safety/) as a parallel analysis pipeline on the message content.

### 7.3 Responsible AI Evaluation Loop — Gap

**Why it's a gap:** No feedback, evaluation, or quality scoring data exists in MCS transcripts. There are no thumbs-up/down signals, CSAT scores, or response quality metrics.

### 7.4 Data Residency Compliance — Gap

**Why it's a gap:** The mapper is a stateless processing tool — it does not persist or transmit data. Data residency compliance depends entirely on:
1. Where MCS transcript data is stored (Dataverse region)
2. Where the OTLP data is sent (App Insights / Log Analytics region)
3. Network transit configuration

### 7.5 Consent Tracking — Gap

**Why it's a gap:** MCS transcripts contain no consent signals, opt-in/opt-out indicators, or data subject access request (DSAR) identifiers.

---

## Appendix A: MCS Property Inventory

All 65 mappable properties from `mcs_schema.py`:

| # | Path | Type | Description |
|---|------|------|-------------|
| 1 | `trace.ConversationInfo.isDesignMode` | bool | Design mode flag |
| 2 | `trace.ConversationInfo.locale` | string | Conversation locale |
| 3 | `trace.VariableAssignment.name` | string | Variable display name |
| 4 | `trace.VariableAssignment.id` | string | Scoped variable ID |
| 5 | `trace.VariableAssignment.newValue` | string | New value |
| 6 | `trace.VariableAssignment.type` | string | Scope: global/local |
| 7 | `trace.DialogRedirect.targetDialogId` | string | Target dialog ID |
| 8 | `trace.DialogRedirect.targetDialogType` | int | Dialog type (0=system, 1=custom) |
| 9 | `trace.SessionInfo.startTimeUtc` | string | Start time (UTC) |
| 10 | `trace.SessionInfo.endTimeUtc` | string | End time (UTC) |
| 11 | `trace.SessionInfo.type` | string | Session type |
| 12 | `trace.SessionInfo.outcome` | string | Session outcome |
| 13 | `trace.SessionInfo.turnCount` | int | Turn count |
| 14 | `trace.SessionInfo.lastUserIntentId` | string | Last user intent |
| 15 | `trace.SessionInfo.impliedSuccess` | bool | Implied success |
| 16 | `trace.SessionInfo.outcomeReason` | string | Outcome reason |
| 17 | `trace.UnknownIntent.userQuery` | string | Unrecognized query |
| 18 | `trace.SkillInfo.action` | int | Action code |
| 19 | `trace.SkillInfo.skillId` | string | Skill ID |
| 20 | `trace.SkillInfo.skillName` | string | Skill name |
| 21 | `event.DynamicPlanReceived.steps` | array | Step IDs |
| 22 | `event.DynamicPlanReceived.isFinalPlan` | bool | Final plan flag |
| 23 | `event.DynamicPlanReceived.planIdentifier` | string | Plan ID |
| 24 | `event.DynamicPlanReceivedDebug.summary` | string | Plan summary |
| 25 | `event.DynamicPlanReceivedDebug.ask` | string | Plan ask |
| 26 | `event.DynamicPlanReceivedDebug.planIdentifier` | string | Plan ID |
| 27 | `event.DynamicPlanReceivedDebug.isFinalPlan` | bool | Final plan flag |
| 28 | `event.DynamicPlanStepTriggered.planIdentifier` | string | Plan ID |
| 29 | `event.DynamicPlanStepTriggered.stepId` | string | Step ID |
| 30 | `event.DynamicPlanStepTriggered.taskDialogId` | string | Task dialog ID |
| 31 | `event.DynamicPlanStepTriggered.thought` | string | LLM reasoning |
| 32 | `event.DynamicPlanStepTriggered.state` | int | Step state code |
| 33 | `event.DynamicPlanStepTriggered.hasRecommendations` | bool | Has recommendations |
| 34 | `event.DynamicPlanStepTriggered.type` | string | Step type (KnowledgeSource/CustomTopic) |
| 35 | `event.DynamicPlanStepBindUpdate.taskDialogId` | string | Task dialog ID |
| 36 | `event.DynamicPlanStepBindUpdate.stepId` | string | Step ID |
| 37 | `event.DynamicPlanStepBindUpdate.arguments.search_query` | string | Search query |
| 38 | `event.DynamicPlanStepBindUpdate.arguments.enable_summarization` | bool | Summarization flag |
| 39 | `event.DynamicPlanStepBindUpdate.arguments.search_keywords` | string | Search keywords |
| 40 | `event.DynamicPlanStepBindUpdate.planIdentifier` | string | Plan ID |
| 41 | `event.UniversalSearchToolTraceData.toolId` | string | Tool ID |
| 42 | `event.UniversalSearchToolTraceData.knowledgeSources` | array | Knowledge sources |
| 43 | `event.UniversalSearchToolTraceData.outputKnowledgeSources` | array | Output sources |
| 44 | `event.UniversalSearchToolTraceData.fullResults` | array | Full results |
| 45 | `event.UniversalSearchToolTraceData.filteredResults` | array | Filtered results |
| 46 | `event.DynamicPlanStepFinished.taskDialogId` | string | Task dialog ID |
| 47 | `event.DynamicPlanStepFinished.stepId` | string | Step ID |
| 48 | `event.DynamicPlanStepFinished.observation.search_result` | object | Search result |
| 49 | `event.DynamicPlanStepFinished.planUsedOutputs` | object | Plan used outputs |
| 50 | `event.DynamicPlanStepFinished.planIdentifier` | string | Plan ID |
| 51 | `event.DynamicPlanStepFinished.state` | string | Step state |
| 52 | `event.DynamicPlanStepFinished.hasRecommendations` | bool | Has recommendations |
| 53 | `event.DynamicPlanStepFinished.executionTime` | string | Execution time |
| 54 | `event.DynamicPlanFinished.planId` | string | Plan ID |
| 55 | `message.user.text` | string | Message text |
| 56 | `message.user.textFormat` | string | Text format |
| 57 | `message.user.channelId` | string | Channel ID |
| 58 | `message.user.from.id` | string | User ID |
| 59 | `message.user.from.aadObjectId` | string | AAD object ID |
| 60 | `message.bot.text` | string | Message text |
| 61 | `message.bot.textFormat` | string | Text format |
| 62 | `message.bot.channelId` | string | Channel ID |
| 63 | `message.bot.attachments` | array | Attachments |
| 64 | `invoke.signin.name` | string | Invoke name |
| 65 | `invokeResponse.status.status` | int | HTTP status |

---

## Appendix B: OTEL Attribute Inventory

All 40 attributes from `otel_registry.py`:

### General Attributes (3)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.operation.name` | string | Name of the GenAI operation (chat, invoke_agent, etc.) | required |
| `gen_ai.system` | string | GenAI system provider identifier | required |
| `gen_ai.provider.name` | string | Human-readable name of the GenAI provider | recommended |

### Agent Attributes (5)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.agent.name` | string | Name of the agent handling the request | recommended |
| `gen_ai.agent.id` | string | Unique identifier of the agent | recommended |
| `gen_ai.agent.description` | string | Description of the agent | recommended |
| `gen_ai.agent.version` | string | Version of the agent | recommended |
| `gen_ai.conversation.id` | string | Unique identifier for the conversation session | recommended |

### Usage Attributes (2)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.usage.input_tokens` | int | Number of input tokens consumed | recommended |
| `gen_ai.usage.output_tokens` | int | Number of output tokens generated | recommended |

### Tool Attributes (6)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.tool.name` | string | Name of the tool being invoked | recommended |
| `gen_ai.tool.type` | string | Type of tool (function, plugin, connector) | recommended |
| `gen_ai.tool.description` | string | Description of the tool | recommended |
| `gen_ai.tool.call.id` | string | Unique identifier for the tool call | recommended |
| `gen_ai.tool.call.arguments` | string | JSON-encoded arguments passed to the tool | recommended |
| `gen_ai.tool.call.result` | string | JSON-encoded result returned by the tool | recommended |

### Message Attributes (4)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.input.messages` | string | JSON-encoded input messages sent to the model | recommended |
| `gen_ai.output.messages` | string | JSON-encoded output messages from the model | recommended |
| `gen_ai.output.type` | string | Type of output (text, card, adaptive_card) | recommended |
| `gen_ai.system_instructions` | string | System prompt or instructions provided to the model | recommended |

### Request Attributes (3)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.request.model` | string | Model identifier used for the request | recommended |
| `gen_ai.request.temperature` | float | Temperature parameter for generation | recommended |
| `gen_ai.request.max_tokens` | int | Maximum number of tokens to generate | recommended |

### Response Attributes (2)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.response.id` | string | Unique identifier for the model response | recommended |
| `gen_ai.response.finish_reasons` | string[] | Reasons the model stopped generating | recommended |

### Retrieval Attributes (3)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `gen_ai.data_source.id` | string | Identifier of the data source searched | recommended |
| `gen_ai.retrieval.query.text` | string | Text of the retrieval query | recommended |
| `gen_ai.retrieval.documents` | string | JSON-encoded retrieved documents | recommended |

### MCS Custom Attributes (12)

| Key | Type | Description | Requirement |
|-----|------|-------------|-------------|
| `copilot_studio.topic_name` | string | Name of the Copilot Studio topic triggered | recommended |
| `copilot_studio.session_outcome` | string | Outcome of the session (resolved, escalated, abandoned) | recommended |
| `copilot_studio.action_type` | string | Type of action executed within a topic | recommended |
| `copilot_studio.plan_identifier` | string | Identifier for the orchestrator plan being executed | recommended |
| `copilot_studio.step_type` | string | Type of step within an orchestrator plan | recommended |
| `copilot_studio.thought` | string | Orchestrator reasoning or chain-of-thought content | recommended |
| `copilot_studio.execution_time` | string | Execution time of the step in milliseconds | recommended |
| `copilot_studio.variable_name` | string | Name of the variable being assigned | recommended |
| `copilot_studio.variable_value` | string | Value assigned to the variable | recommended |
| `copilot_studio.step_id` | string | Step identifier within an orchestrator plan | recommended |
| `copilot_studio.task_dialog_id` | string | Task dialog identifier for a plan step | recommended |
| `copilot_studio.knowledge_source_count` | int | Number of knowledge sources searched | recommended |

---

## Appendix C: Current Mapping Rules

4 rules with 9 attribute mappings from `converter.py` `generate_default_mapping()`:

### Rule 1: `session_root` — Session Root Span

| Property | Value |
|----------|-------|
| MCS entity type | `trace_event` |
| MCS value type | `SessionInfo` |
| OTEL operation | `invoke_agent` |
| Span kind | `CLIENT` |
| Span name template | `invoke_agent {bot_name}` |
| Is root | Yes |
| Parent rule | — |

**Attribute mappings (3):**

| MCS Property | OTEL Attribute | Transform |
|-------------|----------------|-----------|
| `outcome` | `copilot_studio.session_outcome` | direct |
| `bot_name` | `gen_ai.agent.name` | direct |
| `conversation_id` | `gen_ai.conversation.id` | direct |

### Rule 2: `user_turn` — User-Bot Turn

| Property | Value |
|----------|-------|
| MCS entity type | `turn` |
| MCS value type | — |
| OTEL operation | `chat` |
| Span kind | `INTERNAL` |
| Span name template | `chat turn:{turn_index}` |
| Is root | No |
| Parent rule | `session_root` |

**Attribute mappings (3):**

| MCS Property | OTEL Attribute | Transform |
|-------------|----------------|-----------|
| `user_msg` | `gen_ai.input.messages` | template: `[{"role":"user","content":"{value}"}]` |
| `bot_msg` | `gen_ai.output.messages` | template: `[{"role":"assistant","content":"{value}"}]` |
| `topic_name` | `copilot_studio.topic_name` | direct |

### Rule 3: `knowledge_search` — Knowledge Search

| Property | Value |
|----------|-------|
| MCS entity type | `trace_event` |
| MCS value type | `UniversalSearchToolTraceData` |
| OTEL operation | `execute_tool` |
| Span kind | `INTERNAL` |
| Span name template | `execute_tool search` |
| Is root | No |
| Parent rule | `user_turn` |

**Attribute mappings (2):**

| MCS Property | OTEL Attribute | Transform |
|-------------|----------------|-----------|
| `toolId` | `gen_ai.tool.name` | direct |
| _(empty)_ | `gen_ai.tool.type` | constant: `"datastore"` |

### Rule 4: `dynamic_plan` — Dynamic Plan

| Property | Value |
|----------|-------|
| MCS entity type | `trace_event` |
| MCS value type | `DynamicPlanReceived` |
| OTEL operation | `chain` |
| Span kind | `INTERNAL` |
| Span name template | `chain plan` |
| Is root | No |
| Parent rule | `user_turn` |

**Attribute mappings (1):**

| MCS Property | OTEL Attribute | Transform |
|-------------|----------------|-----------|
| `planIdentifier` | `copilot_studio.plan_identifier` | direct |
