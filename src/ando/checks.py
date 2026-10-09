"""Deterministic checks. Each returns a list of (level, project, file, message)."""
import math
import re
import shutil
import subprocess
from collections import Counter

from . import render
from .project import MODULES_DIR

CITE = re.compile(r"(?<![@\w.:/-])((?:[\w.+-]+/)*[\w.+-]+\.([A-Za-z][A-Za-z0-9]{0,7})):(\d+)(?:-(\d+))?")
CODE_EXT = set("""ts tsx js jsx mjs cjs go py rb rs java kt kts scala cs c h cc cpp hpp php pl pm sh bash zsh sql prisma
pgsql proto graphql gql yaml yml json toml ini cfg conf env md lua ex exs erl swift m dart vue svelte tf hcl
dockerfile mk gradle xml html css scss""".split())
RELATIVE_DATE = re.compile(r"\b(yesterday|today|tomorrow|last (week|month|year)|this (week|month)|next (week|month))\b", re.I)
EM_DASH = "\u2014"
MD_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s#]+)(#[^)]*)?\)")
DENY = re.compile(r"^\s*deny:\s*/(.+)/(i?)\s*$", re.M)
SCOPE = re.compile(r"^\s*scope:\s*(.+)$", re.M)


def _cited_paths(text):
    return [(m.group(1), int(m.group(3))) for m in CITE.finditer(text)
            if "/" in m.group(1) or m.group(2).lower() in CODE_EXT]


def run(target, projects, shas=None, prev=None):
    """shas: slug -> sha docs are checked against (default: state baseline). prev: path -> previous text for the update guard."""
    out = []
    for p in projects:
        state = p.load_state()
        sha = (shas or {}).get(p.slug) or ((state or {}).get("baseline") or {}).get("sha")
        out += _required(p, state)
        out += _citations(p, sha)
        out += _style(p, target)
        out += _facts(p, target)
        out += _stamps(p, state)
        if prev:
            out += _guard(p, prev)
        out += _mermaid(p)
        if p.kind == "infra":
            out += _secrets(p)
    out += _repos_md(target)
    out += _bridges(target)
    return out


def _required(p, state):
    out = []
    if not p.required_docs():
        return out
    if not p.dir.exists():
        return [("error", p.slug, "", "no docs directory")]
    for f in p.required_docs():
        if not (p.dir / f).exists():
            out.append(("error", p.slug, f, "required doc missing"))
    if p.kind == "service" and state and state.get("modules"):
        disk = set(p.modules_on_disk())
        want = set(state["modules"])
        for m in sorted(want - disk):
            out.append(("error", p.slug, f"{MODULES_DIR}/{m}.md", "module in state.json has no doc"))
        for m in sorted(disk - want):
            out.append(("warn", p.slug, f"{MODULES_DIR}/{m}.md", "module doc not listed in state.json"))
    return out


def _citations(p, sha):
    if not sha or p.kind == "infra":
        return []
    out = []
    base = (p.spec.get("path", ".") or ".").strip("/")
    files = set(p.repo.ls_files(sha))
    lines = {}
    for doc in p.doc_files():
        rel = doc.relative_to(p.dir)
        text = doc.read_text()
        cites = _cited_paths(text)
        if rel.parts[0] == MODULES_DIR and rel.name != "README.md" and len({c[0] for c in cites}) < 3:
            out.append(("warn", p.slug, str(rel), f"module doc cites {len({c[0] for c in cites})} distinct paths (min 3)"))
        for path, line in cites:
            path = re.sub(r"^(\.\.\.|\.\.?)/", "", path)
            full = path if base in ("", ".") else f"{base}/{path}"
            if full in files or path in files:
                cand = [full if full in files else path]
            else:
                cand = [f for f in files if f.endswith("/" + path)]
            if not cand:
                out.append(("error", p.slug, str(rel), f"cites {path}:{line}, file not found at {sha[:8]}"))
                continue
            for c in cand:
                if c not in lines:
                    lines[c] = p.repo.line_count(sha, c)
            if not any(lines[c] and line <= lines[c] for c in cand):
                most = max(lines[c] or 0 for c in cand)
                out.append(("error", p.slug, str(rel), f"cites {path}:{line}, file has {most} lines at {sha[:8]}"))
            elif len(cand) > 1:
                out.append(("warn", p.slug, str(rel), f"cites {path}:{line}, ambiguous ({len(cand)} files match); use the full path"))
    return out


