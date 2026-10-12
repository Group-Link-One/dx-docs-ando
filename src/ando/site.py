"""Static site for a docs target: rendered markdown, search, bridges explorer, status and questions."""
import html
import http.server
import json
import re
import shutil
import tempfile
import threading
from pathlib import Path, PurePosixPath

import yaml

from . import questions as qmod

WEB = Path(__file__).parent / "web"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
HREF_RE = re.compile(r'href="([^"#:]+\.md)(#[^"]*)?"')
TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
FIRST = ["SYSTEM.md", "REPOS.md"]


def _md():
    try:
        import markdown
    except ImportError:
        raise SystemExit("ando site needs the `markdown` package: pip install markdown")
    return markdown


def _natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _skip(rel):
    return any(p.startswith(".") or p == "scratch" for p in rel.parts)


def sources(target):
    return sorted((p for p in target.root.rglob("*.md") if not _skip(p.relative_to(target.root))),
                  key=lambda p: _natural(p.relative_to(target.root).as_posix()))


def signature(target):
    files = sources(target) + [target.map_dir / "bridges.yaml", target.manifest_path]
    files += [p.meta / "questions.md" for p in target.projects]
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def _title(text, rel):
    m = TITLE_RE.search(text)
    return m.group(1).strip().replace("`", "") if m else rel.stem


def _plain(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"```\w*", "", text)
    return re.sub(r"[|*_`#>\[\]()]+", " ", text)


def _nav(pages, extra, cur):
    tree = {}
    for rel, title in pages:
        node = tree
        for part in rel.parent.parts:
            node = node.setdefault(part, {})
        node.setdefault("", []).append((rel, title))
    depth = len(PurePosixPath(cur).parts) - 1
    up = "../" * depth

    def link(href, label):
        c = ' class="cur"' if href == cur else ""
        return f'<li><a{c} href="{up}{href}">{html.escape(label)}</a></li>'

    def walk(node, prefix):
        out = []
        files = sorted(node.get("", []), key=lambda t: (t[0].name not in FIRST, FIRST.index(t[0].name) if t[0].name in FIRST else 0, _natural(t[0].name)))
        out += [link(rel.with_suffix(".html").as_posix(), title) for rel, title in files]
        for name in sorted((k for k in node if k), key=_natural):
            inner = walk(node[name], prefix + name + "/")
            op = " open" if cur.startswith(prefix + name + "/") else ""
            out.append(f"<li><details{op}><summary>{html.escape(name)}</summary><ul>{''.join(inner)}</ul></details></li>")
        return out

    top = walk(tree, "")
    tools = "".join(link(h, l) for h, l in extra)
    return f'<ul>{tools}</ul><hr style="border:0;border-top:1px solid var(--line)"><ul>{"".join(top)}</ul>'


