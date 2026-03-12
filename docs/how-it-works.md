# How MCS-OTEL Works

## What is this?

MCS-OTEL takes the conversation logs that Microsoft Copilot Studio produces and converts them into a standard observability format called OpenTelemetry (OTEL). Think of it as a translator: Copilot Studio speaks one language (its own internal transcript format), and monitoring tools like Jaeger, Datadog, or Azure Monitor speak another (OTEL). This project bridges the gap so you can actually see what your chatbot is doing under the hood.

## The problem

Microsoft Copilot Studio is a platform for building AI chatbots. When users talk to your bot, Copilot Studio records everything that happened in a **transcript** — a detailed log of the conversation. The problem? These transcripts are a wall of raw JSON. There's no built-in way to:

- See how long each step took
- Understand why the bot chose a particular answer
- Track which knowledge sources were searched
- Spot errors buried in nested data
- Compare performance across conversations

Observability tools solve exactly this — but they expect data in OTEL format. Copilot Studio doesn't export OTEL. So we built the translator.

## The big picture

```
                        MCS-OTEL Pipeline
                        =================

  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  Copilot      │     │              │     │              │
  │  Studio       │────>│   Parse &    │────>│   Map to     │
  │  Transcript   │     │   Extract    │     │   OTEL Spans │
  │  (JSON/CSV)   │     │   Entities   │     │              │
  └──────────────┘     └──────────────┘     └──────┬───────┘
                                                    │
                                                    v
                                            ┌──────────────┐
                                            │  OTLP JSON   │
                                            │  (ready for  │
                                            │  Jaeger etc.) │
                                            └──────────────┘
```

The pipeline has three stages:

1. **Parse** — Read the raw transcript JSON and break it into individual activities
2. **Extract** — Turn activities into clean, normalized entities with flattened properties
3. **Map** — Apply translation rules to convert entities into OTEL spans arranged in a tree

## Key concepts explained

### Transcript

The raw conversation log from Copilot Studio. It's a JSON array of **activities** — every message, every internal event, every trace. A single conversation might produce 20-100 activities depending on complexity.

Here's a simplified snippet from a real transcript:

```json
[
  {
    "type": "message",
    "timestamp": 1771240860,
    "from": {"name": "Test User", "role": 1},
    "text": "What is the refund policy?"
  },
  {
    "valueType": "DynamicPlanReceived",
    "type": "event",
    "timestamp": 1771240863,
    "value": {
      "steps": ["P:UniversalSearchTool"],
      "isFinalPlan": false
    }
  }
]
```

The first activity is a user message. The second is an internal event — the bot's AI decided to search the knowledge base.

### Activities

Individual things that happened during the conversation. There are two kinds:

- **Messages** — what the user said and what the bot replied
- **Trace events** — internal decisions the bot made (searching knowledge, executing a plan step, redirecting to a topic, encountering an error)

Each trace event has a `valueType` that identifies what kind of event it is. The project tracks 26 event types, including:

| Event type | What it means |
|-----------|--------------|
| `DynamicPlanReceived` | The AI orchestrator created a plan to answer the user |
| `DynamicPlanStepTriggered` | A specific step in that plan started executing |
| `DynamicPlanStepFinished` | A step completed (includes results) |
| `UniversalSearchToolTraceData` | The bot searched its knowledge base |
| `DynamicServerInitialize` | An MCP server connection was established |
| `DialogTracingInfo` | Topic/dialog routing information |
| `ErrorTraceData` | Something went wrong |
| `CSATSurveyResponse` | Customer satisfaction score |
| `AIBuilderTraceData` | An AI Builder model or prompt was invoked |
| `DynamicPlanStepBlocked` | A plan step was blocked by policy |
| `KnowledgeTraceData` | Detailed knowledge retrieval diagnostics |

### Entities

Cleaned-up, normalized versions of activities. The parser takes raw activities and produces entities with a consistent structure:

