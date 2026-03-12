# MCS Transcript Analysis Report
Generated: 2026-03-11 23:35 UTC

## Summary

- **Files analyzed:** 3
- **Total activities:** 42
- **Unique valueTypes:** 14
- **Tracked (in TRACKED_EVENT_TYPES):** 12
- **Untracked:** 2
- **Have mapping rules:** 13
- **Tracked but missing rules:** 0

### Files

| File | Activities | Bot | Conversation ID |
|------|-----------|-----|-----------------|
| `pva_studio_transcript.json` | 9 | Troubleshoot_bluebot | `pva-conv-001…` |
| `rex_teams_transcript.json` | 9 | Rex Bluebot | `rex-conv-001…` |
| `zava_expense_transcript.json` | 24 | Expensy (Zava, expenses) | `aff7b04e-abe0-4ec1-a…` |

> **Note:** `ConversationInfo` and `SessionInfo` are handled specially in `_extract_session_info()`,
> not via `TRACKED_EVENT_TYPES`. They appear in the table below but are not "untracked" — they are
> extracted into `MCSTranscript.session_info` and mapped via the `session_root` rule.

## All ValueTypes

| valueType | Count | Files | Tracked | Has Rule | Properties |
|-----------|-------|-------|---------|----------|------------|
| `ConversationInfo` | 2 | 2 | session | session_root | 2 available |
| `DialogRedirect` | 1 | 1 | yes | yes | 1/2 mapped |
| `DialogTracingInfo` | 2 | 1 | yes | yes | 4/1 mapped |
| `DynamicPlanFinished` | 2 | 2 | yes | yes | 2/2 mapped |
| `DynamicPlanReceived` | 3 | 3 | yes | yes | 3/5 mapped |
| `DynamicPlanReceivedDebug` | 1 | 1 | yes | yes | 2/4 mapped |
| `DynamicPlanStepBindUpdate` | 6 | 1 | yes | yes | 5/4 mapped |
| `DynamicPlanStepFinished` | 7 | 2 | yes | yes | 11/8 mapped |
| `DynamicPlanStepTriggered` | 3 | 3 | yes | yes | 3/7 mapped |
| `DynamicServerInitialize` | 1 | 1 | yes | yes | 0/2 mapped |
| `DynamicServerToolsList` | 1 | 1 | yes | yes | 2/2 mapped |
| `ProtocolInfo` | 1 | 1 | yes | yes | 0/1 mapped |
| `SessionInfo` | 2 | 2 | session | yes | 6/7 mapped |
| `UniversalSearchToolTraceData` | 2 | 1 | yes | yes | 4/5 mapped |

## Attribute Mapping Gaps

Tracked types that have mapping rules but unmapped properties.

### `DialogRedirect`

- **Available properties:** targetDialogId, targetDialogType
- **Currently mapped:** targetDialogId
- **Unmapped:** targetDialogType

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="targetDialogType",
                        otel_attribute="copilot_studio.targetDialogType",
                    ),
```

### `DynamicPlanFinished`

- **Available properties:** planId, wasCancelled
- **Currently mapped:** planId, was_cancelled
- **Unmapped:** wasCancelled

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="wasCancelled",
                        otel_attribute="copilot_studio.wasCancelled",
                    ),
```

### `DynamicPlanReceived`

- **Available properties:** isFinalPlan, planIdentifier, steps, toolDefinitions, toolKinds
- **Currently mapped:** is_final_plan, planIdentifier, step_count
- **Unmapped:** isFinalPlan, toolKinds

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="isFinalPlan",
                        otel_attribute="copilot_studio.isFinalPlan",
                    ),
                    AttributeMapping(
                        mcs_property="toolKinds",
                        otel_attribute="copilot_studio.toolKinds",
                    ),
```

### `DynamicPlanReceivedDebug`

- **Available properties:** ask, isFinalPlan, planIdentifier, summary
- **Currently mapped:** plan_summary, user_ask
- **Unmapped:** ask, isFinalPlan, planIdentifier, summary

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="ask",
                        otel_attribute="copilot_studio.ask",
                    ),
                    AttributeMapping(
                        mcs_property="isFinalPlan",
                        otel_attribute="copilot_studio.isFinalPlan",
                    ),
                    AttributeMapping(
                        mcs_property="planIdentifier",
                        otel_attribute="copilot_studio.planIdentifier",
                    ),
                    AttributeMapping(
                        mcs_property="summary",
                        otel_attribute="copilot_studio.summary",
                    ),
```

### `DynamicPlanStepBindUpdate`

- **Available properties:** arguments, planIdentifier, stepId, taskDialogId
- **Currently mapped:** arguments_json, mcp_tool_name, search_keywords, search_query, taskDialogId
- **Unmapped:** arguments, planIdentifier, stepId

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="arguments",
                        otel_attribute="copilot_studio.arguments",
                    ),
                    AttributeMapping(
                        mcs_property="planIdentifier",
                        otel_attribute="copilot_studio.planIdentifier",
                    ),
                    AttributeMapping(
                        mcs_property="stepId",
                        otel_attribute="copilot_studio.stepId",
                    ),
