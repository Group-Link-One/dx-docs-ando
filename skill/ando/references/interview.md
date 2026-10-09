# Interview mode: questions, rounds, facts

## Question format (`<target>/<slug>/.ando/questions.md`)

```markdown
## Q-007 [choice] Which analytics engine runs in production?
key: choice:analytics-engine
evidence: src/olap/** (no deploy manifest), src/warehouse/** (deployed, see map/deploy.json)
default if unanswered: the warehouse engine is live, the olap code is unused
affects: 2.Architecture, 6.Database-Overview, 4.Deep-Exploration/analytics
blocking: yes
lookup: tracker "olap warehouse decision"
```

- Kinds: `liveness`, `choice`, `status`, `ownership`, `naming`, `scope`.
- `key` is stable across runs (kind + subject). The runner and you dedupe on it.
- `lookup` is optional. Add it only when a human decision is likely recorded in an
  external tracker or wiki and the evidence in code is thin.
- Questions raised by `ando map` already follow this format (`raised: ... by ando map`).

## Rounds (human present)

1. Order: blocking first, then the ones whose default you trust least.
2. Ask with `AskUserQuestion`, at most 4 per round. Each question: the default as the
   first option marked "(Recommended)", one or two real alternatives, free text is
   implicit. Put the evidence in the option descriptions, short.
3. After each round, re-read the evidence the answers point at. Answers open new
   questions ("X is dead" leads to "then is the endpoint that only serves X dead too?").
   Add those to the next round.
4. Stop when no blocking questions remain, or the user says stop. Unasked non-blocking
   questions keep their default.

## Facts (`<target>/facts/<slug>.md`, or `_global.md` when it spans projects)

Write each answer as a short, dated, sourced statement, then remove the question from
`questions.md`:

```markdown
- F-003 (2026-10-01, <who answered>, Q-007): The olap code is a discarded experiment,
  never deployed. The warehouse engine is the only analytics store.
  key: choice:analytics-engine
  scope: analytics-service, ingest-service
  deny: /olap (engine|cluster) (is|runs) (live|in production)/i
```

- Number facts per file, never reuse a number.
- `key` copies the question's key so the question is never raised again.
- `scope` lists the projects it applies to (or `all`).
- `deny` (optional, repeatable) is a regex that must not match any doc in scope.
  `ando check` enforces it. Write it narrowly; a broad regex blocks legitimate text.
- After writing facts, apply them: fix the affected sections named in `affects`.

## No human (CI)

Ask nothing. New questions go to `questions.md` and into the run report as a checklist.
Use the defaults and mark them in the docs: `(assumed, see Q-007)`. A human answers later
by editing the facts file or by a PR comment `/ando answer Q-007 <answer>`; the next run
turns it into a fact and applies it.

## External lookups (trackers, wikis, chat)

Connectors to external systems are slow and burn context. Rules:

- Only for a question with `lookup:`, or when the user asks for one. Never as part of
  discover or update by default. In CI only when the prompt says lookups are
  allowed (`ando run --allow-lookups`).
- Run it in a subagent with the cheapest model that can do it (`haiku` for search and
  listing, `sonnet` to read and summarize long threads). Give it the query, the question,
  and a hard output limit: at most 10 lines plus links to the items it used.
- The result is a **candidate** fact with `source: <link>`. Confirm it with the human in
  the next round before writing it. In CI, attach it to the question as
  `lookup result:` and leave the question open.
- List every lookup that ran in the run report.
