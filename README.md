# ando

Keeps architecture docs for many repos in one central directory, and keeps them current.

A Python runner does everything deterministic: it reads each repo through git, tracks which commit
the docs describe, joins the deploy manifests and the interfaces each service declares into
one system map, validates the docs and builds a static site. A Claude skill writes the prose. When
it cannot tell something from the code, it raises a question for a person instead of guessing, and
the answer is recorded as a fact that later runs must respect.

ando is a rewrite of [Terrain](https://github.com/sopaco/terrain) (MIT, see
`THIRD_PARTY_NOTICES.md`).

## How it is meant to be run

- **One operator.** ando expects one person (or one CI identity) with read access to every
  tracked repo and, if live snapshots are used, read-only access to the cluster. That person runs
  the updates, answers the open questions, records facts, reviews the diff and publishes.
- **Readers never run ando.** They read the published site or the docs repo.
- **Others can run it.** The manifest names repos by git URL. Each user maps those URLs to local
  checkouts in a gitignored `ando.local.yaml`, so nobody edits the versioned manifest to run it.
- **Nothing is published unreviewed.** A run only writes files into the docs directory. Committing,
  merging and publishing stay manual steps for the operator.

## Install

```sh
git clone https://github.com/Group-Link-One/dx-docs-ando ando
pip install -r ando/requirements.txt   # pyyaml, markdown
ln -s "$PWD/ando/bin/ando" ~/.local/bin/ando
```

Install the skill by linking `skill/ando` into `~/.claude/skills/`. `ando run` needs the `claude`
CLI. Everything else works without it.

## Quick start

```sh
ando init docs && cd docs
ando add billing --repo git@github.com:acme/billing.git --branch main
ando add infra --repo git@github.com:acme/k8s.git --kind infra
ando status            # how far each project's docs are behind its branch
ando run billing       # prepare, write or update docs with the skill, check, move the baseline
ando map               # deploy map, bridges between services, gap questions
ando questions         # what the operator still has to answer
ando check             # citations, links, Mermaid, style, secrets
ando serve             # local preview at http://127.0.0.1:8000
```

`ando.local.yaml`, next to `ando.yaml`, is per user and never committed:

```yaml
repos:
  git@github.com:acme/billing.git: ~/src/billing
```

A repo without a local mapping is mirror-cloned into `~/.cache/ando/repos`.

## Publishing the site

`ando site --out site` writes plain HTML, CSS and JS: rendered docs, search, a bridges explorer,
project status and open questions. It needs no server-side code. To keep viewers off public CDNs,
download Mermaid once and pass the file:

```sh
curl -fsSL -o mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js
ando site --no-status --mermaid-url mermaid.min.js --out site
```

`--no-status` skips the git lookups, so CI does not need the source repos. Any static server
works. An unprivileged nginx image with `site/` copied into `/usr/share/nginx/html` is enough.
Architecture docs describe internal hosts, topics and endpoints, so serve them on an internal
network only.

## Secrets

**What ando reads**

- **Source code** comes from git objects at a fixed commit, never from the working tree. Untracked
  files such as `.env`, local credentials and build output are never read. Anything *committed* to
  a tracked repo is readable by the skill during a run, including a secret someone committed by
  mistake.
- **Deploy manifests** are parsed into an inventory:
  - Env var names are kept. A value is kept only when it looks like a link (a URL, host, topic or
    queue), and never when the name looks secret (`PASS`, `SECRET`, `TOKEN`, `KEY`, `AUTH`,
    `CREDENTIAL`, `PRIVATE`).
  - `user:password@` is stripped from URLs.
  - Secret references (`secretKeyRef`, `envFrom.secretRef`) are recorded by name only.
  - `Secret` objects are not parsed.
- **Live snapshots** (`ando map --live`) are read-only `kubectl get` calls on workloads and Argo CD
  applications. Only names, namespaces, schedules, images, scale and app labels are written. Secrets
  and ConfigMaps are never queried, and env values from pod specs are dropped.

**What stops a leak**

1. **The skill's rules.** The skill must not copy secret values, tokens, passwords or credentialed
   connection strings into docs, questions or facts. Names are fine.
2. **`ando secrets`.** This scans every publishable file in the docs directory: Markdown, JSON,
   YAML and HTML. It looks for:
   - private keys
   - cloud and SaaS token formats (AWS, GitHub, GitLab, Slack, Google, Stripe)
   - JWTs
   - credentials inside URLs
   - quoted password-like assignments
   - high-entropy strings

   Findings show a masked prefix and a fingerprint, never the value.
3. **Hard gates.** On any finding:
   - `ando stamp` refuses to move a baseline
   - `ando site` refuses to build
   - `ando serve` refuses to rebuild

   Unlike other checks, old findings are not tolerated as debt.
4. **Reviewed exceptions.** A false positive is accepted by adding its fingerprint to
   `secret_allow:` in `ando.yaml`. The fingerprint is a hash, so the value never lands in the
   manifest.
5. **A second scanner in CI.** Run an independent tool such as gitleaks over the docs directory
   before building the site, so one scanner's blind spot is covered by the other.

**What it cannot promise**

- **Pattern and entropy scanning has blind spots.** A short, human-chosen password written in
  prose has no shape to match. The operator's review before publishing is the last line.
- **The skill sees committed secrets.** If a tracked repo has a committed secret, the skill can
  read it during a run. Rotating it and removing it from the repo is the fix. ando only keeps it
  out of the docs.
- **The architecture itself is sensitive** even when it contains no secret: hostnames, topics,
  internal endpoints, data flows. Host the site where only staff can reach it.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
