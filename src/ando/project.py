import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .gitx import Repo

MANIFEST = "ando.yaml"
LOCAL = "ando.local.yaml"
VERSION = "0.1.0"
SERVICE_DOCS = ["1.Overview.md", "2.Architecture.md", "3.Workflows.md",
                "5.Boundaries-Interfaces.md", "6.Database-Overview.md"]
MODULES_DIR = "4.Deep-Exploration"
KINDS = ("service", "infra", "lib", "external")


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_target(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    if os.environ.get("ANDO_TARGET"):
        return Path(os.environ["ANDO_TARGET"]).resolve()
    p = Path.cwd().resolve()
    for d in [p, *p.parents]:
        if (d / MANIFEST).exists():
            return d
    raise SystemExit(f"no {MANIFEST} found from {p} upwards; pass --target or run `ando init`")


class Target:
    def __init__(self, root):
        self.root = Path(root)
        self.manifest_path = self.root / MANIFEST
        self.manifest = yaml.safe_load(self.manifest_path.read_text()) or {}
        self.defaults = self.manifest.get("defaults") or {}
        local = self.root / LOCAL
        self.local = (yaml.safe_load(local.read_text()) or {}) if local.exists() else {}
        self.projects = [Project(self, p) for p in self.manifest.get("projects") or []]

    def project(self, slug):
        for p in self.projects:
            if p.slug == slug:
                return p
        raise SystemExit(f"unknown project: {slug}")

    def select(self, slugs):
        return [self.project(s) for s in slugs] if slugs else self.projects

    @property
    def facts_dir(self):
        return self.root / "facts"

    @property
    def map_dir(self):
        return self.root / "map"

    def facts_text(self, slug=None):
        parts = []
        for name in ["_global.md", f"{slug}.md" if slug else None]:
            if name and (self.facts_dir / name).exists():
                parts.append((self.facts_dir / name).read_text())
        return "\n".join(parts)

    def all_facts_text(self):
        if not self.facts_dir.exists():
            return ""
        return "\n".join(f.read_text() for f in sorted(self.facts_dir.glob("*.md")))


class Project:
    def __init__(self, target, spec):
        self.target = target
        self.spec = {**{k: v for k, v in target.defaults.items() if k in ("docs_in", "max_changed_files", "builds", "language")}, **spec}
        self.slug = spec["slug"]
        self.kind = spec.get("kind", "service")
        if self.kind not in KINDS:
            raise SystemExit(f"{self.slug}: unknown kind {self.kind}")
        self.repo = None if self.kind == "external" else Repo(self._repo_spec(), target.root)

    def _repo_spec(self):
        """ando.local.yaml `repos:` maps a repo URL (or a slug) to a local checkout, so the manifest stays portable."""
        repos = self.target.local.get("repos") or {}
        local = repos.get(self.spec["repo"]) or repos.get(self.slug)
        return {**self.spec, "repo": local} if local else self.spec

    @property
    def dir(self):
        return self.target.root / self.slug

    @property
    def meta(self):
        return self.dir / ".ando"

    @property
    def state_path(self):
        return self.meta / "state.json"

    def load_state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return None

    def save_state(self, state):
        self.meta.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    def new_state(self):
        return {"repo": self.spec["repo"], "branch": self.spec.get("branch"), "path": self.spec.get("path", "."),
                "kind": self.kind, "baseline": None, "last_run": None, "modules": [], "docs": {}}

    def load_json(self, name, default=None):
        p = self.meta / name
        return json.loads(p.read_text()) if p.exists() else default

    def save_json(self, name, data):
        self.meta.mkdir(parents=True, exist_ok=True)
        (self.meta / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def doc_files(self):
        if not self.dir.exists():
            return []
        return sorted(p for p in self.dir.rglob("*.md") if ".ando" not in p.parts)

    def modules_on_disk(self):
        d = self.dir / MODULES_DIR
        return sorted(p.stem for p in d.glob("*.md") if p.name != "README.md") if d.exists() else []

    def required_docs(self):
        if self.spec.get("docs") is False or self.kind == "external":
            return []
        if self.kind == "infra":
            return ["DEPLOY.md"]
        if self.kind == "lib":
            return ["1.Overview.md"]
        return SERVICE_DOCS

    def language(self):
        return self.spec.get("language") or self.target.manifest.get("language") or "en"
