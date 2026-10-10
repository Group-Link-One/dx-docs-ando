"""`ando map`: infra inventory + service builds + ports -> deploy.json, bridges.yaml, gap questions."""
import fnmatch
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from urllib.parse import urlparse

import yaml

from . import inventory, live, questions
from .gitx import _join
from .project import now

DEFAULT_BUILDS = [{"glob": "**/Dockerfile", "image": "{dir}"}]
SVC_HOST = re.compile(r"([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.svc\b")
SELFISH = re.compile(r"(LISTEN|BIND|PUBLIC_URL|SELF_URL|BASE_PATH)", re.I)
PORT_JOINS = [("produces", "consumes"), ("writes", "reads")]


def _glob(rel, pattern):
    return fnmatch.fnmatch(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:]))


def scan_builds(project, sha):
    """Images a service builds, from Dockerfile locations (manifest `builds` patterns) plus ports.json."""
    rules = project.spec.get("builds") or DEFAULT_BUILDS
    base = (project.spec.get("path", ".") or ".").strip("/")
    excludes = project.spec.get("exclude") or []
    builds = []
    for f in project.repo.ls_files(sha):
        rel = f[len(base) + 1:] if base not in ("", ".") else f
        for r in rules:
            if _glob(rel, r["glob"]):
                d = PurePosixPath(rel).parent
                name = PurePosixPath(rel).name
                suffix = name.split("-", 1)[1] if "-" in name else name.split(".", 1)[-1]
                image = r["image"].format(dir=d.name or project.slug, file=name, suffix=suffix, slug=project.slug)
                excluded = any(_glob(rel, ex) or rel.startswith(ex.rstrip("*").rstrip("/") + "/") for ex in excludes)
                builds.append({"image": image, "key": inventory.split_image(image)[2], "from": rel,
                               "source": "scan", "excluded": excluded})
                break
    ports = project.load_json("ports.json", {}) or {}
    for b in ports.get("builds") or []:
        builds.append({"image": b["image"], "key": inventory.split_image(b["image"])[2], "from": b.get("from"),
                       "source": "ports", "excluded": False})
    return builds


def refresh_inventory(project, sha):
    root = project.repo.snapshot(project.slug, sha)
    name = re.sub(r"\.git$", "", project.spec["repo"].rstrip("/")).replace(":", "/").rsplit("/", 1)[-1]
    inv = inventory.extract(root, project.spec.get("exclude") or [], name)
    inv = {"sha": sha, "generated_at": now(), "renderer": "raw yaml + kustomize namespace/images overrides", **inv}
    project.save_json("inventory.json", inv)
    return inv


