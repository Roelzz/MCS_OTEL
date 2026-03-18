# How MCS-OTEL Works

MCS-OTEL converts Microsoft Copilot Studio conversation transcripts into OpenTelemetry (OTEL) traces. Every step — parsing, entity extraction, enrichment, rule matching, and OTLP export — is driven by a single JSON config file. For setup instructions, see the [README](../README.md).

---

## 1. Primer: MCS Transcripts

Microsoft Copilot Studio records every conversation as a **transcript** — a JSON array of **activities**. Each activity represents something that happened: a user message, a bot response, or an internal trace event (knowledge search, plan execution, error, etc.).

Activities have a `type` field (`message`, `trace`, or `event`) and trace/event activities carry a `valueType` identifying the specific event kind (e.g., `DynamicPlanReceived`, `ErrorTraceData`). The `value` field contains the event's payload — often deeply nested JSON.

```mermaid
erDiagram
    Transcript ||--o{ Activity : contains
    Activity {
        string id
        string type "message | trace | event"
        int timestamp
        string valueType "e.g. DynamicPlanReceived"
        object value "event payload"
        string text "message content"
        object from "sender (role + name)"
        string channelId "e.g. msteams"
        object channelData "tenant info etc."
        object conversation "conversation ID"
    }
    Activity ||--o| Value : carries
    Value {
        string varies "structure depends on valueType"
    }
```

Key activity types in a typical transcript:

| type | valueType | Meaning |
|------|-----------|---------|
| `message` | — | User or bot message with `text` content |
| `trace` | `SessionInfo` | Session metadata: outcome, duration, turn count |
| `trace` | `ConversationInfo` | Locale, design mode flag |
| `event` | `DynamicPlanReceived` | AI orchestrator created an execution plan |
| `event` | `DynamicPlanStepTriggered` | A plan step started executing |
| `event` | `DynamicPlanStepFinished` | A plan step completed with results |
| `trace` | `DialogRedirect` | Topic/dialog routing change |
| `trace` | `ErrorTraceData` | Error with code and message |
| `trace` | `UniversalSearchToolTraceData` | Knowledge base search results |
| `trace` | `DynamicServerInitialize` | MCP server connection established |

---

## 2. Primer: OpenTelemetry Traces

OpenTelemetry represents work as **spans** arranged in a tree. Each span has a name, start/end time, key-value attributes, and optionally child spans and events. A **trace** is the root of that tree.

The OTLP JSON wire format nests spans inside scope and resource containers:

```mermaid
flowchart TB
    subgraph OTLP["OTLP JSON"]
        RS["resourceSpans[0]"]
        subgraph Resource["resource"]
            SA["service.name = copilot-studio"]
            SDK["telemetry.sdk.name = mcs-otel-mapper"]
        end
        subgraph SS["scopeSpans[0]"]
            Scope["scope: mcs-otel-mapper v1.1"]
            subgraph Spans["spans[]"]
                S1["Span: invoke_agent Rex Bluebot"]
                S2["Span: chat turn:1"]
                S3["Span: chain plan"]
                S4["..."]
            end
        end
        RS --> Resource
        RS --> SS
    end

    style OTLP fill:#f5f5f5,stroke:#333
    style Resource fill:#e8f4e8,stroke:#4a90d9
    style Spans fill:#fff3e0,stroke:#e8a838
```

Each span carries:

| Field | Example |
|-------|---------|
| `traceId` | `a1b2c3d4...` (32 hex chars, shared across all spans) |
| `spanId` | `e5f6a7b8...` (16 hex chars, unique per span) |
| `parentSpanId` | Links child to parent |
| `name` | `"chat turn:1"` |
| `kind` | 1=INTERNAL, 2=SERVER, 3=CLIENT |
| `startTimeUnixNano` | Nanosecond precision timestamp |
| `endTimeUnixNano` | Nanosecond precision timestamp |
| `attributes[]` | `[{key: "gen_ai.agent.name", value: {stringValue: "Rex Bluebot"}}]` |
| `events[]` | Point-in-time annotations (errors, variable changes) |
| `status` | UNSET (0), OK (1), or ERROR (2) |

MCS-OTEL follows the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for attribute naming — `gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.tool.name`, etc.

---

## 3. High-Level Architecture

### Full Pipeline

```mermaid
flowchart LR
    Upload["Upload<br>JSON / CSV / YAML"]
    Parse["Parse<br>parsers.py"]
    Extract["Extract Entities<br>parsers.py"]
    Enrich["Enrich<br>parsers.py"]
    Map["Map to Spans<br>converter.py"]
    Export["OTLP JSON<br>converter.py"]
    Collector["Jaeger / Datadog<br>/ Azure Monitor"]

    Upload --> Parse --> Extract --> Enrich --> Map --> Export --> Collector

    style Upload fill:#4a90d9,color:white
    style Parse fill:#5ba85b,color:white
    style Extract fill:#5ba85b,color:white
    style Enrich fill:#5ba85b,color:white
    style Map fill:#e8a838,color:white
    style Export fill:#e8a838,color:white
    style Collector fill:#9b59b6,color:white
```

