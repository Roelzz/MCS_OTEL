# Improvement Plan: MCS-OTEL Coverage Expansion

## Problem Statement
The goal was to improve the OTLP coverage and attribute mapping for conversation transcripts, specifically targeting the dataset in `uploaded_files/conversationtranscripts.csv`. Initial analysis revealed gaps in mapping for dynamic planning events, MCP tool execution, and knowledge retrieval details.

## Analysis Findings
Running `improve.py` on the target dataset identified the following missing mappings:

1.  **Dynamic Planning**:
    -   `DynamicPlanReceived`: Missing `isFinalPlan`.
    -   `DynamicPlanReceivedDebug`: Missing `ask` (user query) and `summary`.
    -   `DynamicPlanStepBindUpdate`: Missing `arguments`.

2.  **MCP Integration**:
    -   `DynamicServerInitialize`: Missing initialization results and server info.
    -   `DynamicServerToolsList`: Missing tool definitions and counts.

3.  **Knowledge Retrieval**:
    -   `UniversalSearchToolTraceData`: Missing detailed results (filtered/full) and knowledge source breakdowns.

## Implementation Plan & Execution

### 1. Attribute Registry Updates (`otel_registry.py`)
Added 15 new attributes to the OpenTelemetry registry to support the missing data. Key additions include:
-   `mcs.mcp.*` namespace for Model Context Protocol details.
-   `mcs.plan.*` namespace for planner state.
-   `mcs.knowledge.*` namespace for search results.

### 2. Parser Enhancements (`parsers.py`)
Instead of mapping complex nested objects (like lists of tools or search results) directly to string attributes (which results in messy `[object Object]` or truncated strings), we implemented a **JSON serialization strategy**:
-   **Enrichment**: The parser now detects these complex fields and creates new `*_json` properties (e.g., `mcp_tools_list_json`, `filtered_results_json`).
-   **Clean Data**: This ensures that the OTEL backend receives valid, parseable JSON strings for these rich data structures.

### 3. Converter Mapping Rules (`converter.py`)
Updated the mapping rules to connect the enriched properties to the new OTEL attributes:
-   **DynamicServerInitialize**: Maps `initializationResult` -> `mcs.mcp.initialization_result`.
-   **DynamicServerToolsList**: Maps `toolsList` -> `mcs.mcp.tools_list`.
-   **UniversalSearchToolTraceData**: Maps `filteredResults` -> `mcs.knowledge.filtered_results`.

## Verification
-   **Coverage**: Re-running `improve.py` showed a fill rate improvement to **74%** (up from ~70%) and **100%** event coverage.
-   **Tests**: All 150 unit tests passed, confirming no regressions.

## Next Steps
-   Monitor the `mcs.mcp.*` attributes in your observability backend (Jaeger/Honeycomb) to ensure the JSON values are parsed correctly by your visualization tools.
-   Consider adding specific "count" attributes (e.g., `mcs.mcp.tool_count`) if you need to aggregate these metrics without parsing JSON.
