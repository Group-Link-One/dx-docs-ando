import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from . import checks, live, mapjoin, questions, render, reports, site
from .gitx import GitError, sha256_file
from .project import MANIFEST, VERSION, Target, find_target, now

PATCH_BUDGET = 2000
SKILL_PROMPT = "Use the ando skill. Mode: {mode}. Project: {slug}. Target: {target}. Bundle: {bundle}."


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ando", description="Keep architecture docs for many repos in one place.")
    ap.add_argument("--target", help="docs target dir (default: nearest ando.yaml upwards, or $ANDO_TARGET)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create ando.yaml and dirs")
    s.add_argument("dir", nargs="?", default=".")

    s = sub.add_parser("add", help="add a project to the manifest")
    s.add_argument("slug")
    s.add_argument("--repo", help="required unless --kind external")
    s.add_argument("--branch")
    s.add_argument("--path", default=".")
    s.add_argument("--kind", default="service", choices=["service", "infra", "lib", "external"])
    s.add_argument("--exclude", action="append", default=[])

    s = sub.add_parser("import", help="adopt existing docs (e.g. a Terrain human/ dir) at a known baseline")
    s.add_argument("src")
    s.add_argument("--slug", required=True)
    s.add_argument("--baseline", required=True, help="commit the docs reflect")

    s = sub.add_parser("status", help="baseline vs branch head per project; rewrites REPOS.md (no LLM)")
    s.add_argument("slugs", nargs="*")
    s.add_argument("--fetch", action="store_true")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("map", help="infra inventory + builds + ports joins; deploy and bridge maps (no LLM)")
    s.add_argument("--live", action="store_true", help="snapshot infra projects with `live_context` via read-only kubectl first")

    s = sub.add_parser("prepare", help="decide the mode and write the context bundle for the skill")
    s.add_argument("slug")
    s.add_argument("--mode", choices=["discover", "generate", "update"])

    s = sub.add_parser("stamp", help="after a successful run: check, then move the baseline")
    s.add_argument("slug")
    s.add_argument("--sha", help="default: the head recorded by prepare")
    s.add_argument("--mode", default="update")

    s = sub.add_parser("check", help="deterministic validation")
    s.add_argument("slugs", nargs="*")
    s.add_argument("--quiet", action="store_true", help="only errors")
    s.add_argument("--head", action="store_true", help="resolve citations at the head from the last prepare (use mid-run)")

    s = sub.add_parser("questions", help="list open questions")
    s.add_argument("slugs", nargs="*")

    s = sub.add_parser("site", help="build a static site from the docs (needs `markdown`)")
    s.add_argument("--out", default="site")
    s.add_argument("--mermaid-url", default=site.MERMAID, help="Mermaid script URL (point to a vendored copy to work offline)")
    s.add_argument("--no-status", action="store_true", help="skip git lookups; status comes from the saved baselines only")

    s = sub.add_parser("serve", help="live preview of the site, rebuilt when the docs change")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--mermaid-url", default=site.MERMAID)
    s.add_argument("--no-status", action="store_true")

    s = sub.add_parser("run", help="status, prepare, claude -p, stamp, map, check")
    s.add_argument("slugs", nargs="*")
    s.add_argument("--ci", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--fetch", action="store_true")
    s.add_argument("--allow-lookups", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "init":
        return cmd_init(Path(a.dir))
    target = Target(find_target(a.target))
    rc = globals()[f"cmd_{a.cmd}"](target, a)
    return rc if isinstance(rc, int) else 0


def cmd_init(d):
    d.mkdir(parents=True, exist_ok=True)
    m = d / MANIFEST
    if not m.exists():
        m.write_text("target: .\nlanguage: en  # free text, passed to the model as language and tone\n"
                     "defaults:\n  max_changed_files: 400\n  docs_in: [README.md, docs/**]\n"
                     "# registries: [registry.example.com]  # images from these count as ours\nprojects: []\n")
    for sub in ("facts", "map"):
        (d / sub).mkdir(exist_ok=True)
    gi = d / ".gitignore"
    line = "*/.ando/scratch/\n"
    if not gi.exists() or line not in gi.read_text():
        with gi.open("a") as f:
            f.write(line)
    print(f"initialized {d.resolve()}")


def cmd_add(target, a):
    spec = {"slug": a.slug, "repo": a.repo} if a.repo else {"slug": a.slug}
    if a.kind != "service":
        spec["kind"] = a.kind
    if a.branch:
        spec["branch"] = a.branch
    if a.path != ".":
        spec["path"] = a.path
    if a.exclude:
        spec["exclude"] = a.exclude
    if not a.repo and a.kind != "external":
        raise SystemExit("--repo is required")
    if any(p.slug == a.slug for p in target.projects):
        raise SystemExit(f"{a.slug} already in manifest")
    text = target.manifest_path.read_text().replace("projects: []", "projects:")
    item = yaml.safe_dump([spec], sort_keys=False, default_flow_style=False)
    text = text.rstrip() + "\n" + "".join("  " + l + "\n" for l in item.splitlines())
    target.manifest_path.write_text(text)
    print(f"added {a.slug}")


def _stamp_line(p, base):
    return f"Reflects {p.slug}@{base['sha'][:7]} ({p.spec.get('branch') or 'HEAD'}, {base['date'][:10]})."


def _commit_state(p, sha, mode, result="ok"):
    state = p.load_state() or p.new_state()
    base = p.repo.commit_info(sha)
    state["baseline"] = base
    state["last_run"] = {"mode": mode, "at": now(), "ando": VERSION, "result": result}
    if p.kind != "infra":
        state["modules"] = p.modules_on_disk()
    for doc in p.doc_files():
        render.stamp(doc, _stamp_line(p, base))
    state["docs"] = {str(d.relative_to(p.dir)): sha256_file(d) for d in p.doc_files()}
    p.save_state(state)
    return state


def cmd_import(target, a):
    p = target.project(a.slug)
    _need_repo(p)
    p.repo.ensure()
    src = Path(a.src).resolve()
    if src != p.dir.resolve():
        shutil.copytree(src, p.dir, dirs_exist_ok=True)
    sha = p.repo.resolve(a.baseline)
    state = _commit_state(p, sha, "import")
    print(f"{p.slug}: imported {len(state['docs'])} docs at {sha[:8]}, {len(state['modules'])} modules")


def _need_repo(p):
    if p.kind == "external":
        raise SystemExit(f"{p.slug} is external: it has no repo; edit its .ando/ports.json instead")


def _short(names, n=6):
    if not names:
        return "-"
    return ", ".join(names[:n]) + (f" (+{len(names) - n} more)" if len(names) > n else "")


def project_status(target, p, fetch=False, deploy=None):
    if p.kind == "external":
        return {"slug": p.slug, "kind": p.kind, "repo": "-", "branch": "-", "path": "-", "baseline": "-", "behind": "-",
                "status": "external", "head": None, "deployed": "-", "questions": len(questions.open_questions(p))}
    state = p.load_state()
    row = {"slug": p.slug, "kind": p.kind, "repo": p.spec["repo"], "branch": p.spec.get("branch") or "HEAD",
           "path": p.spec.get("path", "."), "baseline": "-", "behind": "-", "status": "never", "head": None,
           "deployed": _short(sorted(reports.deployed_as(deploy, p.slug))),
           "questions": len(questions.open_questions(p))}
    try:
        p.repo.ensure(fetch=fetch)
        row["head"] = p.repo.head()
    except (GitError, subprocess.CalledProcessError) as e:
        row["status"] = f"error: {e}"[:80]
        return row
    base = (state or {}).get("baseline")
    if base:
        row["baseline"] = f"{base['sha'][:8]} ({base['date'][:10]})"
        if not p.repo.has(base["sha"]):
            row["status"], row["behind"] = "unreachable", "?"
        else:
            row["behind"] = p.repo.behind(base["sha"], row["head"])
            row["status"] = "fresh" if row["behind"] == 0 else "stale"
        if (state.get("last_run") or {}).get("result") == "failed":
            row["status"] = "failed"
    return row


def _deploy(target):
    p = target.map_dir / "deploy.json"
    return json.loads(p.read_text()) if p.exists() else None


def _site_rows(target, a):
    deploy = _deploy(target)
    rows = []
    for p in target.projects:
        if a.no_status:
            st = p.load_state() or {}
            b = st.get("baseline")
            rows.append({"slug": p.slug, "kind": p.kind, "branch": p.spec.get("branch") or "-", "baseline": f"{b['sha'][:8]} ({b['date'][:10]})" if b else "-",
                         "behind": "-", "status": "external" if p.kind == "external" else "saved", "deployed": _short(sorted(reports.deployed_as(deploy, p.slug))),
                         "questions": len(questions.open_questions(p))})
        else:
            rows.append(project_status(target, p, False, deploy))
    return rows


def cmd_site(target, a):
    out = site.build(target, a.out, _site_rows(target, a), a.mermaid_url)
    print(f"site written to {out}/index.html")


def cmd_serve(target, a):
    site.serve(target, _site_rows(target, a), a.port, a.host, a.mermaid_url)


def cmd_status(target, a):
    deploy = _deploy(target)
    rows = [project_status(target, p, a.fetch, deploy) for p in target.select(a.slugs)]
    if not a.slugs:
        reports.repos(target, rows)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['slug']:<22} {r['status']:<12} baseline {r['baseline']:<22} behind {str(r['behind']):<5} questions {r['questions']}")
    return rows


def cmd_map(target, a):
    if getattr(a, "live", False):
        for p in target.projects:
            if p.kind == "infra" and p.spec.get("live_context"):
                snap = live.snapshot(p.spec["live_context"])
                p.save_json("live.json", snap)
                print(f"{p.slug}: live snapshot from {snap['context']}: {len(snap['workloads'])} workloads, {len(snap['apps'])} Argo apps")
    shas = {}
    for p in target.projects:
        if p.kind == "external":
            continue
        p.repo.ensure()
        base = ((p.load_state() or {}).get("baseline") or {}).get("sha")
        shas[p.slug] = p.repo.head() if p.kind == "infra" or not base else base
    deploy, bridges, gaps, invs = mapjoin.build(target, shas)
    added = mapjoin.write(target, deploy, bridges, gaps)
    reports.deploy_map(target, deploy)
    reports.bridges_map(target, bridges)
    for slug, inv in invs.items():
        reports.infra_deploy(target.project(slug), inv)
    n_wl = sum(len(i["workloads"]) for i in invs.values())
    print(f"inventory: {n_wl} workloads in {len(invs)} infra project(s); images: {len(deploy['images'])}; "
          f"edges: {len(bridges['edges'])}; unmatched ports: {len(bridges['unmatched_ports'])}")
    for slug, qs in added.items():
        print(f"  {slug}: +{len(qs)} question(s)")
    reports.repos(target, [project_status(target, p, False, deploy) for p in target.projects])


def _classify(p, rows):
    """Split the diff: pure in-scope renames go to sed; renames crossing the exclude line become A or D."""
    from .mapjoin import _glob
    ex = p.spec.get("exclude") or []
    out_of_scope = lambda path: any(_glob(path, e) or path.startswith(e.rstrip("*").rstrip("/") + "/") for e in ex)
    renames, model = [], []
    for r in rows:
        st, paths = r["status"], r["paths"]
        if st.startswith("R"):
            old, new = paths
            if out_of_scope(new):
                model.append({"status": "D", "paths": [old], "note": f"moved out of scope to {new}"})
            elif out_of_scope(old):
                model.append({"status": "A", "paths": [new], "note": f"moved into scope from {old}"})
            elif st == "R100":
                renames.append((old, new))
            else:
                model.append(r)
        else:
            model.append(r)
    return renames, model


def _apply_renames(p, renames):
    touched = set()
    for doc in p.doc_files():
        text = orig = doc.read_text()
        for old, new in renames:
            text = text.replace(old, new)
        if text != orig:
            doc.write_text(text)
            touched.add(str(doc.relative_to(p.dir)))
    return sorted(touched)


def cmd_prepare(target, a):
    p = target.project(a.slug)
    _need_repo(p)
    p.repo.ensure()
    state = p.load_state()
    head = p.repo.head()
    base = ((state or {}).get("baseline") or {}).get("sha")
    run_dir = p.meta / "scratch" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"slug": p.slug, "kind": p.kind, "head": head, "base": base, "language": p.language(),
              "target": str(target.root), "docs_dir": str(p.dir)}
    rows, renames, model_rows = [], [], []
    if a.mode:
        mode = a.mode
    elif not state or not base or not p.doc_files():
        mode = "discover"
    elif not p.repo.has(base):
        mode = "generate"
    else:
        rows = p.repo.name_status(base, head)
        renames, model_rows = _classify(p, rows)
        if not model_rows:
            mode = "noop"
        elif len(model_rows) > int(p.spec.get("max_changed_files") or 400):
            mode = "ask"
        else:
            mode = "update" if p.kind != "infra" else "inventory"
    bundle["mode"] = mode
    if renames:
        bundle["renamed_in_docs"] = _apply_renames(p, renames)
        bundle["renames"] = renames
    bundle["snapshot"] = str(p.repo.snapshot(p.slug, head))
    before = run_dir / "before"
    shutil.rmtree(before, ignore_errors=True)
    for d in p.doc_files():
        dest = before / d.relative_to(p.dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(d, dest)
    bundle["known_errors"] = sorted({_err_key(f) for f in checks.run(target, [p], shas={p.slug: head}) if f[0] == "error"})
    bundle["changes"] = model_rows
    md = [f"# ando bundle: {p.slug} ({mode})", "",
          f"- head: `{head}`", f"- baseline: `{base}`", f"- snapshot (read code here): `{bundle['snapshot']}`",
          f"- docs: `{p.dir}`", f"- language: {p.language()}", ""]
    if renames:
        md += ["## Pure renames already applied to the docs by the runner", ""] + [f"- `{o}` -> `{n}`" for o, n in renames] + [""]
    if base and mode in ("update", "inventory", "ask"):
        log = p.repo.log(base, head)
        md += ["## Commits since baseline", ""] + [f"- {l}" for l in log[:80]] + ([f"- ... {len(log) - 80} more"] if len(log) > 80 else []) + [""]
    if model_rows:
        md += ["## Changed files", ""] + [f"- {r['status']} `{' -> '.join(r['paths'])}`" + (f" ({r['note']})" if r.get("note") else "") for r in model_rows] + [""]
        md += ["## Patches", ""] + _patches(p, base, head, model_rows)
    facts = target.facts_text(p.slug)
    md += ["## Facts (override the code)", "", facts or "None yet.", ""]
    qs = questions.open_questions(p)
    md += ["## Open questions", ""] + ([f"- {q['id']} [{q['kind']}] {q['title']} (default: {q.get('default if unanswered', '-')})" for q in qs] or ["None."]) + [""]
    ports = p.load_json("ports.json")
    md += ["## ports.json", "", "```json", json.dumps(ports, indent=2) if ports else "{}", "```", ""]
    (run_dir / "bundle.md").write_text("\n".join(md))
    (run_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))
    print(json.dumps({k: bundle[k] for k in ("slug", "mode", "base", "head")} | {"changed": len(model_rows), "renames": len(renames),
                      "bundle": str(run_dir / "bundle.md")}, indent=2))
    return bundle