### Component Map

```mermaid
flowchart TB
    subgraph Config["Config"]
        CL["config_loader.py<br>(91 lines)"]
        DM["config/default_mapping.json<br>(2163 lines)"]
        CL --> DM
    end

    subgraph Core["Core Pipeline"]
        MO["models.py<br>(354 lines)"]
        PA["parsers.py<br>(727 lines)"]
        CO["converter.py<br>(439 lines)"]
        PA --> MO
        CO --> MO
    end

    subgraph Improvement["Improvement Engine"]
        AT["analyze_transcripts.py<br>(521 lines)"]
        IM["improve.py<br>(876 lines)"]
        AT --> PA
        IM --> AT
        IM --> CO
    end

    subgraph WebUI["Web UI (Reflex)"]
        WW["web/web.py<br>(95 lines)"]
        WC["web/components/<br>(12 files, ~2.6k lines)"]
        WS["web/state/<br>(4 mixins, ~1.7k lines)"]
        WW --> WC
        WW --> WS
        WS --> PA
        WS --> CO
    end

    DM --> PA
    DM --> CO

    style Config fill:#f0e6ff,stroke:#9b59b6
    style Core fill:#e8f4e8,stroke:#5ba85b
    style Improvement fill:#fff3e0,stroke:#e8a838
    style WebUI fill:#e3f2fd,stroke:#4a90d9
```

---

## 4. The Config System

`config/default_mapping.json` is the single source of truth. It drives parsing, enrichment, and mapping — no code changes needed to add support for new event types.

See: `config/default_mapping.json`, `config_loader.py`

### MappingSpecification Structure

```mermaid
erDiagram
    MappingSpecification ||--o{ EventMetadata : event_metadata
    MappingSpecification ||--o{ EnrichmentRule : enrichment_rules
    MappingSpecification ||--o{ SpanMappingRule : rules
    MappingSpecification ||--o{ SessionInfoExtraction : session_info_extraction
    MappingSpecification ||--o{ DerivedSessionField : derived_session_fields
    MappingSpecification ||--o{ ChangelogEntry : changelog

    MappingSpecification {
        string version "1.1"
        string name "MCS-to-OTEL GenAI Mapping"
        string service_name "copilot-studio"
        list error_event_names "error, error_code"
    }

    EventMetadata {
        string value_type "e.g. DynamicPlanReceived"
        bool tracked "include in extraction?"
        string label "human-readable name"
        string description "what this event means"
        string entity_type "trace_event"
        string default_output_type "span or event"
    }

    EnrichmentRule ||--o{ EnrichmentOp : derived_fields
    EnrichmentRule {
        string value_type "which event type to enrich"
    }
    EnrichmentOp {
        string target "output property name"
        string op "extract_path | len | join | ..."
        string source "dot-path to input data"
        string separator "for join ops"
        object condition "when to apply"
    }

    SpanMappingRule ||--o{ AttributeMapping : attribute_mappings
    SpanMappingRule {
        string rule_id "unique identifier"
        string mcs_entity_type "trace_event | turn"
        string mcs_value_type "e.g. DynamicPlanReceived"
        string otel_operation_name "e.g. chain"
        string otel_span_kind "CLIENT | INTERNAL"
        string span_name_template "e.g. chain plan"
        bool is_root "true for session_root only"
        string parent_rule_id "which rule is parent"
        string output_type "span or event"
    }

    AttributeMapping {
        string mcs_property "source property path"
        string otel_attribute "target OTEL attribute"
        string transform "direct | template | constant | lookup"
        string transform_value "for template/constant"
    }

    SessionInfoExtraction ||--o{ SessionInfoFieldMapping : field_mappings
    SessionInfoExtraction {
        string source_value_type "SessionInfo | ConversationInfo"
    }
    SessionInfoFieldMapping {
        string source_key "key in activity value"
        string target_key "key in session_info dict"
        string default "fallback value"
    }

    DerivedSessionField {
        string target_key "e.g. environment"
        object condition "field + equals check"
        string true_value "e.g. design"
        string false_value "e.g. production"
    }
```

The 6 sections of the config, in processing order:

| Section | Count | Purpose |
|---------|-------|---------|
| `event_metadata` | 28 entries | Declares which valueTypes to track during entity extraction |
| `session_info_extraction` | 2 entries | Maps SessionInfo/ConversationInfo fields to session properties |
| `derived_session_fields` | 1 entry | Computes `environment` from `is_design_mode` |
| `enrichment_rules` | 16 entries | Flattens nested data into mappable properties per value type |
| `rules` | 28 entries | Maps entities to OTEL spans/events with attribute transforms |
| `changelog` | 1 entry | Version history |

### Config Loading Flow

```mermaid
flowchart LR
    JSON["config/default_mapping.json"]
    Load["config_loader.py<br>load_default_mapping()"]
    Validate["Pydantic validation<br>MappingSpecification"]
    Parsers["parsers.py<br>event_metadata<br>enrichment_rules<br>session_info_extraction"]
    Converter["converter.py<br>rules<br>error_event_names"]

    JSON --> Load --> Validate
    Validate --> Parsers
    Validate --> Converter

    style JSON fill:#f0e6ff,stroke:#9b59b6
    style Validate fill:#e8f4e8,stroke:#5ba85b
```

