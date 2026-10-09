<!-- Portions adapted from Terrain (https://github.com/sopaco/terrain), MIT License, Copyright (c) 2026 Sopaco. See THIRD_PARTY_NOTICES.md. -->
# Phase 4: compose

Goal: turn the scratch notes into the human-facing doc set under `<target>/<slug>/`.
Read notes from `<target>/<slug>/.ando/scratch/` as needed; do not redo research. If a
note is missing a fact you need, read the code for that one point and add it to the note.

## Doc set

| File | Required | Built from |
|---|---|---|
| `1.Overview.md` | always | `preprocessing.md`, `context.md` |
| `2.Architecture.md` | service | `architecture.md`, `domains.md` |
| `3.Workflows.md` | service | `workflows.md` |
| `4.Deep-Exploration/README.md` | always | `domains.md` |
| `4.Deep-Exploration/<module>.md` | one per module | `modules/<module>.md` |
| `5.Boundaries-Interfaces.md` | service, lib | `boundaries.md` |
| `6.Database-Overview.md` | service | `database.md` |

File names are fixed and stay in English whatever the output language. Body text follows
the manifest `language`; identifiers, paths and framework names stay as in the code.

`6.Database-Overview.md` is always written for a service. When the database step was not
triggered, it is a short file that says so and explains how the project persists state.

## Write order

Fewest dependencies first:

1. `5.Boundaries-Interfaces.md`
2. `1.Overview.md`
3. `4.Deep-Exploration/<module>.md`, one at a time, then `4.Deep-Exploration/README.md`
4. `2.Architecture.md`
5. `3.Workflows.md`
6. `6.Database-Overview.md`

## Passes

Large docs are written in 2-3 passes, not one call:

| Doc | Pass 1 | Pass 2 | Pass 3 |
|---|---|---|---|
| `2.Architecture.md` | skeleton with every heading, principles, pattern table, stack | context and container diagrams, module table | sequence diagrams, implementation notes, decisions |
| `3.Workflows.md` | skeleton, end-to-end path diagram | per-workflow flowcharts and sequence diagrams | concurrency, error handling |
| `4.Deep-Exploration/*` | one Write per module | | |
| others | single Write | | |

Pass 1 writes the full heading skeleton with a `TODO(pass N)` line under each heading
still to fill. Later passes replace those lines with the Edit tool. No `TODO` survives the
last pass.

## Evidence

- Every non-trivial claim cites `path:line` (or `path:start-end`) relative to the project
  path, in backticks: `` `src/orders/handler.ts:42` ``.
- Cited lines must exist at the commit being documented. `ando check` verifies this.
- Component tables have a path column filled on every row.
- Diagram node labels name real things (`"OrderService<br/>create()"`), not "Service
  layer".
- A claim that rests on an unanswered question default ends with `(assumed, see Q-NNN)`.
  Use the question's default; do not invent a different one.
- A claim that a fact settles uses the fact and may cite it as `(F-NNN)`. Never write a
  claim that contradicts a fact, even when the code suggests it.
- Repo docs from `docs_in` are linked under a final "See also" heading, never copied.
- No relative dates ("recently", "last month"). Use absolute dates or none.
- Do not write the footer stamp; the runner adds it.

## Style

The docs are read by people, not parsed. Write like a technical article, not slide notes.

- Open every `##` section with 2-4 sentences: what it covers and why it matters. Never
  put a table or list right under a heading.
- Put a sentence before each table (what to look for) and one after (what follows from
  it).
- Decisions state what was chosen, what was given up, and why.
- One short analogy is welcome for a hard concept (a pipeline as an assembly line). Do
  not stack them.
- Module docs start with what the module does and why it exists, not with paths.
- Workflow docs give the whole picture in a paragraph before the steps.
- Parameter tables explain the effect of each setting, not only its type.
- Plain punctuation: no em dashes.

## Templates

Headings are the contract. Keep their names and order; omit a section only when the
template marks it optional and the project has nothing for it. Diagram rules are in
`mermaid.md`.

### 1.Overview.md

```markdown
# <Project name>
<2-3 paragraphs: what it is, the problem it solves, who relies on it.>

## What it does
<summary, then each capability in bold followed by a sentence or two>

## System context
<sentence> + C4Context diagram + <what the diagram shows about its place>

## Technology choices
<paragraph> + table: area | choice | why

## Scope
<what it does and what it deliberately does not do>

## See also            (optional: repo docs from docs_in)
```

### 2.Architecture.md

```markdown
# Architecture: <Project name>

## Overview
### Design principles      (2-4 principles, each tied to modules or files)
### Architecture patterns  (table: pattern | how it is implemented | why)
### Technology stack

## System context (C4 level 1)      (C4Context, may reuse the Overview one)
## Containers (C4 level 2)          (C4Container) + module table: module | path | role | key abstractions
## Components (C4 level 3)          (one `graph LR` per core module, importance >= 7)
## Key flows                        (sequenceDiagram per main flow)
## Implementation notes
### Patterns in the code
### Concurrency
### Performance
## Decisions                        (each: decision, alternative given up, reason, consequence)
```

### 3.Workflows.md

```markdown
# Workflows

## Overview
<the whole picture in prose> + end-to-end `flowchart LR` with input, processing, output subgraphs

## <Workflow name>            (repeat per main workflow)
<what problem it solves, trigger, entry `path:line`>
flowchart TD + sequenceDiagram
table: stage | performed by | input | output | notes

## Concurrency and async model
## Error handling
```

### 4.Deep-Exploration/<module>.md

```markdown
# <Module name>
Path: `src/<module>/`

## What this module does        (2-3 paragraphs)
## Key features                 (each names a real function or type)
## Components                   (table: component | path | responsibility)
## Data flow                    (flowchart for importance >= 4, then steps with `path:line`)
## Interfaces and extension points
## Interactions                 (table: module | direction | interface | notes)
## Role in business flows       (per flow from domains.md)
## Performance                  (optional)
## Notable implementation       (optional)
```

Depth follows the importance score from research: modules scored <= 3 get only "What
this module does", "Key features" and "Components", with no diagram.

### 4.Deep-Exploration/README.md

Index of all modules: a short paragraph on how the project is split, the module
dependency `graph TD`, then a table grouped by domain (core, supporting, generic): module
(linked to its file) | role | importance. Every module file is listed; nothing else is.

### 5.Boundaries-Interfaces.md

```markdown
# Boundaries and interfaces
<one paragraph on what surfaces exist>

## HTTP API            (table: method | path | handler | purpose)
## Messaging           (table: topic or queue | direction | payload | handler)
## CLI                 (per command: description, parameter table with effect, example)
## Configuration       (table: key or env var | default | effect) + example config
## Library API         (lib only)
## Integration notes
```

Omit a surface section the project does not have. Every entry here must match a
`ports.json` entry and the reverse.

### 6.Database-Overview.md

```markdown
# Database overview
<engine(s), ownership, how the schema evolves>

## Summary             (table: tables | views | procedures | indexes)
## Entity relationships  (erDiagram)
## Core tables         (per table: column | type | constraint | meaning)
## Views, procedures, functions   (optional)
```

## After writing

Run the self-check in `checklist.md` on every file written, then report: files written,
module count, open questions referenced by `(assumed, see Q-NNN)` markers, and anything a
human should review.
