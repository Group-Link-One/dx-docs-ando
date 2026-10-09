<!-- Portions adapted from Terrain (https://github.com/sopaco/terrain), MIT License, Copyright (c) 2026 Sopaco. See THIRD_PARTY_NOTICES.md. -->
# Update mode: incremental edits from a diff

You are updating existing documentation, not writing it again. The existing docs are the
research output; no preprocessing or research phase runs in this mode.

## Inputs

The runner hands you a context bundle:

- Baseline sha and current HEAD for the project path.
- Commit log since the baseline, newest first.
- `git diff --name-status -M` with status letters (`A`, `M`, `D`, `R<score>`), already
  filtered by the manifest `exclude` globs. Pure renames (`R100`) were already applied to
  the docs by the runner.
- The patch, `git diff -U3` per file, capped. The biggest files may appear as stat only.
- Facts (`facts/_global.md`, `facts/<slug>.md`), open questions, `ports.json`.
- The list of existing docs under `<target>/<slug>/`.

The change list is authoritative. Investigate only the changed paths; do not re-explore
the repository.

## Ground rules

1. The existing docs are presumed correct for everything the change list does not touch.
2. Facts override code. If the diff suggests something a fact denies, the fact wins in the
   docs. If the code now clearly contradicts a fact (a component marked dead gets a new
   deployment manifest), write a new question in `questions.md` and leave the docs as the
   fact states. Do not edit the fact.
3. The smallest edit that makes the docs accurate is the right edit.
4. An untouched file is the correct outcome, not a missed step.

## How to work

1. Build a docs-impact plan from the change list: for each changed path, name the doc
   (and section) that makes a claim the change now makes wrong, or "none".
2. Read only those docs, and only the changed source paths (and their patches) needed to
   correct them.
3. Edit those docs in place with the Edit tool. Keep structure, heading levels, tone and
   citation style.
4. Update `.ando/ports.json` from the diff (see below).
5. Report (see below).

## Preservation rules (mandatory)

- Reproduce untouched sections verbatim: same wording, order, tables and diagrams. Do not
  rephrase, re-summarize, reformat or "improve" them.
- Revise only what the changed files actually invalidate: new or removed modules, moved
  paths, changed flows, changed dependencies or boundaries.
- `D` (deleted): remove the path from module maps, component tables, path indexes and
  diagrams. Remove claims that only that path supported.
- `R` (renamed, partial): rewrite every citation of the old path to the new one, and fix
  line numbers when the patch shows they moved.
- `M` (modified): fix only claims the patch contradicts. A cited `path:line` whose line
  moved gets its number corrected.
- `A` (added): document it only if it changes an architectural claim (a new endpoint, a
  new consumer, a new module, a new dependency).
- Cosmetic changes (formatting, comments, tests, lockfiles, docs, dependency bumps with
  no behavior change) get no edit.

## Edit mechanics

- Edits go through the Edit tool on files in the target dir. Never rewrite a document end
  to end with Write, and never return a document as reply text.
- Do not delete or truncate existing files.
- Edit at most 3 doc files unless the change list clearly justifies more (a renamed
  module touched in many places, a new service boundary). State the justification in the
  report.
- Add `4.Deep-Exploration/<module>.md` only when the change introduces a genuinely new
  module; delete one only when its module was removed from the repository. In both cases
  update `4.Deep-Exploration/README.md`, the module table in `2.Architecture.md`, and
  report the module list change so the runner updates `state.json`.
- A new module doc follows the template in `compose.md` and the depth for its importance
  in `research.md`.
- New claims follow the evidence rules in `compose.md`: `path:line`, `(assumed, see
  Q-NNN)` for defaults, no claim against a fact.
- Do not touch the footer stamp.

The runner guards every changed doc after the run: it must not be empty, must keep at
least as many `##` headings as before, and must keep at least 60% of its previous length.
A legitimate section removal (a module deleted) must be declared in the report, or the
guard fails the run.

## ports.json

Keep `<target>/<slug>/.ando/ports.json` current from the same diff (rules in `ports.md`):

- A new route, consumer, producer, client call, table access or Dockerfile in the patch
  adds an entry with `via`, `name` and `evidence` (`path:line`).
- A deleted or renamed source updates or removes the entries whose evidence points at it.
- An entry whose evidence line moved gets its line corrected.
- Do not add an entry from naming alone; the patch must show the call, route or binding.

Port changes trigger `ando map` after the run, so be precise: a wrong port becomes a
wrong bridge.

## When nothing changed

If nothing in the change list invalidates any doc or port, change no file and say so
explicitly: "No doc changes: <one line on why, e.g. only tests and lockfiles changed>."
That is a valid, complete run.

## Report

End with a short report for the PR body:

```
Docs edited: 2.Architecture.md (module table), 4.Deep-Exploration/billing.md (data flow)
Sections removed: none
Ports: +1 consumes kafka `orders.created` (src/billing/consumer.ts:18)
Modules: unchanged
Assumptions: (assumed, see Q-014) in 4.Deep-Exploration/billing.md
New questions: Q-015 [liveness] is `src/legacy-export/` still deployed?
Over 3 files: no
```

Before reporting, run the update items of `checklist.md`.

## Example

Change list:

```
M src/billing/invoice.ts
D src/billing/pdf-legacy.ts
M package-lock.json
M src/billing/invoice.test.ts
```

Plan: `invoice.ts` patch changes the tax step (fix the step in
`4.Deep-Exploration/billing.md`, data flow section). `pdf-legacy.ts` deleted (remove its
row from the billing components table and the node from its flowchart). Lockfile and test:
no edit. Result: one file edited, two sections touched, everything else verbatim.

## Edge cases

- **Checking mid-run.** Before stamping, run `ando check <slug> --head` so citations
  resolve at the new head. Plain `ando check` resolves at the old baseline and flags every
  citation of a new file.
- **Pre-existing citation drift.** Imported or older docs may cite wrong lines. Fix
  citations only inside sections you edit. Do not renumber the rest of a file
  mechanically; `ando check` reports that drift as debt.
- **Citation style.** New citations are always relative to the project path, even when
  the surrounding text uses another style.
- **Aggregate counts** (number of models, routes, files). Update an exact count only when
  the diff changes it and it is cheap to verify. When a count is repeated across docs,
  updating all occurrences counts as one change against the 3-file limit. In new text,
  prefer counts that age well ("about 200 models").
- **ports.json missing or partial.** Add only what the diff shows. A full backfill of
  ports belongs to discover (`ando prepare <slug> --mode discover`), not to update.
- **Language.** Prose in the manifest `language`; identifiers, routes, table names and
  error strings stay verbatim as in code.
- **Large bundles.** The bundle can exceed one read; page through it. Patches over the
  budget appear as stat only: read those files in the snapshot.