---

## 5. Worked Example: The Transcript

The examples throughout the rest of this document use the `rex_teams_transcript.json` test fixture — a simplified 1-turn conversation with "Rex Bluebot" on Microsoft Teams.

See: `tests/fixtures/rex_teams_transcript.json`

The conversation flow:

```mermaid
sequenceDiagram
    participant U as User
    participant B as Rex Bluebot
    participant O as Orchestrator
    participant K as Knowledge Search

    Note over B: ConversationInfo (locale=en-US)
    B->>U: Hello! I'm Rex Bluebot. How can I help you today?
    U->>B: What is the refund policy?
    O->>O: DialogRedirect → topic.RefundPolicy
    O->>O: DynamicPlanReceived (1 step: search knowledge)
    O->>K: DynamicPlanStepTriggered (KnowledgeSearch)
    K-->>O: (search completes)
    O->>O: DynamicPlanFinished (not cancelled)
    B->>U: Our refund policy allows returns within 30 days of purchase.
    Note over B: SessionInfo (outcome=Resolved, type=Engaged)
```

The raw transcript contains 9 activities:
1. `ConversationInfo` trace — locale, not design mode
2. Bot greeting message — "Hello! I'm Rex Bluebot..."
3. User message — "What is the refund policy?"
4. `DialogRedirect` trace — routing to topic.RefundPolicy
5. `DynamicPlanReceived` event — plan with 1 step
6. `DynamicPlanStepTriggered` event — knowledge search step
7. `DynamicPlanFinished` event — plan completed
8. Bot response message — "Our refund policy allows returns within 30 days..."
9. `SessionInfo` trace — outcome Resolved, 1 turn

---

## 6. Stage 1: Parsing + Entity Extraction

See: `parsers.py`

### Input Formats

The parser handles 3 JSON structures:
1. **Bare array** — `[{activity}, {activity}, ...]`
2. **Wrapped object** — `{"activities": [...]}`
3. **Dataverse export** — `{"content": "{\"activities\": [...]}"}` (JSON-in-JSON from Dataverse CSV)

### Entity Extraction Flow

```mermaid
flowchart TB
    Raw["Raw JSON"]
    Resolve["_resolve_activities()<br>detect format"]
    Parse["_parse_activity()<br>per activity"]
    Typed["parse_activity_value()<br>SCHEMA_REGISTRY lookup"]

    subgraph Entities["3 Entity Types"]
        Root["session_root<br>(1 per transcript)"]
        Turns["turn entities<br>(1 per user message + greeting)"]
        Events["trace_event entities<br>(1 per tracked valueType)"]
    end

    Session["_extract_session_info()<br>config-driven field extraction"]
    TurnGroup["_extract_turns()<br>group by user messages"]
    Filter["event_metadata filter<br>only tracked=true types"]
    Enrich["apply_enrichment_rules()<br>flatten nested data"]

    Raw --> Resolve --> Parse --> Typed
    Typed --> Session --> Root
    Typed --> TurnGroup --> Turns
    Typed --> Filter --> Enrich --> Events

    style Root fill:#4a90d9,color:white
    style Turns fill:#5ba85b,color:white
    style Events fill:#e8a838,color:white
```

### Turn Grouping

```mermaid
flowchart TB
    Sorted["Sort activities by timestamp"]
    FindUser["Find all user message indices"]
    T0{"Bot messages before<br>first user message?"}
    Turn0["Turn 0 (greeting)<br>bot_msg only"]
    TurnN["Turn N<br>user_msg + last bot_msg in range"]
    Scan["For each user message:<br>collect activities until next user message"]
    Topic["Extract topic from<br>DynamicPlanStepTriggered"]

    Sorted --> FindUser --> T0
    T0 -->|yes| Turn0
    T0 -->|no| Scan
    Turn0 --> Scan
    Scan --> TurnN
    Scan --> Topic

    style Turn0 fill:#5ba85b,color:white
    style TurnN fill:#5ba85b,color:white
```

Turn 0 captures the bot's greeting before any user interaction. Subsequent turns are bounded by consecutive user messages — all bot messages and trace events between two user messages belong to the same turn.

### Worked Example: Entities Produced

From the Rex Bluebot transcript (9 activities → 7 entities):

