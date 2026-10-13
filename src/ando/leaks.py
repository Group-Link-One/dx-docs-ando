"""Secret scan over every file ando writes or publishes. Known token shapes plus a high-entropy fallback.

Findings never carry the secret itself: only the kind, file, line, a masked prefix and a fingerprint.
A reviewed false positive is accepted by listing its fingerprint under `secret_allow:` in ando.yaml.
"""
import hashlib
import math
import re
from collections import Counter

SUFFIXES = {".md", ".json", ".yaml", ".yml", ".txt", ".html"}
PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Stripe key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("credentials in URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"`]+:([^/\s@'\"`]+)@")),
    ("password value", re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token)\b[\"']?\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
]
PLACEHOLDER = re.compile(r"^[<{$*%]|^(?:x+|changeme|password|secret|example|redacted|null|none|string|undefined)$|\.\.\.|process\.env|os\.environ", re.I)
TOKEN = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")
HASHLIKE = re.compile(r"[a-f0-9]{32,64}|[A-Za-z0-9_-]*[_-][A-Za-z0-9_-]*[_-][A-Za-z0-9_-]*")


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _entropy(s):
    c = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in c.values())


def _files(root):
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if f.is_file() and f.suffix in SUFFIXES and ".git" not in rel.parts and "scratch" not in rel.parts \
                and f.name != "ando.local.yaml":
            yield f, rel


def scan_text(text):
    """Yield (line, kind, value) for each suspected secret in text."""
    for n, line in enumerate(text.splitlines(), 1):
        hit = False
        for kind, rx in PATTERNS:
            for m in rx.finditer(line):
                value = m.group(1) if rx.groups else m.group(0)
                if rx.groups and PLACEHOLDER.search(value):
                    continue
                hit = True
                yield n, kind, value
        if hit:
            continue
        for tok in TOKEN.findall(line):
            if "/" in tok.strip("/") and tok.count("/") > 1:
                continue
            if not HASHLIKE.fullmatch(tok) and _entropy(tok) > 4.5:
                yield n, "high-entropy string", tok


def scan(root, allow=()):
    """Findings for every publishable file under root, minus allowed fingerprints."""
    allow = set(allow or ())
    out = []
    for f, rel in _files(root):
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        for line, kind, value in scan_text(text):
            fp = fingerprint(value)
            if fp not in allow:
                out.append({"file": rel.as_posix(), "line": line, "kind": kind, "masked": value[:4] + "...", "fingerprint": fp})
    return out


def format_findings(findings):
    return "\n".join(f"  {x['file']}:{x['line']}  {x['kind']}  {x['masked']}  fingerprint {x['fingerprint']}" for x in findings)
