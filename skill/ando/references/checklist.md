<!-- Portions adapted from Terrain (https://github.com/sopaco/terrain), MIT License, Copyright (c) 2026 Sopaco. See THIRD_PARTY_NOTICES.md. -->
# Quality checklist

Self-check every file you wrote or edited before reporting. Fix failures; do not report
them as done. Items tagged **[check]** are also enforced by `ando check`, and a failure
there fails the run and blocks the baseline from moving. The rest depend on judgment and
are on you.

## Every doc

- [ ] **[check]** No em dash character anywhere. Use periods, commas, colons or
      parentheses.
- [ ] **[check]** No relative dates ("recently", "last week", "new"). Absolute dates or
      none.
- [ ] **[check]** Every cited `path:line` exists at the documented commit, and the line
      is within the file length.
- [ ] **[check]** Links to other projects' docs resolve.
- [ ] **[check]** Every mermaid block parses (rules in `mermaid.md`).
- [ ] **[check]** No claim contradicts a fact (keyword heuristic per fact). Also re-read
      each fact that applies and confirm no sentence says the opposite.
- [ ] Every `(assumed, see Q-NNN)` marker points to an open question that exists, and the
      claim matches that question's default.
- [ ] No `TODO(pass N)` placeholders left.
- [ ] No secret values (tokens, passwords, connection strings with credentials).
- [ ] Body language matches the manifest `language`; identifiers stay as in code.
- [ ] Footer stamp untouched (the runner writes it).

## Narrative style

- [ ] Each `##` section opens with 2-4 sentences of prose, not a table or list.
- [ ] Each table has a sentence before it and a takeaway after it.
- [ ] Decisions say what was chosen, what was given up, and why.
- [ ] Module docs open with what the module does and why it exists.
- [ ] Workflow docs give the whole picture before the steps.
- [ ] Parameter tables explain the effect of each setting.
- [ ] It reads like an article, not slide notes.

## Doc set (generate mode)

- [ ] **[check]** Required files exist for the project kind: service gets all six plus
      `4.Deep-Exploration/README.md`; lib gets `1.Overview.md`, `4.Deep-Exploration/`,
      `5.Boundaries-Interfaces.md`.
- [ ] **[check]** The number of `4.Deep-Exploration/<module>.md` files matches the
      `modules` list in `state.json`.
- [ ] Every candidate module from `domains.md` is either documented or excluded by a
      fact or a `scope` answer. None dropped silently.

## 1.Overview.md

- [ ] Opening summary is specific to this project, not generic.
- [ ] At least one user or caller role is named.
- [ ] Has a C4Context diagram.
- [ ] States scope: what it does and does not do.
- [ ] Stack entries come from manifests and code, not guesses.

## 2.Architecture.md

- [ ] Principles are concrete and tied to modules or files.
- [ ] Has a C4Container (or equivalent) diagram.
- [ ] Has the module table with a path on every row.
- [ ] Has at least one sequence diagram or flowchart.
- [ ] Decisions rest on observed code, not speculation.

## 3.Workflows.md

- [ ] Has an end-to-end flowchart.
- [ ] Has at least one sequence diagram.
- [ ] Each step names a real function or module with `path:line`.

## 4.Deep-Exploration/

- [ ] **[check]** Each module doc cites at least 3 file paths.
- [ ] Each module doc names at least 2 concrete types or functions.
- [ ] Component table has a path on every row.
- [ ] Modules with importance >= 4 have a data flow diagram; <= 3 have none.
- [ ] `README.md` lists every module file and nothing else.

## 5.Boundaries-Interfaces.md

- [ ] Covers every surface the project has (HTTP, messaging, CLI, config, library API).
- [ ] Each interface has its parameters and at least one example where it applies.
- [ ] Every entry matches `ports.json`, and every `ports.json` serves/consumes entry
      appears here.

## 6.Database-Overview.md

- [ ] When triggered: has an erDiagram and column tables (column, type, constraint,
      meaning).
- [ ] When not triggered: says so and explains how state is persisted.

## Update mode

- [ ] **[check]** Each changed doc is not empty, has no fewer `##` headings than before,
      and kept at least 60% of its previous length, unless a section removal was declared.
- [ ] Every edit traces to a path in the change list. Nothing else was rephrased.
- [ ] Untouched sections are byte-for-byte the same.
- [ ] Deleted paths are gone from tables, indexes and diagrams; renamed paths are
      rewritten.
- [ ] At most 3 docs edited, or the report says why more were needed.
- [ ] `ports.json` reflects the diff, with `path:line` evidence on every new entry.
- [ ] If nothing changed, the report says so explicitly.

## Ports and state

- [ ] **[check]** Every `ports.json` and `bridges.yaml` entry cites evidence that exists
      at the project's baseline.
- [ ] **[check]** The `state.json` baseline sha exists in the repo and matches the doc
      footer stamps.
- [ ] No port added from a name alone; the code shows the route, call or binding.
