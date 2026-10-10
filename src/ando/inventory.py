"""Extract a deploy inventory from Kubernetes YAML without a cluster or an LLM."""
import fnmatch
import re
from pathlib import Path

import yaml

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"}
SECRETISH = re.compile(r"(PASS|SECRET|TOKEN|PRIVATE|CREDENTIAL|API_?KEY|ACCESS_?KEY|AUTH)", re.I)
LINKISH_NAME = re.compile(r"(URL|URI|HOST|ENDPOINT|BROKER|ADDR|TOPIC|QUEUE|EXCHANGE|STREAM|SUBJECT|BUCKET|CONSUMER_GROUP|_GROUP$)", re.I)
LINKISH_VALUE = re.compile(r"(^[a-z][a-z0-9+.-]*://)|(\.svc(\.|:|$|/))|(^[\w.-]+:\d{2,5}(,|$))")
USERINFO = re.compile(r"(://)[^/@\s]+@")


def split_image(image):
    """registry/repo:tag@digest -> (repo_without_tag, tag, key) where key is the last path segment."""
    digest = None
    if "@" in image:
        image, digest = image.split("@", 1)
    tag = None
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        image, tag = image.rsplit(":", 1)
    return image, tag or digest, image.rsplit("/", 1)[-1]


def registry_of(repo):
    first = repo.split("/", 1)[0]
    if "/" in repo and ("." in first or ":" in first or first == "localhost"):
        return first
    return "docker.io"


def _excluded(rel, excludes):
    return any(fnmatch.fnmatch(rel, ex) or rel.startswith(ex.rstrip("*").rstrip("/") + "/") for ex in excludes)


def _kustomizations(root, files):
    """Map yaml file -> list of {namespace, images, kdir} from the kustomizations that include it; plus the set of patch files."""
    ctx, patches = {}, set()
    kfiles = [f for f in files if Path(f).name in ("kustomization.yaml", "kustomization.yml", "Kustomization")]

    def resolve(kdir, seen):
        kf = next((kdir / n for n in ("kustomization.yaml", "kustomization.yml", "Kustomization") if (kdir / n).exists()), None)
        if not kf or kf in seen:
            return {"files": [], "namespace": None, "images": []}
        seen.add(kf)
        pre, suf = "", ""
        try:
            k = yaml.safe_load(kf.read_text()) or {}
        except yaml.YAMLError:
            return {"files": [], "namespace": None, "images": []}
        pre, suf = k.get("namePrefix") or "", k.get("nameSuffix") or ""
        for pt in (k.get("patches") or []) + (k.get("patchesStrategicMerge") or []) + (k.get("patchesJson6902") or []):
            pp = pt if isinstance(pt, str) else (pt or {}).get("path")
            if pp and "\n" not in pp:
                patches.add((kdir / pp).resolve())
        out = []
        for r in (k.get("resources") or []) + (k.get("bases") or []) + (k.get("components") or []):
            if not isinstance(r, str) or "://" in r or r.startswith("github.com/"):
                continue
            p = (kdir / r).resolve()
            if p.is_dir():
                out += [(f, pre + fp, fs + suf) for f, fp, fs in resolve(p, seen)["files"]]
            elif p.exists():
                out.append((p, pre, suf))
        return {"files": out, "namespace": k.get("namespace"), "images": k.get("images") or []}

    for kf in kfiles:
        kdir = (root / kf).parent.resolve()
        r = resolve(kdir, set())
        for f, pre, suf in r["files"]:
            ctx.setdefault(f, []).append({"namespace": r["namespace"], "images": r["images"], "kdir": str(kdir.relative_to(root.resolve())),
                                          "prefix": pre, "suffix": suf})
    return ctx, patches


def _override(image, overrides):
    repo, tag, _ = split_image(image)
    for o in overrides:
        if o.get("name") in (repo, split_image(repo)[2]):
            repo = o.get("newName", repo)
            if o.get("digest"):
                return f"{repo}@{o['digest']}"
            tag = str(o.get("newTag", tag)) if o.get("newTag") is not None else tag
    return f"{repo}:{tag}" if tag else repo


