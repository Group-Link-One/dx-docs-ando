"""Reader's view of bridges.yaml: topics, queues and stores become nodes, parallel edges merge, deploy wiring is flagged."""
from .render import mermaid_id

CHANNEL = {"kafka": "topic", "mqtt": "topic", "nats": "topic", "rabbitmq": "queue"}
CALL = ("http", "grpc")


def _family(via):
    return "msg" if via in CHANNEL else "call" if via in CALL else "store"


def build(bridges, raw_edges=None, unmatched=None):
    src = {n["id"]: n for n in bridges["nodes"]}
    raw_edges = bridges["edges"] if raw_edges is None else raw_edges
    unmatched = (bridges.get("unmatched_ports") or []) if unmatched is None else unmatched
    stores = {e["via"] for e in raw_edges if e["via"] in (e["from"], e["to"])}
    nodes, edges = {}, {}

    def node(nid, **attrs):
        if nid not in nodes:
            n = src.get(nid, {})
            kind = "store" if nid in stores else n.get("kind", "component")
            group = n.get("project") or ("external" if kind in ("external", "unknown") else n.get("namespace") or "other")
            nodes[nid] = {"id": nid, "label": nid, "kind": kind, "group": group, "namespace": n.get("namespace"), **attrs}
        return nid

    def edge(a, b, via, config, item):
        e = edges.setdefault((a, b, via, config), {"from": a, "to": b, "via": via, "fam": _family(via), "config": config, "items": []})
        if item not in e["items"]:
            e["items"].append(item)

    def channel(via, name):
        label = name.split(":", 1)[1] if name.startswith(("queue:", "exchange:", "topic:")) else name
        return node(f"{via}:{name}", label=label, kind=CHANNEL[via], group=None, via=via)

    for e in raw_edges:
        via, item = e["via"], {"name": e["name"], "confidence": e["confidence"], "evidence": e["evidence"]}
        fp = {"from_part": e["from_part"]} if e.get("from_part") else {}
        tp = {"to_part": e["to_part"]} if e.get("to_part") else {}
        if e["confidence"] == "config":
            edge(node(e["from"]), node(e["to"]), via, True, item)
        elif via in CHANNEL:
            ch = channel(via, e["name"])
            edge(node(e["from"]), ch, via, False, {**item, **fp})
            edge(ch, node(e["to"]), via, False, {**item, **tp})
        elif via in CALL or via in (e["from"], e["to"]):
            edge(node(e["from"]), node(e["to"]), via, False, {**item, **fp, **tp})
        else:
            st = node(f"store:{via}", label=via, kind="store", group=None, via=via)
            edge(node(e["from"]), st, via, False, {**item, **fp, "access": "writes"})
            edge(st, node(e["to"]), via, False, {**item, **tp, "access": "reads"})

    for u in unmatched:
        if u.get("direction") == "produces" and u.get("via") in CHANNEL and u.get("name"):
            cid = f"{u['via']}:{u['name']}"
            orphan = cid not in nodes
            ch = channel(u["via"], u["name"])
            if orphan:
                nodes[ch]["orphan"] = True
            who = u.get("component") or u["project"]
            if who not in nodes:
                nodes[who] = {"id": who, "label": who, "kind": src.get(who, {}).get("kind", "component"), "group": u["project"],
                              "namespace": src.get(who, {}).get("namespace")}
            edge(who, ch, u["via"], False, {"name": u["name"], "confidence": "code",
                                            "evidence": [f"{u['project']}:{u.get('evidence')}"], "note": u.get("note"),
                                            **({"from_part": u["part"]} if u.get("part") else {})})

    # a service that both writes and reads one store gets a single two-way edge
    out = []
    for (a, b, via, config), e in edges.items():
        if not config and nodes[b]["kind"] == "store" and b.startswith("store:"):
            back = edges.get((b, a, via, False))
            if back:
                flipped = [{**{k: v for k, v in i.items() if k != "to_part"}, **({"from_part": i["to_part"]} if i.get("to_part") else {})}
                           for i in back["items"]]
                e = {**e, "both": True, "items": e["items"] + [i for i in flipped if i not in e["items"]]}
        elif not config and nodes[a]["kind"] == "store" and a.startswith("store:") and (b, a, via, False) in edges:
            continue
        out.append(e)
    out.sort(key=lambda e: (e["from"], e["to"], e["via"], e["config"]))
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": out}


def mermaid(view, max_edges=60):
    """One flowchart of the code-level edges, or None when there is nothing readable to draw."""
    edges = [e for e in view["edges"] if not e["config"]]
    if not edges or len(edges) > max_edges:
        return None
    by_id = {n["id"]: n for n in view["nodes"]}
    lines = ["flowchart LR"]
    for nid in sorted({e["from"] for e in edges} | {e["to"] for e in edges}):
        n = by_id[nid]
        label = n["label"].replace('"', "'")
        if n["kind"] in ("topic", "queue"):
            label = f"{label}<br/>({n['via']}, no known consumer)" if n.get("orphan") else f"{label}<br/>({n['via']})"
        o, c = {"topic": ("([", "])"), "queue": ("([", "])"), "store": ("[(", ")]")}.get(n["kind"], ("[", "]"))
        lines.append(f'  {mermaid_id(nid)}{o}"{label}"{c}')
    for e in edges:
        arrow = "<-->" if e.get("both") else "-->"
        if by_id[e["from"]]["kind"] in ("topic", "queue") or by_id[e["to"]]["kind"] in ("topic", "queue"):
            lines.append(f'  {mermaid_id(e["from"])} {arrow} {mermaid_id(e["to"])}')
        else:
            n = len(e["items"])
            label = e["items"][0]["name"] if n == 1 and len(e["items"][0]["name"]) <= 40 else f"{n} {'routes' if e['fam'] == 'call' else 'names'}"
            label = label.replace('"', "'").replace("|", "/")
            lines.append(f'  {mermaid_id(e["from"])} {arrow}|"{e["via"]}: {label}"| {mermaid_id(e["to"])}')
    return "\n".join(lines)
