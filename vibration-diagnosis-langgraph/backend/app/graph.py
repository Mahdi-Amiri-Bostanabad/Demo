"""Graph assembly: nodes, edges, conditional routes, checkpointer."""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from . import nodes as N
from .state import VibState
from .tools import INVESTIGATION_TOOLS


def build_graph(checkpointer=None):
    g = StateGraph(VibState)

    g.add_node("acquisition", N.acquisition)
    g.add_node("signal_qa", N.signal_qa)
    g.add_node("severity", N.severity)
    g.add_node("spectral", N.spectral)
    g.add_node("triage", N.triage)
    g.add_node("diagnostician", N.diagnostician)
    g.add_node("diag_tools", ToolNode(INVESTIGATION_TOOLS))
    g.add_node("confidence_gate", N.confidence_gate)
    g.add_node("prognosis", N.prognosis)
    g.add_node("planner", N.planner)
    g.add_node("human_review", N.human_review)
    g.add_node("report", N.report)

    g.add_edge(START, "acquisition")
    g.add_edge("acquisition", "signal_qa")
    # QA either rejects (loop back), gives up, or fans out to two parallel analysts.
    g.add_conditional_edges("signal_qa", N.route_after_qa, ["acquisition", "severity", "spectral", "report"])
    # Fan-in: triage waits until BOTH parallel branches have written their results.
    g.add_edge(["severity", "spectral"], "triage")
    g.add_conditional_edges("triage", N.route_after_triage, ["diagnostician", "report"])
    # ReAct-style tool loop.
    g.add_conditional_edges("diagnostician", N.route_after_diagnostician, ["diag_tools", "confidence_gate"])
    g.add_edge("diag_tools", "diagnostician")
    # Confidence gate can send the whole flow back for another measurement.
    g.add_conditional_edges("confidence_gate", N.route_after_gate, ["acquisition", "prognosis", "report"])
    g.add_edge("prognosis", "planner")
    g.add_conditional_edges("planner", N.route_after_planner, ["human_review", "report"])
    g.add_conditional_edges("human_review", N.route_after_review, ["planner", "report"])
    g.add_edge("report", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver())


def graph_topology(compiled) -> dict:
    gg = compiled.get_graph()
    nodes = [{"id": n, "label": N.AGENTS.get(n, n)} for n in gg.nodes]
    edges = [{"source": e.source, "target": e.target, "conditional": bool(e.conditional)} for e in gg.edges]
    return {"nodes": nodes, "edges": edges, "mermaid": gg.draw_mermaid()}