- A **session root** entity (overall conversation metadata)
- **Turn** entities (each user question + bot response pair)
- **Trace event** entities (one per tracked event type)

Each entity has an ID, a type, a label, and a flat dictionary of **properties** — the important data extracted from the raw activity.

### Enrichment

Raw transcript data is often deeply nested. For example, a `DynamicPlanStepFinished` event might have search results buried three levels deep:

```json
{
  "observation": {
    "search_result": {
      "search_results": [
        {"Name": "Refund Policy.docx", "Type": "SharePoint"}
      ]
    }
  }
}
```

Enrichment flattens this into simple, mappable properties:

```
retrieval_document_count: "1"
retrieval_document_names: "Refund Policy.docx"
retrieval_source_types: "SharePoint"
```

This happens automatically during entity extraction. Each event type has its own enrichment logic that knows which nested fields matter.

### Mapping rules

The translation instructions. Each rule says: "When you see an entity of type X, create an OTEL span with these properties." A rule includes:

- **Which entity to match** (by entity type and value type)
- **What OTEL span to create** (operation name, span kind)
- **How to name it** (a template like `"chat turn:{turn_index}"`)
- **Where it goes in the tree** (which parent rule it nests under)
- **Which properties to copy** (attribute mappings from MCS property to OTEL attribute)

The project ships with 28 default rules covering all 26 tracked event types.

### OTEL spans

The output format. A **span** represents a unit of work with:

- A name (like `"knowledge.retrieval"`)
- A start and end time
- Key-value attributes (like `mcs.knowledge.source_count: "3"`)
- A parent span (creating a tree structure)
- An operation name (like `knowledge.retrieval`, `chain`, `chat`)

Spans are the building blocks of distributed tracing. Monitoring tools visualize them as a waterfall or tree, making it easy to see what happened and how long each step took.

### Events vs spans

Some things are better represented as **events** (lightweight annotations attached to a parent span) rather than full spans. Errors and variable assignments, for example, don't have meaningful duration — they're point-in-time occurrences. The mapping rules use `output_type: "event"` for these, which attaches them as events on the parent span instead of creating a separate child span.

## The pipeline step by step

Let's walk through what happens when you upload the sample transcript (a user asking "What is the refund policy?").

### Step 1: Parse

The raw JSON array of 9 activities gets parsed into typed `MCSActivity` objects. The parser:

- Detects the JSON format (bare array, `{"activities": [...]}`, or Dataverse CSV row)
- Normalizes timestamps to epoch seconds/millis
- Extracts the conversation ID (`rex-conv-001`)
- Identifies the bot (`Rex Bluebot`) from the first bot message
- Pulls session metadata (outcome: Resolved, type: Engaged, 1 turn)

### Step 2: Extract entities

The activities become 7 entities:

```
1. session_root     — SessionInfo (outcome=Resolved, bot=Rex Bluebot)
2. turn_0           — Turn 0 (greeting): "Hello! I'm Rex Bluebot..."
3. turn_1           — Turn 1: "What is the refund policy?"
4. trace_DialogRedirect_0      — Dialog redirect to topic.RefundPolicy
5. trace_DynamicPlanReceived_0 — Plan with 1 step: search knowledge
6. trace_DynamicPlanStepTriggered_0 — Step triggered: KnowledgeSearch
7. trace_DynamicPlanFinished_0 — Plan completed, not cancelled
```

During extraction, the `DynamicPlanReceived` entity gets enriched with `step_count: "1"` and `is_final_plan: "False"` (flattened from the nested value).

### Step 3: Map to OTEL spans

The 28 mapping rules are applied. Each entity is matched against rules:

