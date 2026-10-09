import re
from datetime import date

HEAD_RE = re.compile(r"^## (Q-\d+) \[(\w[\w/-]*)\] (.*)$", re.M)


def parse(text):
    out = []
    matches = list(HEAD_RE.finditer(text))
    for i, m in enumerate(matches):
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        fields = dict(re.findall(r"^(\w[\w ]*?):\s*(.*)$", body, re.M))
        out.append({"id": m.group(1), "kind": m.group(2), "title": m.group(3).strip(), **fields})
    return out


def known_keys(*texts):
    keys = set()
    for t in texts:
        keys.update(re.findall(r"key:\s*(\S+)", t or ""))
    return keys


def add(project, items, facts_text=""):
    """Append questions not already open or answered (dedup by key). Returns the ones added."""
    path = project.meta / "questions.md"
    text = path.read_text() if path.exists() else f"# Open questions: {project.slug}\n"
    seen = known_keys(text, facts_text)
    ids = [int(q["id"][2:]) for q in parse(text)]
    ids += [int(x) for x in re.findall(r"\(Q-(\d+)", facts_text or "")]
    n = max(ids, default=0)
    added = []
    for q in items:
        if q["key"] in seen:
            continue
        n += 1
        qid = f"Q-{n:03d}"
        lines = [f"## {qid} [{q['kind']}] {q['title']}",
                 f"key: {q['key']}",
                 f"evidence: {q['evidence']}",
                 f"default if unanswered: {q['default']}",
                 f"affects: {q.get('affects', '-')}",
                 f"blocking: {'yes' if q.get('blocking') else 'no'}",
                 f"raised: {date.today().isoformat()} by ando map"]
        text = text.rstrip() + "\n\n" + "\n".join(lines) + "\n"
        seen.add(q["key"])
        added.append({**q, "id": qid})
    if added:
        project.meta.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return added


def open_questions(project):
    path = project.meta / "questions.md"
    return parse(path.read_text()) if path.exists() else []
