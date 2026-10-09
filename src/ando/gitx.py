import hashlib
import os
import re
import subprocess
import tarfile
import io
from pathlib import Path

CACHE = Path(os.environ.get("ANDO_CACHE", Path.home() / ".cache" / "ando"))


class GitError(RuntimeError):
    pass


def git(gitdir, *args, check=True, binary=False):
    p = subprocess.run(["git", "-C", str(gitdir), *args], capture_output=True)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout if binary else p.stdout.decode(errors="replace")


def is_url(repo):
    return bool(re.match(r"^(\w+://|[\w.-]+@[\w.-]+:)", repo))


class Repo:
    """A project's source repo, read only through git objects."""

    def __init__(self, spec, base_dir):
        self.spec = spec
        repo = spec["repo"]
        if is_url(repo):
            name = re.sub(r"[^\w.-]+", "_", repo)
            self.gitdir = CACHE / "repos" / f"{name}.git"
            self.remote = True
        else:
            p = Path(os.path.expanduser(repo))
            self.gitdir = p if p.is_absolute() else (base_dir / p).resolve()
            self.remote = False
        self.branch = spec.get("branch")

    def ensure(self, fetch=False):
        if self.remote:
            if not self.gitdir.exists():
                self.gitdir.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "clone", "--mirror", "--quiet", self.spec["repo"], str(self.gitdir)], check=True)
            elif fetch:
                git(self.gitdir, "fetch", "--prune", "--quiet")
        else:
            if not (self.gitdir / ".git").exists() and not (self.gitdir / "HEAD").exists():
                raise GitError(f"not a git repo: {self.gitdir}")
            if fetch and self.branch:
                git(self.gitdir, "fetch", "--quiet", "origin", self.branch, check=False)

    def ref(self):
        if not self.branch:
            return "HEAD"
        if not self.remote and self.has(f"refs/remotes/origin/{self.branch}"):
            return f"origin/{self.branch}"
        return self.branch

    def has(self, rev):
        return git(self.gitdir, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False).strip() != ""

    def head(self):
        return self.resolve(self.ref())

    def resolve(self, rev):
        return git(self.gitdir, "rev-parse", f"{rev}^{{commit}}").strip()

    def commit_info(self, sha):
        out = git(self.gitdir, "show", "-s", "--format=%H%x00%cI%x00%s", sha)
        h, date, subject = out.strip().split("\x00", 2)
        return {"sha": h, "date": date, "subject": subject}

    def pathspec(self):
        path = self.spec.get("path", ".") or "."
        spec = [path]
        for ex in self.spec.get("exclude", []) or []:
            spec.append(f":(exclude,glob){_join(path, ex)}")
        return spec

    def behind(self, base, head):
        out = git(self.gitdir, "rev-list", "--count", f"{base}..{head}", "--", *self.pathspec())
        return int(out.strip() or 0)

    def log(self, base, head):
        out = git(self.gitdir, "log", "--no-merges", "--format=%h %cs %s", f"{base}..{head}", "--", *self.pathspec())
        return out.splitlines()

    def name_status(self, base, head):
        out = git(self.gitdir, "diff", "--name-status", "-M", *_relflag(self.spec), base, head, "--", *self.pathspec())
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            rows.append({"status": parts[0], "paths": parts[1:]})
        return rows

    def patch(self, base, head, path):
        return git(self.gitdir, "diff", "-U3", "-M", *_relflag(self.spec), base, head, "--", _join(self.spec.get("path", "."), path))

    def numstat(self, base, head):
        out = git(self.gitdir, "diff", "--numstat", "-M", *_relflag(self.spec), base, head, "--", *self.pathspec())
        stats = {}
        for line in out.splitlines():
            a, d, p = line.split("\t", 2)
            stats[p] = (0 if a == "-" else int(a)) + (0 if d == "-" else int(d))
        return stats

    def ls_files(self, sha, under=None):
        root = _join(self.spec.get("path", "."), under or ".")
        out = git(self.gitdir, "ls-tree", "-r", "--name-only", sha, "--", root)
        return out.splitlines()

    def show(self, sha, path):
        return git(self.gitdir, "show", f"{sha}:{path}", binary=True)

    def line_count(self, sha, path):
        try:
            return self.show(sha, path).count(b"\n") + 1
        except GitError:
            return None

    def snapshot(self, slug, sha):
        """Extract the project path at sha into the cache; returns the dir holding the project root."""
        dest = CACHE / "snap" / slug / sha[:12]
        root = dest / _rel(self.spec) if _rel(self.spec) else dest
        if (dest / ".complete").exists():
            return root
        dest.mkdir(parents=True, exist_ok=True)
        data = git(self.gitdir, "archive", "--format=tar", sha, "--", self.spec.get("path", ".") or ".", binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            tf.extractall(dest, filter=_safe_member)
        (dest / ".complete").write_text(sha)
        return root


def _rel(spec):
    p = (spec.get("path", ".") or ".").strip("/")
    return "" if p in ("", ".") else p + "/"


def _safe_member(member, path):
    """Drop members the data filter rejects (e.g. symlinks escaping the repo) instead of aborting."""
    try:
        return tarfile.data_filter(member, path)
    except tarfile.FilterError:
        return None


def _relflag(spec):
    r = _rel(spec)
    return [f"--relative={r}"] if r else []


def _join(base, sub):
    base = (base or ".").strip("/")
    sub = (sub or ".").lstrip("/")
    if base in ("", "."):
        return sub
    if sub in ("", "."):
        return base
    return f"{base}/{sub}"


def sha256_file(p):
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()
