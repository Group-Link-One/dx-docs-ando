import re
from pathlib import Path

STAMP_RE = re.compile(r"\n*<!-- ando:stamp -->.*\Z", re.S)


def put_block(path, name, body, header=None):
    """Replace the generated block `name` in path, creating the file (with header) if needed."""
    path = Path(path)
    begin, end = f"<!-- ando:begin {name} -->", f"<!-- ando:end {name} -->"
    block = f"{begin}\n{body.rstrip()}\n{end}"
    text = path.read_text() if path.exists() else (header.rstrip() + "\n\n" if header else "")
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if pat.search(text):
        text = pat.sub(lambda _: block, text)
    else:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def stamp(path, line):
    path = Path(path)
    text = STAMP_RE.sub("", path.read_text()).rstrip()
    path.write_text(f"{text}\n\n<!-- ando:stamp -->\n_{line}_\n")


def read_stamp(path):
    m = re.search(r"<!-- ando:stamp -->\n_(.*)_", Path(path).read_text())
    return m.group(1) if m else None


def table(headers, rows):
    esc = lambda v: str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def mermaid_id(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)