def _env(containers):
    names, links, secrets, configmaps = [], [], set(), set()
    for c in containers:
        for e in c.get("env") or []:
            n = e.get("name")
            names.append(n)
            vf = e.get("valueFrom") or {}
            if "secretKeyRef" in vf:
                secrets.add(vf["secretKeyRef"].get("name"))
                continue
            if "configMapKeyRef" in vf:
                configmaps.add(vf["configMapKeyRef"].get("name"))
                continue
            v = e.get("value")
            if not isinstance(v, str) or not v or SECRETISH.search(n or ""):
                continue
            if LINKISH_VALUE.search(v) or LINKISH_NAME.search(n or ""):
                links.append({"name": n, "value": USERINFO.sub(r"\1", v)[:300]})
        for ef in c.get("envFrom") or []:
            if "secretRef" in ef:
                secrets.add(ef["secretRef"].get("name"))
            if "configMapRef" in ef:
                configmaps.add(ef["configMapRef"].get("name"))
    return names, links, sorted(s for s in secrets if s), sorted(c for c in configmaps if c)


def _pod_spec(doc):
    spec = doc.get("spec") or {}
    if doc["kind"] == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec") or {})
    return ((spec.get("template") or {}).get("spec") or {})


def extract(root, excludes=(), repo_name=None):
    root = Path(root)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.suffix in (".yaml", ".yml"))
    files = [f for f in files if not _excluded(f, excludes)]
    kctx, patches = _kustomizations(root, files)
    inv = {"workloads": [], "services": [], "ingresses": [], "apps": [], "namespaces": [], "unparsed": []}
    for rel in files:
        path = (root / rel).resolve()
        if path in patches:
            continue
        try:
            docs = [d for d in yaml.safe_load_all(path.read_text(errors="replace")) if isinstance(d, dict) and d.get("kind")]
        except yaml.YAMLError:
            inv["unparsed"].append(rel)
            continue
        contexts = kctx.get(path) or [{"namespace": None, "images": [], "kdir": None}]
        for doc in docs:
            for c in contexts:
                _collect(inv, doc, rel, c)
    _apply_app_namespaces(inv)
    _dangling_apps(inv, root, repo_name)
    _mark_variants(inv)
    for k in ("workloads", "services", "ingresses", "apps"):
        inv[k] = _dedupe(inv[k])
    inv["namespaces"] = sorted(set(inv["namespaces"]))
    return inv


def _collect(inv, doc, rel, ctx):
    kind, meta = doc["kind"], doc.get("metadata") or {}
    name = meta.get("name")
    if name and kind != "Namespace":
        name = ctx.get("prefix", "") + name + ctx.get("suffix", "")
    ns = meta.get("namespace") or ctx["namespace"]
    base = {"name": name, "namespace": ns, "file": rel, "kustomization": ctx["kdir"], "base_name": meta.get("name")}
    kdir = ctx["kdir"]
    if kdir and not (rel.startswith(kdir + "/") or kdir == "."):
        base["overlay"] = kdir
    if kind in WORKLOAD_KINDS:
        pod = _pod_spec(doc)
        containers = (pod.get("initContainers") or []) + (pod.get("containers") or [])
        names, links, secrets, cms = _env(containers)
        images = []
        for c in containers:
            if c.get("image"):
                img = _override(c["image"], ctx["images"])
                repo, tag, key = split_image(img)
                images.append({"container": c.get("name"), "image": repo, "tag": tag, "key": key,
                               "registry": registry_of(repo), "init": c in (pod.get("initContainers") or [])})
        res = {}
        for c in pod.get("containers") or []:
            if c.get("resources"):
                res[c.get("name")] = c["resources"]
        spec = doc.get("spec") or {}
        inv["workloads"].append({**base, "kind": kind, "images": images,
                                 "replicas": spec.get("replicas"), "schedule": spec.get("schedule"),
                                 "suspended": spec.get("suspend"), "resources": res,
                                 "env": sorted(set(n for n in names if n)), "links": links,
                                 "secret_refs": secrets, "configmap_refs": cms,
                                 "labels": ((spec.get("template") or {}).get("metadata") or {}).get("labels") or meta.get("labels") or {}})
    elif kind == "Service":
        spec = doc.get("spec") or {}
        inv["services"].append({**base, "type": spec.get("type"), "selector": spec.get("selector") or {},
                                "ports": [p.get("port") for p in spec.get("ports") or []],
                                "external": spec.get("externalName")})
    elif kind == "Ingress":
        hosts, backends = [], []
        for r in (doc.get("spec") or {}).get("rules") or []:
            if r.get("host"):
                hosts.append(r["host"])
            for p in ((r.get("http") or {}).get("paths") or []):
                svc = ((p.get("backend") or {}).get("service") or {}).get("name") or (p.get("backend") or {}).get("serviceName")
                if svc:
                    backends.append(svc)
        inv["ingresses"].append({**base, "hosts": sorted(set(hosts)), "backends": sorted(set(backends))})
    elif kind == "Application" and str(doc.get("apiVersion", "")).startswith("argoproj.io"):
        spec = doc.get("spec") or {}
        srcs = spec.get("sources") or ([spec["source"]] if spec.get("source") else [])
        dest = spec.get("destination") or {}
        inv["apps"].append({**base, "project": spec.get("project"),
                            "sources": [{"repo": s.get("repoURL"), "path": s.get("path"), "chart": s.get("chart"),
                                         "revision": s.get("targetRevision")} for s in srcs],
                            "dest_namespace": dest.get("namespace"), "dest_server": dest.get("server") or dest.get("name"),
                            "auto_sync": bool((spec.get("syncPolicy") or {}).get("automated"))})
    elif kind == "Namespace" and name:
        inv["namespaces"].append(name)


