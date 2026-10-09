<!-- Portions adapted from Terrain (https://github.com/sopaco/terrain), MIT License, Copyright (c) 2026 Sopaco. See THIRD_PARTY_NOTICES.md. -->
# Phase 3: research

Goal: understand every module of the project well enough to write the doc set, and
persist what you learn to scratch so composition never depends on what is still in
context. No final docs are written in this phase.

Inputs, read first:

- `<target>/facts/_global.md` and `<target>/facts/<slug>.md`: ground truth. A fact beats
  anything the code suggests.
- `<target>/<slug>/.ando/questions.md`: open questions and their defaults.
- `<target>/<slug>/.ando/ports.json` and the module list in `.ando/state.json` (from
  discover), when present.
- Repo docs listed in the manifest `docs_in`: evidence, ranked below code.

Output: markdown notes under `<target>/<slug>/.ando/scratch/`. Nothing is written into the
source repo.

## Scratch layout

```
<target>/<slug>/.ando/scratch/
  preprocessing.md      # step 1: project facts, stack, layout, entrypoints
  context.md            # step 2: users, external systems, scope
  domains.md            # step 3: full module list, DDD grouping, scores, flows
  architecture.md       # step 4
  workflows.md          # step 5
  boundaries.md         # step 6
  database.md           # step 7 (only when triggered)
  modules/<module>.md   # step 8: one note per module
```

Rules for scratch:

- Write each note as soon as its step is done, with absolute paths. Do not hold a step's
  findings only in context.
- Under context pressure, drop earlier findings from working memory and re-read the note
  when needed.
- Every claim in a note carries evidence as `path:line` (or `path` for whole-file claims).
  A note without evidence is a guess and must not reach the docs.
- Mark anything that rests on an open question default with `(assumed, see Q-NNN)`.
- Scratch is gitignored and kept between runs. Overwrite stale notes; do not append.

## Step order

```
1 preprocessing -> 2 context -> 3 domains -> [4 architecture, 5 workflows, 6 boundaries, 7 database] -> 8 modules
```

Searches for steps 4, 5 and 6 are independent: run them in parallel. Step 8 needs the
module list from step 3.

## Step 1: preprocessing

Pick the scan strategy by size (count source files, excluding tests and vendored code):

| Size | Source files | Strategy |
|---|---|---|
| Small | < 100 | List recursively, read every core file |
| Medium | 100-500 | List top-level dirs, read entrypoints, config, README, grep for the rest |
| Large | > 500 | README, main config, entrypoints, outlines of core modules, targeted grep |

Skip: `.git/ node_modules/ target/ build/ dist/ out/ bin/ obj/ vendor/ .cache/
__pycache__/`, test dirs and files (`test/ tests/ __tests__/ *.test.* *.spec.*`), and
every manifest `exclude` glob.

Read in priority order:

1. README, the build manifest (`package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`,
   `pom.xml`, ...), the main entrypoints.
2. Module declaration files (`index.ts`, `mod.rs`, `__init__.py`), core types and
   interfaces, config structs.
3. Files named `*service*`, `*handler*`, `*worker*`, `*pipeline*`, `*orchestrator*`.

For files over 500 lines, read the outline and the first 100 lines, then only the ranges
you need.

Useful greps: interfaces (`interface `, `trait `, `abstract class`, `Protocol`), entrypoints
(`func main`, `def main`, `async fn main`, `listen(`), imports between modules, env reads
(`process.env`, `os.Getenv`, `os.environ`, `env::var`).

`preprocessing.md` holds: name, kind (service, CLI, library, worker), languages, runtime
and frameworks, top dependencies, annotated directory tree, entrypoints, candidate modules
with one-line roles, notable oddities.

## Step 2: system context

Answer, with evidence:

- Who uses the system (people, other services, scheduled jobs) and through which
  interface (HTTP, CLI, queue, SDK).
- Which external systems it depends on: databases, brokers, third-party APIs, object
  storage. Check env var names and client constructors.
- What problem it solves, its main inputs and outputs.
- What is in scope and what is explicitly not.

Cross-check against `ports.json`. A port with no matching code, or code with no port, is a
finding: note it for the ports update.

## Step 3: domain modules (full coverage)

Coverage is mandatory. Every module must end up with a doc.

A. Enumerate. Every first-level directory of the main source root (`src/`, `lib/`,
   `app/`, `cmd/`, `internal/`, `packages/*`, `services/*`) is a candidate. Exclude pure
   test and generated directories and anything a fact or a `scope` answer excludes. List
   the full set in `domains.md` before grouping, so nothing is dropped silently.

B. Group (DDD). Several small directories can form one domain (for example `cache/` and
   `metrics/` as "caching"). Classify each domain:

   - Core: delivers the business value (for example `orders`, `billing`, `checkout`).
   - Supporting: technical support for core (integrations, clients, queue adapters).
   - Generic: shared infrastructure (config, utils, types, logging, i18n).

C. Score. For each module: importance 1-10, complexity 1-10, path, one-line role, main
   abstractions, depends on, depended on by.

D. Relate. Draw the module dependency graph (mermaid `graph TD`, see `mermaid.md`) and
   list business flows that cross modules: name, entrypoint, modules involved, importance.

The module slugs chosen here become the `4.Deep-Exploration/<module>.md` file names and
the `modules` list in `state.json`. Use lowercase kebab-case (`order-intake`).

A module that exists in code but whose liveness is unknown is still documented; its doc
states the status from facts, or the question default with the `(assumed, see Q-NNN)`
marker.

## Step 4: architecture

Identify the pattern from evidence, not from naming alone:

- Layered: `controller/service/repository/model`, one-way dependencies.
- Event-driven: `event`, `handler`, `subscriber`, `publisher`, broker clients.
- Pipeline: `pipeline`, `stage`, `step`, `processor`, chained calls.
- CQRS: separate command and query paths.
- Several deployables in one repo: multiple `main` entrypoints, separate Dockerfiles.

Record: pattern and the evidence for it, design principles (what problem each solves),
stack table with the reason for each choice, key data types (type, path, purpose), core
interfaces and their implementations, inferred decisions as "chose X over Y because Z".

## Step 5: workflows

- Find entrypoints and trace each main call chain 2-3 levels deep across files.
- For each workflow: trigger (request, message, schedule, CLI), entry function with
  `path:line`, ordered steps with the function each step calls, output, nodes and edges
  for the diagram.
- Note the concurrency model (async, worker pools, locks, consumers) and the error
  strategy (retries, dead letter, partial failure, what aborts the run).
- Note key cross-component interactions for a sequence diagram.

## Step 6: boundaries

Enumerate every external surface:

- HTTP or gRPC endpoints: method, path, handler `path:line`, request and response shape.
- Messages produced and consumed: topic or queue, payload type, handler.
- CLI commands and flags, with defaults.
- Config and env vars: name, type, default, effect.
- Public API if the project is a library: exported functions and types.

Every item found here must also appear in `ports.json` (serves, calls, produces,
consumes, reads, writes). Collect the differences for the ports update.

## Step 7: database (conditional)

Run when any of these hold: `.sql` or `.sqlproj` files; `migrations/`, `sql/`, `db/`,
`database/` directories; an ORM dependency (prisma, typeorm, sequelize, sqlalchemy,
hibernate, gorm, diesel, sqlx, mongoose, ...); a DB config file.

Read migrations in order to follow schema evolution, then ORM entities. Record counts
(tables, views, procedures, indexes), each core table (column, type, constraint, meaning)
and relations (`orders 1:N order_items via order_id`). Note which project owns each table
when a fact or the code says so; shared tables are bridges.

When not triggered, note in `database.md` how the project persists state, if at all.

## Step 8: per-module research

Depth follows importance. Sort modules by importance, highest first, and work in batches
of 3-4: research, write `modules/<module>.md`, release, next.

| Importance | Depth | Files read | Diagram | Minimum note content |
|---|---|---|---|---|
| >= 7 (core) | deep | 5+ | full flowchart plus interaction table | role, features, components, data flow, interfaces, interactions |
| 4-6 (supporting) | standard | 3 | small flowchart | role, features, components, interaction table |
| <= 3 (generic) | brief | 1-2 | none | role, responsibilities, file list |

Read order inside a module: entry file, files named `core`, `main`, `service`, `handler`,
`processor`, then the largest files.

Questions every note answers:

- What role does the module play, and what breaks without it?
- Its public interface (types, functions, endpoints).
- Its internal data flow, as steps with the function and `path:line` of each.
- Notable algorithms or patterns, extension points.
- Performance traits: sync or async, caching, batching.
- Its part in each business flow from step 3.

Each note carries at least 3 file paths and 2 concrete type or function names, so the doc
built from it meets the citation bar in `checklist.md`.

## Before leaving the phase

- `domains.md` lists every candidate module, and each kept module has a
  `modules/<module>.md`.
- Port differences from steps 2 and 6 are collected (apply them to `ports.json` now, with
  evidence).
- Code that contradicts a fact, or a doc in `docs_in` that contradicts the code, is a new
  question in `questions.md`, not a silent choice.