def _patches(p, base, head, rows):
    stats = p.repo.numstat(base, head)
    files = [r["paths"][-1] for r in rows if r["status"] != "D"]
    files.sort(key=lambda f: stats.get(f, 0))
    out, used = [], 0
    for f in files:
        n = stats.get(f, 0)
        if used + n > PATCH_BUDGET:
            out.append(f"- `{f}`: {n} changed lines (patch omitted, over budget; read the file in the snapshot)")
            continue
        out += [f"### {f}", "", "```diff", p.repo.patch(base, head, f).rstrip(), "```", ""]
        used += n
    return out


def _err_key(f):
    return f"{f[1]}|{f[2]}|{f[3]}"


def _print_findings(findings, quiet=False):
    errors = [f for f in findings if f[0] == "error"]
    for lvl, slug, f, msg in findings:
        if quiet and lvl != "error":
            continue
        print(f"{lvl:<5} {slug}:{f} {msg}")
    print(f"{len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    return errors


def cmd_check(target, a):
    shas = {}
    if getattr(a, "head", False):
        for p in target.select(a.slugs):
            b = p.meta / "scratch" / "run" / "bundle.json"
            if b.exists():
                shas[p.slug] = json.loads(b.read_text())["head"]
    errors = _print_findings(checks.run(target, target.select(a.slugs), shas=shas), a.quiet)
    return 1 if errors else 0


def cmd_stamp(target, a):
    p = target.project(a.slug)
    _need_repo(p)
    p.repo.ensure()
    run_dir = p.meta / "scratch" / "run"
    bundle = json.loads((run_dir / "bundle.json").read_text()) if (run_dir / "bundle.json").exists() else {}
    sha = a.sha or bundle.get("head") or p.repo.head()
    state = p.load_state() or {}
    known = state.get("docs") or {}
    changed = {str(d.relative_to(p.dir)) for d in p.doc_files() if known.get(str(d.relative_to(p.dir))) != sha256_file(d)}
    prev = {}
    if (run_dir / "before").exists():
        for f in (run_dir / "before").rglob("*.md"):
            prev[str(p.dir / f.relative_to(run_dir / "before"))] = f.read_text()
    findings = checks.run(target, [p], shas={p.slug: sha}, prev=prev)
    old_errors = set(bundle.get("known_errors") or [])
    gating = [f for f in findings if f[0] == "error" and _err_key(f) not in old_errors
              and (f[2] in changed or f[2] in ("", ".ando/state.json"))]
    debt = [f for f in findings if f[0] == "error" and f not in gating]
    if gating:
        _print_findings(gating)
        if state:
            state["last_run"] = {"mode": a.mode, "at": now(), "ando": VERSION, "result": "failed"}
            p.save_state(state)
        print(f"{p.slug}: baseline NOT moved")
        return 1
    _commit_state(p, sha, a.mode)
    print(f"{p.slug}: baseline -> {sha[:8]} ({len(changed)} doc(s) changed, {len(debt)} pre-existing error(s) left as debt)")


def cmd_questions(target, a):
    for p in target.select(a.slugs):
        for q in questions.open_questions(p):
            print(f"{p.slug} {q['id']} [{q['kind']}] {q['title']}")


def cmd_run(target, a):
    rows = cmd_status(target, argparse.Namespace(slugs=a.slugs, fetch=a.fetch, json=False))
    rc = 0
    for r in rows:
        if r["status"] in ("fresh", "external"):
            continue
        p = target.project(r["slug"])
        b = cmd_prepare(target, argparse.Namespace(slug=p.slug, mode=None))
        if b["mode"] == "noop":
            if not a.dry_run:
                cmd_stamp(target, argparse.Namespace(slug=p.slug, sha=b["head"], mode="noop"))
            continue
        if b["mode"] == "ask" and a.ci:
            print(f"{p.slug}: {len(b['changes'])} changed files over the limit; skipped in CI")
            continue
        prompt = SKILL_PROMPT.format(mode=b["mode"], slug=p.slug, target=target.root,
                                     bundle=p.meta / "scratch" / "run" / "bundle.md")
        if a.allow_lookups:
            prompt += " External tracker lookups allowed."
        if a.ci:
            prompt += " Non-interactive: do not ask questions, write new ones to questions.md."
        cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--add-dir", str(target.root), "--add-dir", b["snapshot"]]
        print(("DRY " if a.dry_run else "") + " ".join(cmd[:3]) + " ...")
        if a.dry_run:
            continue
        if subprocess.run(cmd).returncode != 0:
            rc = 1
            continue
        rc |= cmd_stamp(target, argparse.Namespace(slug=p.slug, sha=b["head"], mode=b["mode"])) or 0
    if not a.dry_run:
        cmd_map(target, a)
        rc |= cmd_check(target, argparse.Namespace(slugs=[], quiet=True, head=False)) or 0
    return rc


if __name__ == "__main__":
    sys.exit(main() or 0)