```

### `DynamicPlanStepFinished`

- **Available properties:** executionTime, hasRecommendations, observation, planIdentifier, planUsedOutputs, state, stepId, taskDialogId
- **Currently mapped:** connector_result_url, executionTime, hitl_responder_id, retrieval_document_count, retrieval_document_names, retrieval_errors, retrieval_source_types, state, taskDialogId, tool_is_error, tool_result_text
- **Unmapped:** hasRecommendations, planIdentifier, planUsedOutputs, stepId

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="hasRecommendations",
                        otel_attribute="copilot_studio.hasRecommendations",
                    ),
                    AttributeMapping(
                        mcs_property="planIdentifier",
                        otel_attribute="copilot_studio.planIdentifier",
                    ),
                    AttributeMapping(
                        mcs_property="planUsedOutputs",
                        otel_attribute="copilot_studio.planUsedOutputs",
                    ),
                    AttributeMapping(
                        mcs_property="stepId",
                        otel_attribute="copilot_studio.stepId",
                    ),
```

### `DynamicPlanStepTriggered`

- **Available properties:** hasRecommendations, planIdentifier, state, stepId, taskDialogId, thought, type
- **Currently mapped:** taskDialogId, thought, type
- **Unmapped:** hasRecommendations, planIdentifier, state, stepId

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="hasRecommendations",
                        otel_attribute="copilot_studio.hasRecommendations",
                    ),
                    AttributeMapping(
                        mcs_property="planIdentifier",
                        otel_attribute="copilot_studio.planIdentifier",
                    ),
                    AttributeMapping(
                        mcs_property="state",
                        otel_attribute="copilot_studio.state",
                    ),
                    AttributeMapping(
                        mcs_property="stepId",
                        otel_attribute="copilot_studio.stepId",
                    ),
```

### `DynamicServerInitialize`

- **Available properties:** dialogSchemaName, initializationResult
- **Currently mapped:** none
- **Unmapped:** dialogSchemaName, initializationResult

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="dialogSchemaName",
                        otel_attribute="copilot_studio.dialogSchemaName",
                    ),
                    AttributeMapping(
                        mcs_property="initializationResult",
                        otel_attribute="copilot_studio.initializationResult",
                    ),
```

### `DynamicServerToolsList`

- **Available properties:** dialogSchemaName, toolsList
- **Currently mapped:** tool_count, tool_names
- **Unmapped:** dialogSchemaName, toolsList

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="dialogSchemaName",
                        otel_attribute="copilot_studio.dialogSchemaName",
                    ),
                    AttributeMapping(
                        mcs_property="toolsList",
                        otel_attribute="copilot_studio.toolsList",
                    ),
```

### `ProtocolInfo`

- **Available properties:** endpoint
- **Currently mapped:** none
- **Unmapped:** endpoint

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="endpoint",
                        otel_attribute="copilot_studio.endpoint",
                    ),
```

### `SessionInfo`

- **Available properties:** endTimeUtc, impliedSuccess, outcome, outcomeReason, startTimeUtc, turnCount, type
- **Currently mapped:** bot_name, channel, conversation_id, environment, outcome, tenant
- **Unmapped:** endTimeUtc, impliedSuccess, outcomeReason, startTimeUtc, turnCount, type

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="endTimeUtc",
                        otel_attribute="copilot_studio.endTimeUtc",
                    ),
                    AttributeMapping(
                        mcs_property="impliedSuccess",
                        otel_attribute="copilot_studio.impliedSuccess",
                    ),
                    AttributeMapping(
                        mcs_property="outcomeReason",
                        otel_attribute="copilot_studio.outcomeReason",
                    ),
                    AttributeMapping(
                        mcs_property="startTimeUtc",
                        otel_attribute="copilot_studio.startTimeUtc",
                    ),
                    AttributeMapping(
                        mcs_property="turnCount",
                        otel_attribute="copilot_studio.turnCount",
                    ),
                    AttributeMapping(
                        mcs_property="type",
                        otel_attribute="copilot_studio.type",
                    ),
```

### `UniversalSearchToolTraceData`

- **Available properties:** filteredResults, fullResults, knowledgeSources, outputKnowledgeSources, toolId
- **Currently mapped:** knowledge_source_count, knowledge_sources, output_knowledge_sources, toolId
- **Unmapped:** filteredResults, fullResults, knowledgeSources, outputKnowledgeSources

**Suggested attribute mappings:**
```python
                    AttributeMapping(
                        mcs_property="filteredResults",
                        otel_attribute="copilot_studio.filteredResults",
                    ),
                    AttributeMapping(
                        mcs_property="fullResults",
                        otel_attribute="copilot_studio.fullResults",
                    ),
                    AttributeMapping(
                        mcs_property="knowledgeSources",
                        otel_attribute="copilot_studio.knowledgeSources",
                    ),
                    AttributeMapping(
                        mcs_property="outputKnowledgeSources",
                        otel_attribute="copilot_studio.outputKnowledgeSources",
                    ),
```

