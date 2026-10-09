# Deploy docs: narrating the inventory

`infra` projects (repos of Kubernetes YAML, Kustomize overlays, Argo CD apps) get no
module docs. The runner extracts the inventory without a model (`ando map`):

- `<target>/<infra-slug>/.ando/inventory.json`: workloads (kind, namespace, images and
  tags, replicas, schedule, env names, in-cluster links, secret ref names), services,
  ingresses, Argo apps, variants (overlays and `-suffix` copies).
- `map/deploy.json`: each image joined to the project and path that build it and the
  workloads that run it.
- Generated tables inside `<!-- ando:begin ... -->` blocks of `<infra-slug>/DEPLOY.md`
  and `map/DEPLOY.md`.

You write the prose around those blocks. Never edit inside them.

## `<infra-slug>/DEPLOY.md`

Above the inventory block, in this order:

1. **Summary**: what this repo deploys, to which cluster(s), how changes reach the cluster
   (Argo auto-sync, manual apply, CI), counts by kind.
2. **Platform components**: third-party systems it runs (brokers, databases, caches,
   ingress controllers, operators, observability), with namespace and how services reach
   them (from the bridges).
3. **Variants**: what each recurring variant means (disaster recovery copy, perf test,
   v2 migration), taken from facts. Unanswered: cite the question.
4. **Exposure**: public hosts per ingress and what they route to.
5. **Oddities**: scaled to zero, suspended jobs, apps pointing to missing paths, images
   pinned to `latest`, workloads with no source. Each cites the file and the question.

## `map/DEPLOY.md`

Above the generated block, a short narrative: which projects run in prod and as what,
what is built but not deployed (with the liveness question or fact), what runs from
excluded or legacy paths, and what runs with no tracked source.

## Update (mode `inventory`)

The bundle lists changed YAML files. Re-run `ando map` first (the runner usually did),
then edit only the prose the change affects: a new workload, a removed one, a variant,
a new host, a schedule change. Tag bumps alone need no prose change.

## Never

- Copy values from `Secret` objects, `stringData`, or credential-looking env values.
- Claim something runs because a YAML file exists: Argo apps, overlays and
  `replicas: 0` decide that. When unsure, ask.
- Describe the live cluster state. The repo is what you read; say "declared".