def _apply_app_namespaces(inv):
    """Workloads without a namespace inherit it from the Argo app whose source path contains their file."""
    paths = []
    for a in inv["apps"]:
        for s in a["sources"]:
            if s.get("path") and a.get("dest_namespace"):
                paths.append((s["path"].strip("/").rstrip("/") + "/", a["dest_namespace"], a["name"]))
    for kind in ("workloads", "services", "ingresses"):
        for w in inv[kind]:
            hits = [p for p in paths if w["file"].startswith(p[0]) or (w.get("kustomization") and (w["kustomization"] + "/").startswith(p[0]))]
            if hits:
                best = max(hits, key=lambda p: len(p[0]))
                w["apps"] = sorted({h[2] for h in hits})
                if not w["namespace"]:
                    w["namespace"] = best[1]
        # a base only reached through managed overlays is not itself a separate, disabled deployment
        managed_files = {w["file"] for w in inv[kind] if w.get("apps")}
        inv[kind] = [w for w in inv[kind] if w.get("apps") or w["file"] not in managed_files]


def _dangling_apps(inv, root, repo_name):
    """Argo apps whose source path should be in this repo but is not."""
    for a in inv["apps"]:
        for s in a["sources"]:
            p = (s.get("path") or "").strip("/")
            same_repo = repo_name and re.sub(r"\.git$", "", (s.get("repo") or "").rstrip("/")).endswith("/" + repo_name)
            if p and same_repo and not s.get("chart") and not (Path(root) / p).exists():
                s["missing"] = True


def _mark_variants(inv):
    """`foo-dr` next to `foo`, or an overlay dir over a shared base: record variant + suffix, so each suffix is asked once."""
    names = {w["name"] for w in inv["workloads"]}
    for w in inv["workloads"]:
        if w.get("overlay"):
            tail = w["overlay"].split("/")
            bn = w.get("base_name") or w["name"]
            label = tail[-1][len(bn) + 1:] if tail[-1].startswith(bn + "-") else "/".join(
                t for t in tail if t not in w["file"].split("/"))
            w["variant_of"], w["variant"] = bn, label or tail[-1]
            continue
        parts = w["name"].split("-")
        for i in range(len(parts) - 1, 0, -1):
            base = "-".join(parts[:i])
            if base in names:
                w["variant_of"], w["variant"] = base, "-".join(parts[i:])
                break


def _dedupe(items):
    seen, out = set(), []
    for i in items:
        k = (i.get("kind"), i.get("namespace"), i.get("name"), i.get("file"), i.get("kustomization"))
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out
