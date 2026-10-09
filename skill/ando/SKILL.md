---
name: ando
description: Keep human-readable architecture docs for many repos in one central docs directory, plus a company map (repo catalog with tracked baselines, bridges between systems, deploy map from infra YAML). Use when the user asks to document a repo or a set of repos, update docs after code changed, answer open documentation questions, map how services talk to each other, or survey what an infra repo deploys. Triggers - "ando", "document this repo", "update the docs", "architecture docs", "system map", "deploy map", "what runs in prod", "open questions in the docs".
---

# ando

ando keeps architecture docs for N projects in one **target directory** (usually a docs
repo). Source repos are never written to. A small runner (`ando`, Python) does every
deterministic step: git, baselines, diffs, the deploy inventory, the joins, checks. You
do the reading, the questions and the writing.

## Find your bearings

1. Locate the target: the nearest `ando.yaml` upwards, `$ANDO_TARGET`, or the path the
   user or runner gave you. Read `ando.yaml`.
2. Run `ando status` to see each project: `never`, `fresh`, `stale`, `failed`,
   `unreachable`. It also rewrites `REPOS.md`.
3. If the runner handed you a bundle (`Bundle: <path>` in the prompt), read it first. It
   names the mode, baseline, head, the snapshot dir with the code at head, the changes,
   facts, open questions and `ports.json`.

## Modes

| mode | when | read |
|---|---|---|
| discover | project has no docs or no baseline | `references/discover.md` |
| interview | open questions exist and a human is present | `references/interview.md` |
| generate | after discover/interview, or baseline unreachable | `references/research.md`, then `references/compose.md` |
| update | baseline reachable, diff not empty | `references/update.md` |
| inventory | an infra project changed | `references/deploy.md` |
| system | ports or the deploy map changed | `references/system.md` |

Flow for a new project: `ando prepare <slug>` (gives mode `discover`), discover, interview
(skip in CI), generate, then `ando stamp <slug> --mode generate`. For a stale project:
`ando prepare <slug>`, follow the mode, then `ando stamp <slug> --mode <mode>`. After any
project changed: `ando map`, then system mode if the maps changed, then `ando check`.

## Hard rules

1. **Never write into a source repo.** Read code in the snapshot dir the bundle names (or
   the repo path read-only). Write only under the target directory.
2. **Facts override code.** `facts/_global.md` and `facts/<slug>.md` are ground truth.
   Code that now contradicts a fact becomes a new question, never a silent doc change and
   never an edit to the fact.
3. **Do not guess what the code cannot tell you.** Liveness, which of two implementations
   is live, deprecation, ownership, misleading names: write a question
   (`references/interview.md` has the format). Non-blocking ones get a default written into
   the doc as `(assumed, see Q-NNN)`.
4. **Evidence.** Every claim about code cites `path:line` relative to the project path.
   Cited files and lines must exist at the commit being documented.
5. **The runner owns** `state.json`, footer stamps (`<!-- ando:stamp -->`), and the blocks
   between `<!-- ando:begin X -->` and `<!-- ando:end X -->`. Never edit those by hand;
   write prose outside them.
6. **Edit, do not rewrite.** In update mode change docs with the Edit tool, smallest edit
   first. An untouched file is a valid outcome.
7. **Style.** Language and tone come from `language` in the manifest. No em dashes. No
   relative dates ("last week"); use absolute dates. Mermaid must parse
   (`references/mermaid.md`).
8. **Secrets.** Never copy secret values, tokens, passwords or connection strings with
   credentials into any doc, question or fact. Names of secrets are fine.
9. **Expensive lookups are opt-in.** External trackers or wikis (any MCP connector) are
   used only as `references/interview.md` describes: on a question marked `lookup:`, or
   when the user asks, and always through a cheap subagent.

## Layout you are writing into

```
<target>/
  ando.yaml  REPOS.md  SYSTEM.md
  map/  bridges.yaml BRIDGES.md deploy.json DEPLOY.md sources.md
  facts/  _global.md <slug>.md
  <slug>/
    1.Overview.md 2.Architecture.md 3.Workflows.md
    4.Deep-Exploration/README.md 4.Deep-Exploration/<module>.md
    5.Boundaries-Interfaces.md 6.Database-Overview.md     (service; lib: 1 + 4)
    DEPLOY.md                                              (infra)
    .ando/ state.json ports.json inventory.json questions.md scratch/
```

## Finishing a run

1. Self-check against `references/checklist.md`.
2. Run `ando stamp <slug> --mode <mode>`. It runs the checks on the docs you changed and
   moves the baseline only if they pass. Fix what it reports and stamp again.
3. Report: docs edited (or "no doc changes needed" and why), questions added, assumptions
   made, ports changed.