def _page(title, body, nav, cur, scripts=""):
    depth = len(PurePosixPath(cur).parts) - 1
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en" data-root="{up}" data-mermaid="{MERMAID}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><link rel="stylesheet" href="{up}style.css"></head>
<body><nav id="side"><a class="brand" href="{up}index.html">Architecture docs</a>
<input id="q" type="search" placeholder="Search docs" autocomplete="off"><div id="results"></div>{nav}</nav>
<main>{body}</main><script src="{up}app.js"></script>{scripts}</body></html>"""


def _banner(rel, rows):
    slug = rel.parts[0] if len(rel.parts) > 1 else None
    row = next((r for r in rows if r["slug"] == slug), None)
    if not row:
        return ""
    st = row["status"].split(":")[0]
    behind = f", {row['behind']} commits behind" if isinstance(row["behind"], int) and row["behind"] else ""
    return (f'<div class="banner"><span class="badge {html.escape(st)}">{html.escape(st)}</span> '
            f'{html.escape(slug)}: docs baseline {html.escape(str(row["baseline"]))}{behind}.</div>')


def _slug_link(slug, first):
    href = first.get(slug)
    return f'<a href="{html.escape(href)}">{html.escape(slug)}</a>' if href else html.escape(slug)


def _status_table(rows, pages):
    first = {}
    for rel, _ in pages:
        if len(rel.parts) > 1:
            first.setdefault(rel.parts[0], rel.with_suffix(".html").as_posix())

    head = "<tr><th>Project</th><th>Kind</th><th>Branch</th><th>Baseline</th><th>Behind</th><th>Status</th><th>Deployed as</th><th>Open questions</th></tr>"
    body = "".join(
        f'<tr><td>{_slug_link(r["slug"], first)}</td><td>{r["kind"]}</td>'
        f'<td>{html.escape(str(r["branch"]))}</td><td>{html.escape(str(r["baseline"]))}</td><td>{r["behind"]}</td>'
        f'<td><span class="badge {html.escape(r["status"].split(":")[0])}">{html.escape(r["status"].split(":")[0])}</span></td>'
        f'<td>{html.escape(str(r["deployed"]))}</td><td>{r["questions"]}</td></tr>' for r in rows)
    return f"<table>{head}{body}</table>"


def _questions_page(target, bridges):
    rows = []
    for p in target.projects:
        for q in qmod.open_questions(p):
            rows.append((p.slug, q))
    out = ["<h1>Open questions</h1>"]
    if rows:
        out.append("<table><tr><th>ID</th><th>Project</th><th>Kind</th><th>Question</th><th>Evidence</th><th>Default if unanswered</th><th>Blocking</th></tr>")
        for slug, q in rows:
            out.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in (
                q["id"], slug, q["kind"], q["title"], q.get("evidence", ""), q.get("default if unanswered", ""), q.get("blocking", ""))) + "</tr>")
        out.append("</table>")
    else:
        out.append("<p>None open.</p>")
    un = (bridges or {}).get("unmatched_ports") or []
    if un:
        out.append(f"<h2>Ports with no counterpart ({len(un)})</h2><p class='muted'>Something produces, consumes, serves or calls "
                   "these and no declared peer matches them. Some are expected (see the facts).</p>"
                   "<table><tr><th>Project</th><th>Component</th><th>Direction</th><th>Via</th><th>Name</th><th>Evidence</th><th>Note</th></tr>")
        for u in un:
            out.append("<tr>" + "".join(f"<td>{html.escape(str(u.get(k, '')))}</td>" for k in (
                "project", "component", "direction", "via", "name", "evidence", "note")) + "</tr>")
        out.append("</table>")
    return "".join(out)


def build(target, out, rows, mermaid_url=MERMAID):
    markdown = _md()
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in ("style.css", "app.js", "explorer.js"):
        shutil.copy(WEB / f, out / f)
    srcs = sources(target)
    rels = {p.relative_to(target.root) for p in srcs}
    texts = {r: (target.root / r).read_text() for r in rels}
    pages = [(r, _title(texts[r], r)) for r in sorted(rels, key=lambda r: _natural(r.as_posix()))]
    bridges_path = target.map_dir / "bridges.yaml"
    bridges = yaml.safe_load(bridges_path.read_text()) if bridges_path.exists() else None
    extra = [("index.html", "Status")]
    if bridges:
        extra.append(("explorer.html", "Bridges explorer"))
    extra.append(("questions.html", "Open questions"))

    def write(rel, title, body, scripts=""):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        page = _page(title, body, _nav(pages, extra, rel), rel, scripts).replace(MERMAID, mermaid_url)
        dest.write_text(page)

    for rel in rels:
        md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
        body = md.convert(texts[rel])

        def fix(m, rel=rel):
            tgt = PurePosixPath(*rel.parent.parts, m.group(1))
            norm = PurePosixPath(*[p for p in _resolve(tgt)])
            if norm.name == "questions.md" and ".ando" in norm.parts:
                return f'href="{"../" * len(rel.parent.parts)}questions.html{m.group(2) or ""}"'
            if Path(norm.as_posix()) in rels:
                return f'href="{m.group(1)[:-3]}.html{m.group(2) or ""}"'
            return m.group(0)

        body = HREF_RE.sub(fix, body)
        write(rel.with_suffix(".html").as_posix(), _title(texts[rel], rel), _banner(rel, rows) + body)

    pending = sum(r["questions"] for r in rows)
    home = ("<h1>Architecture docs</h1><p class='muted'>Start with <a href='SYSTEM.html'>SYSTEM</a>. "
            f"{pending} open question(s): <a href='questions.html'>list</a>.</p>" if (target.root / "SYSTEM.md").exists() else
            "<h1>Architecture docs</h1>") + _status_table(rows, pages)
    write("index.html", "Architecture docs", home)
    write("questions.html", "Open questions", _questions_page(target, bridges))
    if bridges:
        data = {"nodes": bridges["nodes"], "edges": bridges["edges"]}
        (out / "bridges-data.js").write_text("window.BRIDGES=" + json.dumps(data) + ";")
        body = ("<h1>Bridges explorer</h1><p class='muted'>Pick a node to see who feeds it and what it feeds. "
                "Every edge comes from <code>map/bridges.yaml</code>.</p><input id='sel' list='nodes' placeholder='Type a node name' autocomplete='off'>"
                "<datalist id='nodes'></datalist><div id='out'></div>")
        write("explorer.html", "Bridges explorer", body, '<script src="bridges-data.js"></script><script src="explorer.js"></script>')
    index = [{"path": r.with_suffix(".html").as_posix(), "title": t, "text": _plain(texts[r])[:20000]} for r, t in pages]
    (out / "search.js").write_text("window.SEARCH=" + json.dumps(index) + ";")
    return out


def _resolve(path):
    parts = []
    for p in path.parts:
        if p == "..":
            if parts:
                parts.pop()
        elif p != ".":
            parts.append(p)
    return parts


def serve(target, rows, port, host, mermaid_url=MERMAID):
    out = Path(tempfile.mkdtemp(prefix="ando-site-"))
    state = {"sig": None}
    lock = threading.Lock()

    def refresh():
        with lock:
            sig = signature(target)
            if sig != state["sig"]:
                build(target, out, rows, mermaid_url)
                state["sig"] = sig

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(out), **k)

        def do_GET(self):
            refresh()
            super().do_GET()

        def log_message(self, *a):
            pass

    refresh()
    srv = http.server.ThreadingHTTPServer((host, port), Handler)
    print(f"serving {target.root} at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(out, ignore_errors=True)