| # | entity_id | entity_type | value_type | Key Properties |
|---|-----------|-------------|------------|----------------|
| 1 | `session_root` | `trace_event` | `SessionInfo` | outcome=Resolved, bot_name=Rex Bluebot, channel=msteams |
| 2 | `turn_0` | `turn` | — | bot_msg="Hello! I'm Rex Bluebot...", is_greeting=true |
| 3 | `turn_1` | `turn` | — | user_msg="What is the refund policy?", bot_msg="Our refund policy..." |
| 4 | `trace_DialogRedirect_0` | `trace_event` | `DialogRedirect` | targetDialogId=topic.RefundPolicy |
| 5 | `trace_DynamicPlanReceived_0` | `trace_event` | `DynamicPlanReceived` | step_count=1, is_final_plan=False |
| 6 | `trace_DynamicPlanStepTriggered_0` | `trace_event` | `DynamicPlanStepTriggered` | taskDialogId=P:UniversalSearchTool, type=KnowledgeSearch |
| 7 | `trace_DynamicPlanFinished_0` | `trace_event` | `DynamicPlanFinished` | was_cancelled=False |

Note: `ConversationInfo` data is absorbed into `session_root` via `session_info_extraction` rather than creating a separate entity. Entity #5 has enriched properties (`step_count`, `is_final_plan`) that were flattened from the nested `value` field during extraction.

### 6.1 Value Models (SCHEMA_REGISTRY)

Each known `valueType` has a Pydantic model in `models.py` that validates and types the raw `value` dict. This catches malformed data early and provides IDE autocomplete.

See: `models.py` lines 38-199

The pattern:

```
Activity with valueType="SessionInfo" →
  SCHEMA_REGISTRY["SessionInfo"] →
    SessionInfoValue model →
      validated, typed dict
```

| valueType | Model Class | Key Fields |
|-----------|-------------|------------|
| `SessionInfo` | `SessionInfoValue` | outcome, type, startTimeUtc, endTimeUtc, turnCount, outcomeReason, impliedSuccess |
| `IntentRecognition` | `IntentRecognitionValue` | intentName, intentId, score, userMessage |
| `ConversationInfo` | `ConversationInfoValue` | isDesignMode, locale |
| `DynamicPlanReceived` | `DynamicPlanReceivedValue` | steps, isFinalPlan, planIdentifier, toolDefinitions |
| `DynamicPlanStepTriggered` | `DynamicPlanStepTriggeredValue` | planIdentifier, stepId, taskDialogId, thought, type |
| `DynamicPlanFinished` | `DynamicPlanFinishedValue` | planId, wasCancelled |
| `DialogRedirect` | `DialogRedirectValue` | targetDialogId, targetDialogName, sourceDialogId |
| `VariableAssignment` | `VariableAssignmentValue` | name, value, type |
| `ErrorTraceData` | `ErrorTraceDataValue` | isUserError, errorCode, errorMessage |
| `UnknownIntent` | `UnknownIntentValue` | userQuery |
| `KnowledgeTraceData` | `KnowledgeTraceDataValue` | completionState, isKnowledgeSearched, citedKnowledgeSources |
| `GPTAnswer` | `GPTAnswerValue` | gptAnswerState |
| `CSATSurveyResponse` | `CSATSurveyResponseValue` | score, comment |
| `PRRSurveyResponse` | `PRRSurveyResponseValue` | response |
| `EscalationRequested` | `EscalationRequestedValue` | escalationRequestType |
| `HandOff` | `HandOffValue` | (extra="allow") |
| `ImpliedSuccess` | `ImpliedSuccessValue` | dialogId |
| `nodeTraceData` | `NodeTraceDataValue` | nodeID, nodeType, startTime, endTime, topicDisplayName |

All models use `ConfigDict(extra="allow")` so unknown fields pass through without error.

---

## 7. Stage 2: Enrichment System

See: `parsers.py` lines 474-669

### Why Enrichment Exists

MCS trace events often bury useful data inside nested structures. A `DynamicPlanStepFinished` event might have search results at `observation.search_result.search_results[0].Name` — three levels deep. Mapping rules can only read flat, top-level properties. Enrichment bridges this gap by extracting, counting, joining, and flattening nested data into simple string properties.

### Enrichment Pipeline

```mermaid
flowchart LR
    Entity["Entity with<br>nested properties"]
    Match{"Match enrichment rule<br>by value_type"}
    Loop["For each EnrichmentOp<br>in derived_fields"]
    Check{"Condition<br>met?"}
    Apply["Apply op:<br>extract / len / join / ..."]
    Skip["Skip op"]
    Done["Enriched entity<br>with flat properties"]

    Entity --> Match
    Match -->|found| Loop
    Match -->|no match| Done
    Loop --> Check
    Check -->|yes| Apply --> Loop
    Check -->|no| Skip --> Loop
    Loop -->|all ops done| Done

    style Entity fill:#e8a838,color:white
    style Done fill:#5ba85b,color:white
```

### Condition Types

```mermaid
stateDiagram-v2
    [*] --> CheckCondition
    CheckCondition --> if_isinstance: type check
    CheckCondition --> if_not_empty: value present?
    CheckCondition --> if_not_none: not None?
    CheckCondition --> prefix: string starts with?
    CheckCondition --> unconditional: no condition

    if_isinstance --> Pass: isinstance(val, dict/list/str)
    if_isinstance --> Fail: wrong type

    if_not_empty --> Pass: truthy value
    if_not_empty --> Fail: empty/falsy

    if_not_none --> Pass: value is not None
    if_not_none --> Fail: value is None

    prefix --> Pass: val.startswith(prefix)
    prefix --> Fail: no match

    unconditional --> Pass: always

    Pass --> ApplyOp
    Fail --> SkipOp
```