def build(target, shas):
    """shas: slug -> sha to read at (baseline for service projects, HEAD for infra)."""
    infra = [p for p in target.projects if p.kind == "infra"]
    services = [p for p in target.projects if p.kind != "infra"]
    invs = {}
    for p in infra:
        invs[p.slug] = refresh_inventory(p, shas[p.slug])
    builds = {p.slug: scan_builds(p, shas[p.slug]) for p in services if shas.get(p.slug)}

    by_key = defaultdict(lambda: {"builders": [], "workloads": []})
    for slug, bl in builds.items():
        for b in bl:
            by_key[b["key"]]["builders"].append({"project": slug, **b})
    undeclared = []
    for slug, inv in invs.items():
        needs_app = target.project(slug).spec.get("live_requires_app")
        snap = target.project(slug).load_json("live.json")
        if snap:
            live_wl = {(x["namespace"], x["name"]): x for x in snap["workloads"]}
            live_apps = {x["name"]: x for x in snap["apps"]}
            by_name = defaultdict(list)
            for x in snap["workloads"]:
                by_name[x["name"]].append(x)
            for w in inv["workloads"]:
                if not w["namespace"] and len(by_name.get(w["name"], [])) == 1:
                    w["namespace"] = by_name[w["name"]][0]["namespace"]
            declared = {(w["namespace"], w["name"]) for w in inv["workloads"]}
            for k, x in sorted(live_wl.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
                ours = any(inventory.registry_of(inventory.split_image(i)[0]) in (target.manifest.get("registries") or []) for i in x["images"] if i)
                if k not in declared and live.running(x) and (x.get("app") or ours):
                    src = (live_apps.get(x.get("app")) or {}).get("sources") or [{}]
                    undeclared.append({"infra": slug, "namespace": k[0], "name": k[1], "kind": x["kind"], "app": x.get("app"),
                                       "app_repo": src[0].get("repo"), "app_path": src[0].get("path"),
                                       "images": [inventory.split_image(i)[2] for i in x["images"] if i]})
                    for i in x["images"]:
                        if not i:
                            continue
                        repo, tag, key = inventory.split_image(i)
                        by_key[key]["workloads"].append({
                            "infra": slug, "kind": x["kind"], "name": k[1], "namespace": k[0], "file": f"(cluster, app {x.get('app') or '-'})",
                            "image": repo, "tag": tag, "registry": inventory.registry_of(repo), "replicas": x.get("replicas"),
                            "schedule": x.get("schedule"), "suspended": x.get("suspended"), "variant": None, "variant_of": None,
                            "apps": [x["app"]] if x.get("app") else [], "managed": bool(x.get("app")), "live": True, "undeclared": True})
        for w in inv["workloads"]:
            if snap:
                lw = live_wl.get((w["namespace"], w["name"]))
                w["managed"] = any(a in live_apps for a in w.get("apps") or [])
                w["live"] = live.running(lw) if lw else w["managed"]
                w["live_from"] = "cluster " + snap["taken_at"][:10]
            else:
                w["managed"] = bool(w.get("apps"))
                w["live"] = w["managed"] or not needs_app or not any(i["registry"] in (target.manifest.get("registries") or []) for i in w["images"])
            for img in w["images"]:
                by_key[img["key"]]["workloads"].append({
                    "infra": slug, "kind": w["kind"], "name": w["name"], "namespace": w["namespace"],
                    "file": w["file"], "image": img["image"], "tag": img["tag"], "registry": img["registry"],
                    "replicas": w.get("replicas"), "schedule": w.get("schedule"), "suspended": w.get("suspended"),
                    "variant": w.get("variant"), "variant_of": w.get("variant_of"), "apps": w.get("apps", []),
                    "managed": w["managed"], "live": w["live"]})

    own = set(target.manifest.get("registries") or [])
    if not own:
        own = {w["registry"] for e in by_key.values() if e["builders"] for w in e["workloads"]}
    hosts = _ingress_hosts(invs)
    for key, e in by_key.items():
        for w in e["workloads"]:
            w["hosts"] = sorted(hosts.get((w["infra"], w["namespace"]), set()))

    deploy = {"generated_at": now(), "own_registries": sorted(own), "images": {}, "undeclared_live": undeclared}
    for key in sorted(by_key):
        e = by_key[key]
        ours = bool(e["builders"]) or any(w["registry"] in own for w in e["workloads"])
        deploy["images"][key] = {"ours": ours, **e}

    bridges = _bridges(target, invs, deploy, services)
    gaps = _gaps(target, deploy, invs)
    return deploy, bridges, gaps, invs


def _ingress_hosts(invs):
    out = defaultdict(set)
    for slug, inv in invs.items():
        for ing in inv["ingresses"]:
            out[(slug, ing["namespace"])].update(ing["hosts"])
    return out


def _bridges(target, invs, deploy, services):
    owner = {}
    for key, e in deploy["images"].items():
        proj = next((b["project"] for b in e["builders"] if not b["excluded"]), None) or \
            next((b["project"] for b in e["builders"]), None)
        for w in e["workloads"]:
            owner[(w["infra"], w["namespace"], w["name"])] = proj

    nodes, edges = {}, []

    def node(nid, **attrs):
        nodes.setdefault(nid, {"id": nid, **attrs})
        return nid

    for slug, inv in invs.items():
        svc_index = {(s["namespace"], s["name"]): s for s in inv["services"]}
        ing_index = {h: i for i in inv["ingresses"] for h in i["hosts"]}
        wl_by_ns = defaultdict(list)
        for w in inv["workloads"]:
            wl_by_ns[w["namespace"]].append(w)

        def resolve(ns, svc):
            s = svc_index.get((ns, svc))
            if s and s["selector"]:
                for w in wl_by_ns.get(ns, []):
                    if all(w["labels"].get(k) == v for k, v in s["selector"].items()):
                        return node(w["name"], kind="workload", namespace=ns, project=owner.get((slug, ns, w["name"])))
            return node(f"{ns}/{svc}", kind="service", namespace=ns)

        for w in inv["workloads"]:
            src = node(w["name"], kind="workload", namespace=w["namespace"], project=owner.get((slug, w["namespace"], w["name"])))
            for link in w["links"]:
                targets = set()
                for m in SVC_HOST.finditer(link["value"]):
                    targets.add(resolve(m.group(3), m.group(1).split(".")[-1]))
                if SELFISH.search(link["name"]):
                    continue
                for part in re.split(r"[,\s]+", link["value"]):
                    if "://" not in part or ".svc" in part:
                        continue
                    host = urlparse(part).hostname or ""
                    if not host or host in ("localhost", "0.0.0.0") or host.startswith("127."):
                        continue
                    if host in ing_index:
                        ing = ing_index[host]
                        for b in ing["backends"]:
                            targets.add(resolve(ing["namespace"], b))
                    elif "." not in host:
                        targets.add(resolve(w["namespace"], host))
                    else:
                        targets.add(node(host, kind="external"))
                for t in targets:
                    if t != src:
                        edges.append({"from": src, "to": t, "via": _via(link), "name": link["name"],
                                      "evidence": [f"{slug}:{w['file']}"], "confidence": "config"})

    unmatched = []
    ports = {p.slug: p.load_json("ports.json", {}) or {} for p in services}
    workload_names = {n["id"] for n in nodes.values() if n.get("kind") == "workload"}

    def comp(slug, port):
        c = port.get("component") or slug
        return node(c, kind="workload" if c in workload_names else "component", project=slug)

    binds = defaultdict(set)
    for slug, pj in ports.items():
        for bnd in pj.get("binds") or []:
            q = bnd["queue"] if bnd["queue"].startswith("exchange:") else "queue:" + bnd["queue"].removeprefix("queue:")
            binds[(bnd.get("via", "rabbitmq"), "exchange:" + bnd["exchange"].removeprefix("exchange:"))].add((q, f"{slug}:{bnd.get('evidence')}"))

    def reach(via, name, seen):
        """Queues reachable from an exchange, following exchange-to-exchange binds."""
        for dest, ev in binds.get((via, name), ()):
            if dest in seen:
                continue
            seen.add(dest)
            if dest.startswith("exchange:"):
                yield from reach(via, dest, seen)
            else:
                yield dest, ev

    for slug, pj in ports.items():
        extra = []
        for port in pj.get("produces") or []:
            for q, ev in reach(port.get("via"), port.get("name"), set()):
                extra.append({**port, "name": q, "bound_by": ev})
        pj["produces"] = (pj.get("produces") or []) + extra

    for out_dir, in_dir in PORT_JOINS:
        index = defaultdict(list)
        for slug, pj in ports.items():
            for port in pj.get(in_dir) or []:
                index[(port.get("via"), port.get("name"))].append((slug, port))
        for slug, pj in ports.items():
            for port in pj.get(out_dir) or []:
                k = (port.get("via"), port.get("name"))
                matches = [m for m in index.get(k, []) if (m[0], m[1].get("component")) != (slug, port.get("component"))]
                for other, oport in matches:
                    a, b = (comp(slug, port), comp(other, oport))
                    edges.append({"from": a, "to": b, "via": k[0], "name": k[1],
                                  "evidence": [f"{slug}:{port.get('evidence')}", f"{other}:{oport.get('evidence')}"] + ([port["bound_by"]] if port.get("bound_by") else []),
                                  "confidence": "code"})
                if not matches and out_dir == "produces" and not port.get("bound_by") and not binds.get(k):
                    unmatched.append({"project": slug, "component": port.get("component"), "direction": out_dir, **port})
            # calls name the callee first: "<component or project> METHOD /path"
            for port in pj.get("calls") or []:
                if port.get("via") not in ("http", "grpc"):
                    continue
                callee, _, route = (port.get("name") or "").partition(" ")
                served = [(s, sp) for s, spj in ports.items() for sp in spj.get("serves") or []
                          if (sp.get("component") or s) == callee or (s == callee and not sp.get("component"))]
                hit = [x for x in served if x[1].get("name") == route.strip()]
                if served or callee in workload_names:
                    to = comp(hit[0][0], hit[0][1]) if hit else (comp(served[0][0], served[0][1]) if served else node(callee, kind="workload"))
                    edges.append({"from": comp(slug, port), "to": to, "via": port["via"], "name": route.strip() or port["name"],
                                  "evidence": [f"{slug}:{port.get('evidence')}"] + ([f"{hit[0][0]}:{hit[0][1].get('evidence')}"] if hit else []),
                                  "confidence": "code" if hit else "code-caller"})
                elif "." in callee:
                    edges.append({"from": comp(slug, port), "to": node(callee, kind="external"), "via": port["via"], "name": route.strip(),
                                  "evidence": [f"{slug}:{port.get('evidence')}"], "confidence": "code-caller"})
                elif callee and not callee.startswith("env:"):
                    edges.append({"from": comp(slug, port), "to": node(callee, kind="unknown"), "via": port["via"], "name": route.strip(),
                                  "evidence": [f"{slug}:{port.get('evidence')}"], "confidence": "code-caller"})
                else:
                    unmatched.append({"project": slug, "component": port.get("component"), "direction": "calls", **port})
    merged = {}
    for e in edges:
        k = (e["from"], e["to"], e["via"], e["name"])
        if k in merged:
            merged[k]["evidence"] = sorted(set(merged[k]["evidence"]) | set(e["evidence"]))
        else:
            merged[k] = e
    uniq = list(merged.values())
    return {"generated_at": now(), "nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": uniq,
            "unmatched_ports": unmatched}


def _via(link):
    v, n = link["value"].lower(), link["name"].upper()
    for scheme in ("amqp", "mqtt", "redis", "postgres", "mysql", "mongodb", "nats", "kafka", "s3", "grpc"):
        if v.startswith(scheme) or scheme.upper() in n:
            return {"postgres": "postgres", "amqp": "rabbitmq"}.get(scheme, scheme)
    if "BROKER" in n:
        return "kafka"
    if v.startswith("http"):
        return "http"
    return "other"


def _gaps(target, deploy, invs):
    out = defaultdict(list)
    infra_first = next((p.slug for p in target.projects if p.kind == "infra"), None)
    if not infra_first:
        return out
    for key, e in deploy["images"].items():
        live = [w for w in e["workloads"] if w["live"]]
        in_scope = [b for b in e["builders"] if not b["excluded"]]
        if in_scope and not live:
            for b in in_scope:
                out[b["project"]].append({
                    "kind": "liveness", "key": f"deploy:built-not-deployed:{key}",
                    "title": f"`{b['from']}` builds image `{key}` but no workload in the infra repos runs it. Is it deployed elsewhere, or dead?",
                    "evidence": f"{b['project']}:{b['from']}; no match in {', '.join(invs)}",
                    "default": "not deployed from the tracked infra repos; documented as inactive",
                    "affects": "1.Overview, 2.Architecture, the module doc that owns it"})
        if live and e["builders"] and not in_scope:
            b = e["builders"][0]
            out[b["project"]].append({
                "kind": "scope", "key": f"deploy:deployed-from-excluded:{key}",
                "title": f"Image `{key}` runs in prod but its source `{b['from']}` is excluded from the docs. Document it?",
                "evidence": f"{b['project']}:{b['from']}; " + ", ".join(f"{w['infra']}:{w['file']}" for w in live[:3]),
                "default": "keep excluded, list it in DEPLOY.md as running legacy code",
                "affects": "2.Architecture, map/DEPLOY.md", "blocking": True})
        if live and not e["builders"] and e["ours"]:
            w = live[0]
            out[w["infra"]].append({
                "kind": "ownership", "key": f"deploy:deployed-not-built:{key}",
                "title": f"Workload `{w['name']}` runs `{w['image']}` but no tracked project builds it. Which repo owns it?",
                "evidence": f"{w['infra']}:{w['file']}",
                "default": "owned by an untracked repo; listed as unknown source",
                "affects": "map/DEPLOY.md, REPOS.md"})
        for w in live:
            if w["replicas"] == 0 or w["suspended"]:
                out[w["infra"]].append({
                    "kind": "liveness", "key": f"deploy:scaled-down:{w['namespace']}/{w['name']}",
                    "title": f"`{w['name']}` is declared with {'replicas: 0' if w['replicas'] == 0 else 'suspend: true'}. Paused on purpose, or dead?",
                    "evidence": f"{w['infra']}:{w['file']}",
                    "default": "paused; documented as not running",
                    "affects": "map/DEPLOY.md"})
    for slug, inv in invs.items():
        for a in inv["apps"]:
            for s in a["sources"]:
                if s.get("missing"):
                    out[slug].append({
                        "kind": "liveness", "key": f"deploy:app-missing-path:{a['name']}",
                        "title": f"Argo app `{a['name']}` points to `{s['path']}`, which does not exist in this repo. Leftover app, or source lives elsewhere?",
                        "evidence": f"{slug}:{a['file']}",
                        "default": "leftover app; the service is not deployed from here",
                        "affects": "map/DEPLOY.md"})
    # a suffix is worth a question only when it cuts across workloads (`-dr` on several), not one app's own overlays
    tokens = defaultdict(lambda: {"names": set(), "first": None})
    for slug, inv in invs.items():
        for w in inv["workloads"]:
            for tok in (w.get("variant") or "").lower().split("/"):
                if tok:
                    tokens[tok]["names"].add(w["variant_of"])
                    tokens[tok]["first"] = tokens[tok]["first"] or (slug, w)
    for tok, t in sorted(tokens.items()):
        if len(t["names"]) < 2:
            continue
        slug, w = t["first"]
        out[slug].append({
            "kind": "naming", "key": f"deploy:variant-suffix:{tok}",
            "title": f"What does the variant `{tok}` mean? It appears on {len(t['names'])} workloads ({', '.join(sorted(t['names'])[:4])}).",
            "evidence": f"{slug}:{w.get('overlay') or w['file']}",
            "default": "a variant of the base workload; purpose unknown",
            "affects": "map/DEPLOY.md"})
    return out


def write(target, deploy, bridges, gaps):
    import json
    target.map_dir.mkdir(parents=True, exist_ok=True)
    (target.map_dir / "deploy.json").write_text(json.dumps(deploy, indent=2, ensure_ascii=False) + "\n")
    (target.map_dir / "bridges.yaml").write_text(yaml.safe_dump(bridges, sort_keys=False, allow_unicode=True, width=120))
    facts = target.all_facts_text()
    added = {}
    for slug, items in gaps.items():
        new = questions.add(target.project(slug), items, facts)
        if new:
            added[slug] = new
    return added