- `session_root` matches the root rule → creates the top-level `invoke_agent Rex Bluebot` span
- `turn_0` and `turn_1` match the turn rule → create `chat turn:0` and `chat turn:1` spans under the root
- `DynamicPlanReceived` matches the plan rule → creates `chain plan` span under `turn_1`
- `DynamicPlanStepTriggered` matches the step rule → creates `chain step:KnowledgeSearch` span under `dynamic_plan`
- `DynamicPlanFinished` matches the finished rule → creates `chain plan.finished` span under `dynamic_plan`
- `DialogRedirect` matches the redirect rule → creates `dialog_redirect` event on `turn_1`

### Step 4: Build the tree

Parent-child relationships are established based on the `parent_rule_id` in each mapping rule. The result is a span tree (shown below).

## The span tree

Here's what the output looks like for our example transcript:

```
invoke_agent Rex Bluebot (CLIENT)         ← root span
├── chat turn:0 (CLIENT)                  ← bot greeting
├── chat turn:1 (CLIENT)                  ← user question + bot answer
│   ├── chain plan (INTERNAL)             ← AI orchestrator's plan
│   │   ├── chain step:KnowledgeSearch    ← step: search knowledge
│   │   └── chain plan.finished           ← plan completed
│   └── [event] dialog_redirect           ← topic routing (event, not span)
```

The full default hierarchy for complex conversations looks like this:

```
invoke_agent {bot_name}                   ← session root
└── chat turn:{N}                         ← one per user message
    ├── chain plan                        ← AI orchestrator plan
    │   ├── chain step:{action}           ← each plan step
    │   ├── chain step.bind               ← step parameter binding
    │   ├── tool.execute step.finished    ← step completion + results
    │   └── chain plan.finished           ← plan done
    ├── knowledge.retrieval               ← knowledge base search
    ├── topic_classification              ← intent/topic routing
    ├── chain dialog.tracing              ← dialog flow info
    ├── create_agent mcp.init             ← MCP server connection
    │   └── create_agent mcp.init.confirm ← MCP handshake confirmed
    └── [events]                          ← errors, variables, etc.
```

## The self-learning loop

The project includes an improvement engine (`improve.py`) that can analyze hundreds of real transcripts to find gaps in the mapping rules and automatically fix them.

### How it works

```
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ Analyze   │────>│ Classify │────>│ Auto-fix │──┐
  │ all files │     │ findings │     │ obvious  │  │
  └──────────┘     └──────────┘     │ gaps     │  │
       ^                            └──────────┘  │
       │                                          │
       └──────────────────────────────────────────┘
                    repeat until converged
```

1. **Analyze** — Run every transcript through the full pipeline. Measure coverage (how many entities produce spans) and fill rate (how many attributes have values).
2. **Classify** — Sort gaps into two buckets:
   - **Auto-fixable**: An unknown event type appears in 3+ files → safe to add automatically
   - **Needs review**: Rare types or ones with complex nested data → flagged for a human
3. **Auto-fix** — Add new types to the tracker, create mapping rules, extend attribute mappings
4. **Re-analyze** — Run again with the improved rules and measure improvement
5. **Repeat** — Stop when there's nothing left to fix or improvement drops below 0.1%

### What it produces

- Per-iteration metrics (coverage %, fill rate, what was fixed)
- A code export file with Python snippets to paste into the source files
- The final improved mapping specification as JSON

## The web dashboard

The project includes a Reflex web app at `http://localhost:3000` with several panels:

| Page/Panel | What it does |
|-----------|-------------|
| **Upload** | Drag-and-drop a transcript JSON or Dataverse CSV file |
| **Mapping Editor** | Visual drag-and-drop editor (React Flow) showing MCS entities on the left, OTEL attributes on the right, with lines connecting them. Add, edit, or remove mapping rules. |
| **Span Tree** | Interactive tree visualization of the generated OTEL spans. Shows parent-child nesting, timing, and attributes for each span. |
| **Export** | Download the OTLP JSON output, ready to import into Jaeger or send to a collector |
| **Improve** (`/improve`) | Dashboard for the self-learning loop: set parameters, run iterations, see coverage charts, review findings, accept/reject suggestions, and apply changes to source code |

