# System mode: the company layer

Runs after `ando map` when ports, inventories or the project list changed. Inputs:
`REPOS.md`, `map/bridges.yaml`, `map/deploy.json`, every project's `1.Overview.md` and
`2.Architecture.md`, all facts.

## `SYSTEM.md` (prose, you own all of it)

1. **What the company runs**: one paragraph, then the projects grouped by domain, one line
   each with a link to `<slug>/1.Overview.md`.
2. **Main flows**: 3 to 6 end-to-end flows (how data or a request crosses systems), each
   as a short numbered list plus one mermaid flowchart. Every arrow must be an edge in
   `bridges.yaml`; cite the edge's `via` and `name`. No edge, no arrow.
3. **Shared infrastructure**: brokers, databases, caches, buckets used by several
   projects, from nodes with several incoming edges.
4. **Boundaries**: external systems (`kind: external` nodes) and who talks to them.
5. **Known gaps**: unmatched ports, untracked sources, open ownership questions. Link the
   questions.

## `map/BRIDGES.md`

The runner writes the per-group diagrams and edge tables. Above the block, write a short
reading guide: what the groups are, which edges are `config` only (seen in deploy env,
not confirmed in code) and which are `code`.

## Rules

- Do not invent edges. If a flow needs an edge that is not there, raise an `ownership`
  question or a missing port in the project's `ports.json` (via that project's update),
  then leave the flow with a visible `(gap, see Q-NNN)`.
- `confidence: config` edges are real deployment wiring, but the direction of data may be
  unknown (a broker URL says "connects", not "produces"). Say "connects to" for those.
- Keep `SYSTEM.md` under roughly 400 lines. Detail belongs in project docs; link there.
- Cross-project links are relative (`../<slug>/2.Architecture.md#...`). `ando check`
  verifies they resolve.