### Enrichment Operations

| Op | What it does | Input example | Output example |
|----|-------------|---------------|----------------|
| `extract_path` | Dot-path traversal into nested dicts | `observation.search_result.search_results` → `[{Name: "Policy.docx"}]` | `"[{'Name': 'Policy.docx'}]"` |
| `len` | Count list items | `steps` → `["P:SearchTool", "P:Topic1"]` | `"2"` |
| `join` | Join list with separator, supports `[*].field` | `actions[*].actionType` → `["Send", "Condition"]` | `"Send, Condition"` |
| `join_unique_sorted` | Dedupe + sort + join | `results[*].Type` → `["SharePoint", "Web", "SharePoint"]` | `"SharePoint, Web"` |
| `json_dump` | Serialize sub-object to JSON string | `observation` → `{content: [...]}` | `'{"content": [...]}'` |
| `str_coerce` | `str(value)` — coerce to string | `isFinalPlan` → `False` | `"False"` |
| `rename` | Copy value under a new key | `dialogSchemaName` → `"schema_v1"` | props[`mcp_dialog_schema`] = `"schema_v1"` |
| `conditional` | Apply only if prefix matches, optional extract | `taskDialogId` = `"MCP:myTool"` with `extract=split_last_colon` | `"myTool"` |

### Worked Example: DynamicPlanReceived Enrichment

Before enrichment:
```
{
  "steps": ["P:UniversalSearchTool"],
  "isFinalPlan": false,
  "planIdentifier": "plan-id-001",
  "timestamp": 1771240863
}
```

Enrichment rule applies 3 ops:
1. `len` on `steps` → `step_count = "1"`
2. `str_coerce` on `isFinalPlan` → `is_final_plan = "False"`
3. `len` on `toolDefinitions` → (null, skipped)

After enrichment:
```
{
  "steps": ["P:UniversalSearchTool"],
  "isFinalPlan": false,
  "planIdentifier": "plan-id-001",
  "timestamp": 1771240863,
  "step_count": "1",
  "is_final_plan": "False"
}
```

The enriched `step_count` and `is_final_plan` properties are now flat strings that mapping rules can directly reference.

---

## 8. Stage 3: Rule Matching + Span Building

See: `converter.py`

### The 5-Phase Algorithm

```mermaid
flowchart TB
    P1["Phase 1: Match Rules<br>For each rule, find matching entities.<br>Create spans or queue events."]
    P2["Phase 2: Build Tree<br>Link child spans to parents<br>via parent_rule_id."]
    P3["Phase 3: Find Root<br>Locate the is_root=true span.<br>Attach orphans as children."]
    P4["Phase 4: Attach Events<br>Place queued events on their<br>parent spans."]
    P5["Phase 5: Error Status<br>Mark parent spans as ERROR<br>when they contain error events."]

    P1 --> P2 --> P3 --> P4 --> P5

    style P1 fill:#4a90d9,color:white
    style P2 fill:#4a90d9,color:white
    style P3 fill:#4a90d9,color:white
    style P4 fill:#e8a838,color:white
    style P5 fill:#e74c3c,color:white
```

**Phase 1** iterates all 28 rules. For each rule, it finds entities matching `mcs_entity_type` + `mcs_value_type`. Matched entities produce either a span (added to the tree) or a pending event (queued for Phase 4). Span names are built from templates like `"chat turn:{turn_index}"` using entity properties.

**Phase 2** walks rules with a `parent_rule_id`. For each child span, it finds the best parent span (closest by timestamp) from the parent rule's span list and sets `parent_span_id`.

**Phase 3** finds the root span (the one rule with `is_root: true`). Any spans without a parent get adopted as children of the root. Root timing is adjusted to cover all children.

**Phase 4** attaches queued events to their parent spans (or root if no parent specified).

**Phase 5** checks if any error events (names in `error_event_names`) were attached. If so, the parent span gets `status: ERROR`.

### The 28-Rule Tree

This is the complete rule hierarchy from `config/default_mapping.json`. Blue nodes are spans, orange nodes are events.

