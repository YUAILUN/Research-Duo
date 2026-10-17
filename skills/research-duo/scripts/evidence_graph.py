"""Validate provenance structure and trace changes, without certifying source truth."""
from contracts import require, strings, text


def audit(data):
    require(isinstance(data, dict), "graph input must be an object")
    nodes = data.get("nodes")
    require(isinstance(nodes, list) and nodes, "nodes required")
    by_id = {}
    for node in nodes:
        require(isinstance(node, dict), "node must be an object")
        nid = text(node.get("id"), "node id")
        require(nid not in by_id, "duplicate node id")
        text(node.get("label"), "node label")
        kind = node.get("kind")
        require(kind in ("evidence", "assumption", "claim", "judgment", "decision"), "invalid node kind")
        deps = strings(node.get("depends_on"), "depends_on")
        if kind in ("evidence", "assumption"):
            require(not deps, "evidence/assumption nodes are roots; use clusters for common sources")
        else:
            require(deps, "derived node requires explicit evidence or assumption dependencies")
        if kind == "evidence":
            text(node.get("source"), "source")
            text(node.get("cluster"), "cluster")
        by_id[nid] = node
    for node in nodes:
        require(set(node["depends_on"]) <= set(by_id), "dangling dependency")
    changed = strings(data.get("changed_ids", []), "changed_ids")
    require(set(changed) <= set(by_id), "unknown changed node")
    # Iterative topological pass avoids Python recursion limits on valid deep graphs.
    pending, ancestors, order = set(by_id), {}, []
    while pending:
        ready = sorted(nid for nid in pending if set(by_id[nid]["depends_on"]) <= set(ancestors))
        require(ready, "cycle detected; circular support cannot justify a decision")
        for nid in ready:
            deps = by_id[nid]["depends_on"]
            ancestors[nid] = set(deps).union(*(ancestors[d] for d in deps))
            order.append(nid)
        pending.difference_update(ready)
    trace = {}
    for nid in order:
        closure = ancestors[nid] | {nid}
        refs = sorted(k for k in closure if by_id[k]["kind"] == "evidence")
        clusters = sorted({by_id[k]["cluster"] for k in refs})
        trace[nid] = {"evidence_ids": refs, "declared_source_clusters": clusters,
                      "assumption_ids": sorted(k for k in closure if by_id[k]["kind"] == "assumption")}
    affected = [nid for nid in order if (ancestors[nid] | {nid}) & set(changed)]
    return {"structurally_valid": True, "trace": trace, "affected_ids": affected,
            "decisions_to_revisit": [k for k in affected if by_id[k]["kind"] == "decision"],
            "notice": "Clusters are user declarations, not proven independence. Audit checks references/cycles, not truth, entailment, sufficiency, or a statistical causal DAG."}