## The CLI tools

### analyze_transcripts.py

Scans transcript files and produces a markdown report showing which event types are covered, which are missing mapping rules, and what properties aren't being mapped.

```bash
# Scan the default directories
uv run python analyze_transcripts.py

# Scan a specific directory or CSV file
uv run python analyze_transcripts.py samples/

# Custom output with verbose logging
uv run python analyze_transcripts.py -o my_report.md -v
```

Output goes to `docs/transcript_analysis.md`.

### improve.py

Runs the self-learning improvement loop against a corpus of transcripts.

```bash
# Run against a directory of JSON files
uv run python improve.py /path/to/transcripts/

# Run against a Dataverse CSV export
uv run python improve.py samples/conversationtranscripts.csv

# Limit to 3 iterations, require 5+ files for auto-fix
uv run python improve.py samples/ -n 3 --min-files 5
```

Output goes to `improve_runs/`.

## File map

### Core logic

| File | Purpose |
|------|---------|
| `parsers.py` | Reads raw transcript JSON/CSV, extracts activities, produces normalized entities with enriched properties |
| `converter.py` | Applies mapping rules to entities, builds the OTEL span tree, exports OTLP JSON |
| `models.py` | All data models: MCSActivity, MCSEntity, OTELSpan, SpanMappingRule, AttributeMapping, etc. |
| `otel_registry.py` | 104 OTEL attribute definitions across 10 categories (the "vocabulary" of output attributes) |

### CLI tools

| File | Purpose |
|------|---------|
| `analyze_transcripts.py` | Coverage analysis — finds gaps between transcripts and mapping rules |
| `improve.py` | Self-learning loop — iteratively improves mapping rules using real transcripts |

### Web UI

| File | Purpose |
|------|---------|
| `main.py` | Reflex app entry point |
| `rxconfig.py` | Reflex configuration (ports, environment) |
| `web/web.py` | Frontend layout and routing |
| `web/components/` | UI components: upload panel, mapping editor, span tree viewer, export panel, improve dashboard |
| `web/state/` | Reflex state managers: handle uploads, mapping edits, preview generation, improvement runs |

### Tests

| File | Purpose |
|------|---------|
| `tests/test_parsers.py` | Parser unit tests |
| `tests/test_converter.py` | Converter unit tests |
| `tests/test_models.py` | Model unit tests |
| `tests/test_enrichment.py` | Entity enrichment tests |
| `tests/test_improve.py` | Improvement engine tests |
| `tests/fixtures/` | Sample transcript JSON and CSV files used by tests |

## Glossary

| Term | Meaning |
|------|---------|
| **Activity** | A single event in a Copilot Studio transcript (message, trace, or event) |
| **Attribute** | A key-value pair on an OTEL span (like `mcs.session.outcome: "Resolved"`) |
| **Copilot Studio** | Microsoft's platform for building AI chatbots (formerly Power Virtual Agents) |
| **Dataverse** | Microsoft's data platform where Copilot Studio stores conversation transcripts |
| **Enrichment** | Flattening nested JSON structures into simple key-value properties |
| **Entity** | A normalized, cleaned-up version of a transcript activity, ready for mapping |
| **Mapping rule** | Instructions for converting one type of MCS entity into an OTEL span |
| **MCP** | Model Context Protocol — a standard for connecting AI agents to external tools |
| **OTEL** | OpenTelemetry — an open standard for collecting observability data (traces, metrics, logs) |
| **OTLP** | OpenTelemetry Protocol — the wire format for sending OTEL data to collectors |
| **Span** | A unit of work in a trace, with a name, timing, attributes, and parent-child relationships |
| **Trace** | A tree of spans representing an entire conversation session |
| **Transcript** | The raw conversation log exported from Copilot Studio |
| **Turn** | One user message + the bot's response (a back-and-forth exchange) |
| **valueType** | The identifier for what kind of trace event an activity represents |