```mermaid
flowchart TB
    classDef spanNode fill:#4a90d9,color:white,stroke:#2c6faa
    classDef eventNode fill:#e8a838,color:white,stroke:#c4882a
    classDef rootNode fill:#2c6faa,color:white,stroke:#1a4a7a,stroke-width:3px

    SR["session_root<br>invoke_agent {bot_name}<br>CLIENT, root"]:::rootNode

    UT["user_turn<br>chat turn:{N}<br>CLIENT"]:::spanNode
    CSAT["csat_response<br>(event)"]:::eventNode
    PRR["prr_response<br>(event)"]:::eventNode
    IS["implied_success<br>(event)"]:::eventNode
    ESC["escalation<br>(event)"]:::eventNode
    HO["handoff<br>(event)"]:::eventNode

    SR --> UT
    SR --> CSAT
    SR --> PRR
    SR --> IS
    SR --> ESC
    SR --> HO

    KS["knowledge_search<br>knowledge.retrieval<br>CLIENT"]:::spanNode
    DP["dynamic_plan<br>chain plan<br>INTERNAL"]:::spanNode
    TC["topic_classification<br>dialog_redirect<br>INTERNAL"]:::spanNode
    MCI["mcp_server_init<br>create_agent mcp_init<br>INTERNAL"]:::spanNode
    MCT["mcp_tools_list<br>create_agent mcp_tools<br>INTERNAL"]:::spanNode
    DT["dialog_tracing<br>chain dialog_trace<br>INTERNAL"]:::spanNode
    PI["protocol_info<br>chain protocol_info<br>INTERNAL"]:::spanNode
    SI["skill_info<br>create_agent skill_info<br>INTERNAL"]:::spanNode
    AB["ai_builder_trace<br>execute_tool ai_builder<br>INTERNAL"]:::spanNode
    BLK["dynamic_plan_step_blocked<br>blocked_step<br>INTERNAL"]:::spanNode
    KTD["knowledge_trace_data<br>knowledge.trace.data<br>INTERNAL"]:::spanNode
    ET["error_trace<br>(event)"]:::eventNode
    EC["error_code<br>(event)"]:::eventNode
    VA["variable_assignment<br>(event)"]:::eventNode
    UI["unknown_intent<br>(event)"]:::eventNode

    UT --> KS
    UT --> DP
    UT --> TC
    UT --> MCI
    UT --> MCT
    UT --> DT
    UT --> PI
    UT --> SI
    UT --> AB
    UT --> BLK
    UT --> KTD
    UT --> ET
    UT --> EC
    UT --> VA
    UT --> UI

    PSB["plan_step_bind<br>chain bind:{tool}<br>INTERNAL"]:::spanNode
    PSF["plan_step_finished<br>execute_tool {tool}<br>CLIENT"]:::spanNode
    PF["plan_finished<br>chain plan_finished<br>INTERNAL"]:::spanNode
    PST["plan_step_triggered<br>chain step:{tool}<br>INTERNAL"]:::spanNode
    PRD["plan_received_debug<br>chain plan_debug<br>INTERNAL"]:::spanNode

    DP --> PSB
    DP --> PSF
    DP --> PF
    DP --> PST
    DP --> PRD

    MCIC["mcp_server_init_confirmation<br>create_agent mcp_init_confirm<br>INTERNAL"]:::spanNode

    MCI --> MCIC
```

Summary: **19 span rules** + **9 event rules** = **28 total rules**.

| Parent | Child Spans | Child Events |
|--------|-------------|--------------|
| `session_root` | `user_turn` | `csat_response`, `prr_response`, `implied_success`, `escalation`, `handoff` |
| `user_turn` | `knowledge_search`, `dynamic_plan`, `topic_classification`, `mcp_server_init`, `mcp_tools_list`, `dialog_tracing`, `protocol_info`, `skill_info`, `ai_builder_trace`, `dynamic_plan_step_blocked`, `knowledge_trace_data` | `error_trace`, `error_code`, `variable_assignment`, `unknown_intent` |
| `dynamic_plan` | `plan_step_bind`, `plan_step_finished`, `plan_finished`, `plan_step_triggered`, `plan_received_debug` | — |
| `mcp_server_init` | `mcp_server_init_confirmation` | — |

### Single Rule Match Logic

```mermaid
flowchart TB
    Entity["Entity"]
    CheckType{"entity_type ==<br>rule.mcs_entity_type?"}
    CheckVT{"value_type ==<br>rule.mcs_value_type?<br>(or label matches)"}
    NoVT{"rule has<br>mcs_value_type?"}
    BuildName["Build span name<br>from template"]
    BuildAttrs["Apply attribute<br>mappings"]
    IsEvent{"output_type<br>== event?"}
    QueueEvent["Queue as<br>pending event"]
    CreateSpan["Create OTELSpan"]
    NoMatch["Skip"]

    Entity --> CheckType
    CheckType -->|no| NoMatch
    CheckType -->|yes| NoVT
    NoVT -->|no, match all| BuildName
    NoVT -->|yes| CheckVT
    CheckVT -->|no| NoMatch
    CheckVT -->|yes| BuildName
    BuildName --> BuildAttrs --> IsEvent
    IsEvent -->|yes| QueueEvent
    IsEvent -->|no| CreateSpan

    style CreateSpan fill:#4a90d9,color:white
    style QueueEvent fill:#e8a838,color:white
    style NoMatch fill:#ccc,color:#333
```

### 8.1 Transform Types

See: `converter.py` lines 54-67

| Transform | What it does | MCS value | transform_value | Output |
|-----------|-------------|-----------|-----------------|--------|
| `direct` | Pass through as-is | `"Resolved"` | — | `"Resolved"` |
| `template` | String substitution | `"What is refund?"` | `[{{"role":"user","content":"{value}"}}]` | `[{"role":"user","content":"What is refund?"}]` |
| `constant` | Ignore input, use fixed value | (any) | `"copilot_studio"` | `"copilot_studio"` |
| `lookup` | Same as direct (reserved for future use) | `"en-US"` | — | `"en-US"` |

