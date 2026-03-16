import reflex as rx
from reflex.components.component import NoSSRComponent
from reflex.event import EventHandler, passthrough_event_spec


class MappingFlow(NoSSRComponent):
    """React Flow wrapper for ETL-style drag-and-drop mapping UI.

    Manages local React state for nodes/edges (smooth UX) and fires
    Reflex events only when connections are created or deleted.
    """

    library = "@xyflow/react@12"
    tag = "MappingFlow"

    initial_nodes: rx.Var[list[dict]]
    initial_edges: rx.Var[list[dict]]
    on_connect_edge: EventHandler[passthrough_event_spec(dict)]
    on_delete_edge: EventHandler[passthrough_event_spec(str)]
    on_edge_click: EventHandler[passthrough_event_spec(str)]

    def add_custom_code(self) -> list[str]:
        return ["import '@xyflow/react/dist/style.css';"]

    def _get_dynamic_imports(self) -> str:
        return (
            "const MappingFlow = ClientSide("
            "() => Promise.all([import('@xyflow/react'), import('react')]).then(([mod, React]) => {\n"
            "  const { ReactFlow, Background, Controls, MiniMap, applyEdgeChanges } = mod;\n"
            "  const { useState, useEffect, useCallback, createElement } = React;\n"
            "  return function MappingFlowWrapper({ children, ...props }) {\n"
            "    const [nodes, setNodes] = useState(props.initialNodes || []);\n"
            "    const [edges, setEdges] = useState(props.initialEdges || []);\n"
            "    useEffect(() => {\n"
            "      setNodes(props.initialNodes || []);\n"
            "    }, [JSON.stringify(props.initialNodes)]);\n"
            "    useEffect(() => {\n"
            "      setEdges(props.initialEdges || []);\n"
            "    }, [JSON.stringify(props.initialEdges)]);\n"
            "    const handleConnect = useCallback((params) => {\n"
            "      const edgeId = params.source + '->' + params.target;\n"
            "      const newEdge = {\n"
            "        ...params, id: edgeId, animated: true,\n"
            "        style: { stroke: '#22c55e', strokeWidth: 2 },\n"
            "        markerEnd: { type: 'arrowclosed', color: '#22c55e' },\n"
            "      };\n"
            "      setEdges((eds) => [...eds.filter(e => e.id !== edgeId), newEdge]);\n"
            "      if (props.onConnectEdge) props.onConnectEdge(params);\n"
            "    }, [props.onConnectEdge]);\n"
            "    const handleEdgesChange = useCallback((changes) => {\n"
            "      setEdges((eds) => applyEdgeChanges(changes, eds));\n"
            "      changes.filter(c => c.type === 'remove').forEach(r => {\n"
            "        if (props.onDeleteEdge) props.onDeleteEdge(r.id);\n"
            "      });\n"
            "    }, [props.onDeleteEdge]);\n"
            "    const handleEdgeClick = useCallback((event, edge) => {\n"
            "      var ruleId = (edge.data && edge.data.ruleId) || '';\n"
            "      if (props.onEdgeClick) props.onEdgeClick(ruleId);\n"
            "    }, [props.onEdgeClick]);\n"
            "    return createElement(ReactFlow, {\n"
            "      nodes, edges,\n"
            "      onConnect: handleConnect,\n"
            "      onEdgesChange: handleEdgesChange,\n"
            "      onEdgeClick: handleEdgeClick,\n"
            "      nodesDraggable: false,\n"
            "      nodesConnectable: true,\n"
            "      fitView: true,\n"
            "      style: { width: '100%', height: '100%' },\n"
            "      proOptions: { hideAttribution: true },\n"
            "    }, [\n"
            "      createElement(Background, { key: 'bg', gap: 20, size: 1 }),\n"
            "      createElement(Controls, { key: 'ctrl', showInteractive: false }),\n"
            "      createElement(MiniMap, { key: 'mm', pannable: true, zoomable: true }),\n"
            "    ]);\n"
            "  };\n"
            "}))"
        )


mapping_flow = MappingFlow.create