def _style(p, target):
    out = []
    slugs = {x.slug for x in target.projects}
    for doc in p.doc_files():
        rel = str(doc.relative_to(p.dir))
        text = doc.read_text()
        n = text.count(EM_DASH)
        if n:
            out.append(("error", p.slug, rel, f"{n} em dash(es)"))
        for m in RELATIVE_DATE.finditer(_strip_code(text)):
            out.append(("warn", p.slug, rel, f"relative date: '{m.group(0)}'"))
        for m in MD_LINK.finditer(text):
            dest = (doc.parent / m.group(1)).resolve()
            if not dest.exists():
                out.append(("error", p.slug, rel, f"broken link: {m.group(1)}"))
    return out


def _strip_code(text):
    return re.sub(r"```.*?```|`[^`\n]*`", "", text, flags=re.S)


def _facts(p, target):
    """Facts may carry `deny: /regex/` lines: docs in the fact's scope must not match."""
    out = []
    text = target.all_facts_text()
    for block in re.split(r"\n(?=- F-\d+)", text):
        fid = re.match(r"- (F-\d+)", block)
        if not fid:
            continue
        scope = SCOPE.search(block)
        if scope and p.slug not in [s.strip() for s in scope.group(1).split(",")] and "all" not in scope.group(1):
            continue
        for pat, flag in DENY.findall(block):
            rx = re.compile(pat, re.I if flag else 0)
            for doc in p.doc_files():
                for m in rx.finditer(doc.read_text()):
                    out.append(("error", p.slug, str(doc.relative_to(p.dir)), f"contradicts {fid.group(1)}: '{m.group(0)}'"))
    return out


def _stamps(p, state):
    out = []
    base = (state or {}).get("baseline")
    if not base:
        return [("warn", p.slug, "", "no baseline in state.json")]
    if not p.repo.has(base["sha"]):
        out.append(("error", p.slug, ".ando/state.json", f"baseline {base['sha'][:8]} not found in repo"))
    for doc in p.doc_files():
        s = render.read_stamp(doc)
        if s and base["sha"][:7] not in s:
            out.append(("error", p.slug, str(doc.relative_to(p.dir)), f"stamp '{s}' does not match baseline {base['sha'][:7]}"))
    return out


def _guard(p, prev):
    out = []
    for doc in p.doc_files():
        old = prev.get(str(doc))
        if old is None:
            continue
        new = doc.read_text()
        if not new.strip():
            out.append(("error", p.slug, str(doc.relative_to(p.dir)), "doc emptied"))
        elif len(re.findall(r"^## ", new, re.M)) < len(re.findall(r"^## ", old, re.M)):
            out.append(("error", p.slug, str(doc.relative_to(p.dir)), "fewer ## headings than before"))
        elif len(new) < 0.6 * len(old):
            out.append(("error", p.slug, str(doc.relative_to(p.dir)), f"shrank to {len(new) * 100 // len(old)}% of previous length"))
    return out


def _mermaid(p):
    out = []
    has_mmdc = shutil.which("mmdc")
    for doc in p.doc_files():
        for i, block in enumerate(re.findall(r"```mermaid\n(.*?)```", doc.read_text(), re.S)):
            rel = str(doc.relative_to(p.dir))
            if has_mmdc:
                r = subprocess.run(["mmdc", "-i", "-", "-o", "/dev/null", "-q"], input=block, text=True, capture_output=True)
                if r.returncode:
                    out.append(("error", p.slug, rel, f"mermaid block {i + 1} does not parse"))
            else:
                for opener, closer in ("[]", "()", "{}"):
                    if block.count(opener) != block.count(closer):
                        out.append(("warn", p.slug, rel, f"mermaid block {i + 1}: unbalanced {opener}{closer} (install mmdc for a real parse)"))
                        break
    return out


def _entropy(s):
    c = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in c.values())


def _secrets(p):
    out = []
    files = [p.meta / "inventory.json"] + p.doc_files()
    for f in files:
        if not f.exists():
            continue
        for tok in re.findall(r"[A-Za-z0-9+/=_-]{32,}", f.read_text()):
            if _entropy(tok) > 4.5 and not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", tok):
                out.append(("error", p.slug, str(f.relative_to(p.dir)), f"possible secret: {tok[:6]}..."))
    return out


def _repos_md(target):
    path = target.root / "REPOS.md"
    if not path.exists():
        return [("warn", "-", "REPOS.md", "missing; run `ando status`")]
    text = path.read_text()
    return [("error", "-", "REPOS.md", f"no row for {p.slug}") for p in target.projects if f"| {p.slug} |" not in text]


def _bridges(target):
    import yaml
    path = target.map_dir / "bridges.yaml"
    if not path.exists():
        return []
    out = []
    data = yaml.safe_load(path.read_text()) or {}
    for e in data.get("edges") or []:
        if not e.get("evidence"):
            out.append(("error", "-", "map/bridges.yaml", f"edge {e['from']} -> {e['to']} has no evidence"))
    return out
