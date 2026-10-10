"""Read-only cluster snapshot: workload names, replicas, images and Argo apps. No env, no secrets."""
import json
import subprocess

from .project import now

WORKLOADS = "deployments,statefulsets,daemonsets,cronjobs"


def _get(context, kinds):
    p = subprocess.run(["kubectl", "--context", context, "get", kinds, "-A", "-o", "json"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"kubectl get {kinds} ({context}): {p.stderr.strip()}")
    return json.loads(p.stdout).get("items") or []


def snapshot(context):
    wl = []
    for d in _get(context, WORKLOADS):
        kind, meta, spec = d["kind"], d["metadata"], d.get("spec") or {}
        pod = ((spec.get("jobTemplate") or {}).get("spec") or spec).get("template", {}).get("spec") or {}
        wl.append({"kind": kind, "namespace": meta.get("namespace"), "name": meta.get("name"),
                   "replicas": spec.get("replicas"), "ready": (d.get("status") or {}).get("readyReplicas"),
                   "suspended": spec.get("suspend"), "schedule": spec.get("schedule"),
                   "images": [c.get("image") for c in pod.get("containers") or []],
                   "app": _app_label(meta)})
    apps = []
    try:
        items = _get(context, "applications.argoproj.io")
    except SystemExit:
        items = []
    for a in items:
        spec, st = a.get("spec") or {}, a.get("status") or {}
        srcs = spec.get("sources") or ([spec["source"]] if spec.get("source") else [])
        apps.append({"name": a["metadata"]["name"], "dest_namespace": (spec.get("destination") or {}).get("namespace"),
                     "sources": [{"repo": s.get("repoURL"), "path": s.get("path"), "chart": s.get("chart")} for s in srcs],
                     "sync": (st.get("sync") or {}).get("status"), "health": (st.get("health") or {}).get("status")})
    return {"context": context, "taken_at": now(), "workloads": wl, "apps": apps}


def _app_label(meta):
    labels = meta.get("labels") or {}
    return labels.get("argocd.argoproj.io/instance") or labels.get("app.kubernetes.io/instance")


def running(w):
    """A live workload counts as running unless scaled to zero or suspended."""
    if w["kind"] == "CronJob":
        return not w.get("suspended")
    return w.get("replicas") != 0