---

## 9. Stage 4: OTLP Export

See: `converter.py` lines 330-439

After the span tree is built, `to_otlp_json()` serializes it into the OTLP JSON format:

1. **Flatten** the span tree depth-first into a flat list
2. **Wrap** in `resourceSpans → scopeSpans → spans[]` structure
3. **Convert** each span's attributes to typed OTLP values (`stringValue`, `intValue`, `boolValue`, `doubleValue`)
4. **Serialize** events with their attributes and nanosecond timestamps

### OTLP Output Structure (Worked Example)

```mermaid
flowchart TB
    subgraph OTLP["resourceSpans[0]"]
        subgraph Res["resource"]
            SN["service.name = Rex Bluebot"]
            SDKN["telemetry.sdk.name = mcs-otel-mapper"]
        end
        subgraph Scope["scopeSpans[0] / scope: mcs-otel-mapper v1.1"]
            S1["invoke_agent Rex Bluebot<br>kind=CLIENT, trace_id=a1b2.."]
            S2["chat turn:0<br>kind=CLIENT, parent=S1"]
            S3["chat turn:1<br>kind=CLIENT, parent=S1"]
            S4["dialog_redirect<br>kind=INTERNAL, parent=S3"]
            S5["chain plan<br>kind=INTERNAL, parent=S3"]
            S6["chain step:P:UniversalSearchTool<br>kind=INTERNAL, parent=S5"]
            S7["chain plan_finished<br>kind=INTERNAL, parent=S5"]
        end
    end

    S1 --> S2
    S1 --> S3
    S3 --> S4
    S3 --> S5
    S5 --> S6
    S5 --> S7

    style OTLP fill:#f5f5f5,stroke:#333
    style Res fill:#e8f4e8,stroke:#5ba85b
    style Scope fill:#fff3e0,stroke:#e8a838
```

