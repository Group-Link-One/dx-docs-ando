# Ports: how a project touches the outside

`<target>/<slug>/.ando/ports.json` lists every way the project talks to something outside
its own process. `ando map` joins ports across projects into `map/bridges.yaml`, so a
wrong or vague port becomes a wrong edge in the company map. Precision beats coverage.

## Shape

```json
{
  "serves":   [{"component": "orders-api", "via": "http", "name": "POST /v1/orders", "evidence": "src/api/orders.ts:42"}],
  "calls":    [{"component": "orders-api", "via": "http", "name": "billing-api POST /v1/invoices", "evidence": "src/clients/billing.ts:18"}],
  "produces": [{"via": "kafka", "name": "orders.created", "evidence": "src/events/publish.ts:30"}],
  "consumes": [{"via": "rabbitmq", "name": "payments.settled", "evidence": "src/workers/settle.ts:12"}],
  "reads":    [{"via": "postgres", "name": "billing.invoices", "evidence": "src/repo/invoices.ts:8"}],
  "writes":   [{"via": "s3", "name": "bucket:order-exports", "evidence": "src/export/s3.ts:51"}],
  "binds":    [{"via": "rabbitmq", "exchange": "payments", "queue": "payments.settled", "key": "settled.*", "evidence": "src/workers/settle.ts:9"}],
  "builds":   [{"image": "registry.example.com/orders-api", "from": "services/api/Dockerfile"}]
}
```

`component` is the deployable unit the port belongs to: in a monorepo, the service whose
image runs it (usually its directory and image name, the same name the deploy inventory
uses for the workload); in a single-service repo, its image name or the project slug.
The company map draws one node per component, so code edges and deploy-config edges meet
on the same node. Shared libraries are not components: attribute their ports to each
service that uses them.

`via`: `http`, `grpc`, `kafka`, `rabbitmq`, `mqtt`, `nats`, `redis`, `postgres`, `mysql`,
`mongodb`, `clickhouse`, `druid`, `s3`, `webhook`, `other`.

## Naming, so the join matches

The join is exact on `(via, name)`. Two projects must write the same name for the same
thing:

- **Topics, queues, streams, subjects:** the literal name as configured. If it comes from
  an env var, resolve it from the deploy inventory (`inventory.json` `links`) or the
  default in code; if unresolvable, write `env:VAR_NAME` and raise a `naming` question.
- **HTTP served:** `METHOD /path` with path params as `:id`. One entry per route group is
  fine (`* /v1/orders/*`) when there are many.
- **HTTP called:** `<callee component> METHOD /path`, where the callee is the component
  name of the server (a workload name from the inventory) or, for third parties, the
  external host. The join pairs a call with a serve of that component and route; a call
  to a known component without a matching serve still becomes an edge (`code-caller`).
- **Brokers with routing (RabbitMQ):** producers write `exchange:<name>`, consumers
  `queue:<name>`, and every `bindQueue` (or declared binding) goes in `binds`. The join
  follows exchange to queue through `binds`, so a missing binding is a missing edge.
- **Tables:** `schema.table` (or `database.table`); collections the same way.
- **Buckets:** `bucket:<name>`. **Keys or prefixes in a shared cache:** `prefix:<name>`.
- **Webhooks to third parties:** `calls` with the external host as the name.

## Rules

- Every entry has `evidence` as `path:line` relative to the project path.
- Only what runs in the documented scope. Tests, fixtures and excluded paths do not
  count.
- `builds` lists images this project builds when the manifest `builds` patterns do not
  cover them (the runner already scans Dockerfiles). The image name must match what the
  deploy manifests use, without the tag.
- Keep it current: in update mode, an added producer, a renamed topic or a removed route
  changes `ports.json` in the same run.
- Facts win: a port that only serves a component a fact marks dead is still listed, with
  `"status": "dead (F-003)"`.
