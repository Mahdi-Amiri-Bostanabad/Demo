import { useMemo } from "react";
import { Background, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { EDGE_HANDLES, EDGE_LABELS, KIND_STYLE, NODE_META } from "../meta";
import type { NodeStatus, RunView, Topology } from "../types";

type Data = { id: string; status: NodeStatus; visits: number; progress?: string; selected: boolean; llm?: string };

const SIDES: [string, Position][] = [["t", Position.Top], ["r", Position.Right], ["b", Position.Bottom], ["l", Position.Left]];

function AgentNode({ data }: NodeProps<Node<Data>>) {
  const m = NODE_META[data.id];
  const ks = KIND_STYLE[m.kind];
  const terminal = m.kind === "terminal";
  return (
    <div className={`agent-node ${data.status} ${terminal ? "terminal" : ""} ${data.selected ? "sel" : ""}`}
      style={{ ["--kc" as any]: ks.color }}>
      {SIDES.map(([id, pos]) => (
        <span key={id}>
          <Handle id={`s-${id}`} type="source" position={pos} className="h" />
          <Handle id={`t-${id}`} type="target" position={pos} className="h" />
        </span>
      ))}
      {terminal ? (
        <div className="term-label">{m.label}</div>
      ) : (
        <>
          <div className="an-top">
            <span className="an-tag">{ks.tag}</span>
            {data.visits > 0 && <span className="an-visits" title="times executed">×{data.visits}</span>}
          </div>
          <div className="an-label">{m.label}</div>
          <div className="an-sub">{data.status === "active" && data.progress ? data.progress : m.sub}</div>
          {data.llm && <div className={`an-llm ${data.llm}`}>{data.llm === "live" ? "LLM live" : data.llm === "rules" ? "rule engine" : "LLM fallback"}</div>}
        </>
      )}
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

export default function GraphView({ topo, view, highlight }: { topo: Topology | null; view: RunView; highlight?: string[] }) {
  const nodes: Node<Data>[] = useMemo(() => {
    if (!topo) return [];
    return topo.nodes.map((n) => {
      const m = NODE_META[n.id] || { x: 0, y: 0 };
      return {
        id: n.id, type: "agent", position: { x: m.x, y: m.y }, draggable: false,
        data: {
          id: n.id, status: view.nodeStatus[n.id] || "idle", visits: view.visits[n.id] || 0,
          progress: view.progress[n.id], selected: !!highlight?.includes(n.id),
          llm: view.values?.llm_usage?.[n.id],
        },
      };
    });
  }, [topo, view.nodeStatus, view.visits, view.progress, view.values, highlight]);

  const edges: Edge[] = useMemo(() => {
    if (!topo) return [];
    return topo.edges.map((e) => {
      const k = `${e.source}->${e.target}`;
      const [sh, th] = EDGE_HANDLES[k] || ["r", "l"];
      const count = view.edgeCounts[k] || 0;
      const hot = view.lastEdges.includes(k) && view.status !== "idle";
      const color = hot ? "#dafa9c" : count ? "#b5b5b5" : "#3a3a3a";
      return {
        id: k, source: e.source, target: e.target, sourceHandle: `s-${sh}`, targetHandle: `t-${th}`,
        type: "smoothstep", animated: hot,
        label: EDGE_LABELS[k] ? `${EDGE_LABELS[k]}${count > 1 ? ` ×${count}` : ""}` : count > 1 ? `×${count}` : undefined,
        labelStyle: { fill: count ? "#ededed" : "#737373", fontSize: 11 },
        labelBgStyle: { fill: "#0f0f0f", fillOpacity: 0.9 },
        labelBgPadding: [4, 2] as [number, number],
        style: { stroke: color, strokeWidth: hot ? 3 : count ? 2 : 1.2, strokeDasharray: e.conditional && !count ? "5 4" : undefined,
          filter: hot ? "drop-shadow(0 0 4px #dafa9c88)" : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
        zIndex: hot ? 10 : count ? 5 : 0,
      } as Edge;
    });
  }, [topo, view.edgeCounts, view.lastEdges, view.status]);

  return (
    <>
    <div className="graph-wrap">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.08 }}
        proOptions={{ hideAttribution: true }} nodesConnectable={false} elementsSelectable={false} nodesFocusable={false} edgesFocusable={false}
        zoomOnScroll={false} panOnScroll={false} minZoom={0.3}>
        <Background color="#262626" gap={22} />
      </ReactFlow>
    </div>
      <div className="legend">
        {Object.entries(KIND_STYLE).filter(([k]) => k !== "terminal").map(([k, v]) => (
          <span key={k}><i style={{ background: v.color }} />{v.tag}</span>
        ))}
        <span><i className="dash" />conditional edge</span>
        <span><i style={{ background: "#dafa9c" }} />last transition</span>
      </div>
    </>
  );
}