The `service.name` is set to the bot name when available (from `botContent.yml` or the transcript's first bot message), falling back to `"copilot-studio"`.

---

## 10. The Improvement Engine

See: `improve.py`, `analyze_transcripts.py`

The improvement engine is a self-learning loop that analyzes real transcripts to find gaps in the mapping config and iteratively fixes them.

### Improvement Loop

```mermaid
flowchart TB
    Start["Load current<br>default_mapping.json"]
    Analyze["Analyze corpus<br>(all transcripts)"]
    Measure["Measure coverage %<br>and fill rate %"]
    Classify["Classify findings:<br>new_type | new_attribute | new_enrichment"]
    Split{"Auto-fixable?"}
    Auto["Auto-fix:<br>add EventMetadata +<br>SpanMappingRule"]
    Review["Needs review:<br>complex nested types"]
    Check{"Converged?<br>no fixes or < 0.1% gain"}
    Save["Save proposed_mapping.json"]
    Approve["User: review diff<br>then approve"]

    Start --> Analyze --> Measure --> Classify --> Split
    Split -->|">= 3 files| Auto
    Split -->|"< 3 files or nested"| Review
    Auto --> Check
    Review --> Check
    Check -->|no| Analyze
    Check -->|yes| Save --> Approve

    style Start fill:#4a90d9,color:white
    style Auto fill:#5ba85b,color:white
    style Review fill:#e8a838,color:white
    style Save fill:#9b59b6,color:white
```

### Finding Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Detected: corpus analysis

    Detected --> AutoFixed: auto_fixable=true, >= min_file_count
    Detected --> NeedsReview: auto_fixable=false or nested

    AutoFixed --> Applied: next iteration uses updated spec
    NeedsReview --> Applied: human approves
    NeedsReview --> Rejected: human rejects

    Applied --> [*]: coverage improved
    Rejected --> [*]: finding discarded
```

Finding categories:

| Category | Auto-fixable? | What it means |
|----------|---------------|---------------|
| `new_type` | Yes (if >= 3 files) | Unknown valueType found — add EventMetadata + SpanMappingRule |
| `new_attribute` | Yes | Property on a tracked type has no AttributeMapping — add one |
| `new_enrichment` | No | Type has nested structures — needs manual enrichment rules |

The CLI workflow:
1. `uv run python improve.py run /path/to/transcripts/`
2. `uv run python improve.py diff` — see what changed
3. `uv run python improve.py approve` — apply with version bump

---

## 11. The Web UI

See: `web/web.py`, `web/components/`, `web/state/`

The Reflex app provides a visual interface for the full pipeline.

### UI Structure

```mermaid
flowchart TB
    subgraph App["Reflex App (port 3000)"]
        subgraph Index["/ (Index Page)"]
            OV["Overview Tab<br>Upload → Connection → Mapping Editor → Span Tree → Export"]
            SE["Session Tab<br>Session Dashboard + Conversation View"]
            EN["Entities Tab<br>Entity Browser"]
            RG["Rule Graph Tab<br>Rule Hierarchy (React Flow)"]
            RE["Registry Tab<br>Event Registry"]
        end
        IMP["/improve<br>Improvement Dashboard"]
    end

    style App fill:#f5f5f5,stroke:#333
    style Index fill:#e3f2fd,stroke:#4a90d9
    style IMP fill:#fff3e0,stroke:#e8a838
```

### State Mixins

The app state is composed from 4 mixins that handle different concerns:

| Mixin | File | Manages |
|-------|------|---------|
| `UploadMixin` | `web/state/_upload.py` (224 lines) | File upload, transcript parsing, botContent parsing, entity extraction |
| `MappingMixin` | `web/state/_mapping.py` (794 lines) | Mapping editor state, rule CRUD, React Flow node/edge generation, OTLP export |
| `PreviewMixin` | `web/state/_preview.py` (339 lines) | Span tree rendering, entity browsing, session dashboard data, conversation view |
| `ImproveMixin` | `web/state/_improve.py` (330 lines) | Improvement engine UI, run management, finding review, proposed mapping diff |

These compose into a single `State` class:

```python
class State(UploadMixin, MappingMixin, PreviewMixin, ImproveMixin, rx.State):
    pass
```

---

## 12. Source File Reference

### Core Pipeline

| File | Lines | Role |
|------|-------|------|
| `models.py` | 354 | All Pydantic models: MCS input types, OTEL output types, mapping specification |
| `parsers.py` | 727 | Transcript parsing, entity extraction, enrichment ops, turn grouping, botContent parsing |
| `converter.py` | 439 | 5-phase rule matching, span tree building, OTLP JSON serialization |
| `config_loader.py` | 91 | Load and validate `config/default_mapping.json` into `MappingSpecification` |
| `config/default_mapping.json` | 2163 | Single source of truth: 27 event types, 16 enrichment rules, 28 mapping rules |
| `otel_registry.py` | 32 | OTEL attribute definitions (the output vocabulary) |
| `log.py` | 10 | Loguru logger setup |
| `utils.py` | 8 | Utility functions (`to_snake_case`) |

### Improvement Engine

| File | Lines | Role |
|------|-------|------|
| `analyze_transcripts.py` | 521 | Corpus analysis, coverage measurement, gap detection, report generation |
| `improve.py` | 876 | Self-learning loop, finding classification, auto-fix, diff, approve CLI |

### Web UI

| File | Lines | Role |
|------|-------|------|
| `main.py` | 1 | Reflex app entry point |
| `rxconfig.py` | 21 | Reflex configuration |
| `web/web.py` | 95 | Page layout, tab structure, routing |
| `web/state/__init__.py` | 12 | State composition from 4 mixins |
| `web/state/_upload.py` | 224 | Upload handling, parsing, entity extraction |
| `web/state/_mapping.py` | 794 | Mapping editor, React Flow, OTLP export |
| `web/state/_preview.py` | 339 | Span tree, entity browser, session dashboard |
| `web/state/_improve.py` | 330 | Improvement engine dashboard |
| `web/components/` | ~2,600 | 12 UI component files (upload, mapping editor, span tree, etc.) |

### Tests

| File | Role |
|------|------|
| `tests/fixtures/rex_teams_transcript.json` | Simple 1-turn Teams transcript (used in worked examples) |
| `tests/fixtures/pva_studio_transcript.json` | Multi-turn Studio transcript |
| `tests/fixtures/zava_expense_transcript.json` | Complex expense-reporting transcript |
| `tests/fixtures/zava_bot_content.yml` | Sample botContent.yml metadata |
| `tests/fixtures/sample_dataverse.csv` | Dataverse CSV export format |

---

## Glossary

| Term | Meaning |
|------|---------|
| **Activity** | A single event in a Copilot Studio transcript (message, trace, or event) |
| **Attribute** | A key-value pair on an OTEL span (e.g., `mcs.session.outcome: "Resolved"`) |
| **Copilot Studio** | Microsoft's platform for building AI chatbots (formerly Power Virtual Agents) |
| **Dataverse** | Microsoft's data platform where Copilot Studio stores conversation transcripts |
| **Enrichment** | Flattening nested JSON structures into simple key-value properties for mapping |
| **Entity** | A normalized version of a transcript activity, ready for rule matching |
| **Event (OTEL)** | A point-in-time annotation on a span (no duration), used for errors and variable changes |
| **Mapping rule** | Instructions for converting one type of MCS entity into an OTEL span or event |
| **MCP** | Model Context Protocol — a standard for connecting AI agents to external tools |
| **OTEL** | OpenTelemetry — an open standard for collecting observability data |
| **OTLP** | OpenTelemetry Protocol — the JSON wire format for sending trace data to collectors |
| **Span** | A unit of work in a trace, with name, timing, attributes, and parent-child relationships |
| **Trace** | A tree of spans representing an entire conversation session |
| **Transcript** | The raw conversation log exported from Copilot Studio |
| **Turn** | One user message + the bot's response (a back-and-forth exchange) |
| **valueType** | The identifier for what kind of trace event an activity represents |
