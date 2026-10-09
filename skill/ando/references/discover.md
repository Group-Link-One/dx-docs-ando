# Discover mode: inventory, module map, ports, questions

Discover writes no docs. It produces the inputs every later mode relies on:
`.ando/scratch/discover.md`, `.ando/ports.json`, `.ando/questions.md`, and rows in
`map/sources.md`.

## Inputs

- The bundle: snapshot dir (code at head), facts, open questions.
- `map/deploy.json` and `map/bridges.yaml` if `ando map` has run: they tell you which of
  this project's images actually run, and where.
- Existing docs listed by `docs_in` in the manifest (default `README.md`, `docs/**`).

## Steps

1. **Tree and stack.** List top-level dirs, package manifests, lockfiles, languages,
   entrypoints (`main`, `cmd/`, `bin/`, server bootstraps), build files, Dockerfiles, CI
   workflows, compose files, deploy manifests. Note the size (file count) to pick a scan
   strategy in `research.md`.
2. **Existing docs as evidence.** Read the `docs_in` files. Add one row per file to
   `map/sources.md` (`| <slug> | path@<sha7> | one-line summary |`). Treat them as lower
   trust than code and facts. When a doc contradicts the code, write a `status` question.
3. **Module map.** Candidate modules from the directory layout and the entrypoints. Group
   them into domains (core, supporting, generic), score importance 1 to 10. Write the map
   to `scratch/discover.md`. Names are kebab-case; they become
   `4.Deep-Exploration/<module>.md`.
4. **Ports.** Fill `.ando/ports.json` following `ports.md`. Every entry carries evidence.
5. **Questions.** Write them (format in `interview.md`) when the answer would change the
   docs and the code cannot settle it. Look for:
   - **liveness**: code with no entrypoint, no import, no deploy manifest, no CI job; or
     an image that `deploy.json` lists under "built but not deployed".
   - **choice**: two implementations of the same role (two databases, two queues, two
     runtimes) with no clear winner in config.
   - **status**: names or comments saying legacy, deprecated, old, v1, tmp, experiment,
     poc; repo docs that disagree with the code.
   - **ownership**: a table, topic or endpoint used by several projects; an unmatched port
     in `bridges.yaml`.
   - **naming**: env vars or modules whose name says one thing and whose use says another.
   - **scope**: folders that may not deserve docs (tools, scripts, fixtures, vendored code).
6. **Do not duplicate.** Skip a question whose `key:` already exists in `questions.md`
   or in a fact. Prefer one question with a good default over three narrow ones.

## Output check

- `scratch/discover.md` has: stack, entrypoints, module map with scores, deploy status per
  image (from `deploy.json`), list of evidence for each blocking question.
- `ports.json` validates against `ports.md`.
- Every question has evidence, a default, `affects`, `blocking`.

Next: interview if a human is present and blocking questions exist; otherwise generate,
using defaults and marking them `(assumed, see Q-NNN)`.
