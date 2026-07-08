# Methodology

## Boundary

Oneiros is treated as a black-box memory service. CEO-Bench-specific code stays in this repository or in a CEO-Bench fork. Oneiros should not gain benchmark-specific modules or commands.

## Run State

Each run gets isolated state:

```text
runs/<run_id>/
  ceobench_workspace/
  oneiros/
    oneiros.db
    conversations/fresh/
    conversations/archive/
  weeks/
```

The runner sets:

```text
ONEIROS_DB_PATH=<run>/oneiros/oneiros.db
ONEIROS_CONVERSATIONS_DIR=<run>/oneiros/conversations
```

The benchmark model/provider settings are inherited from `~/.oneiros/config.toml` by default. The runner reads Oneiros' Azure extractor section at runtime, uses the same endpoint, deployment, API version, API key, and CA bundle for benchmark subprocesses, and writes only redacted/non-secret provider metadata to run manifests.

## Weekly Ingestion

After a successful `next-week`, the runner stages one observed weekly transcript as a canonical Oneiros conversation under `conversations/fresh/`, then runs:

```bash
oneiros extract --session <week-session-id>
```

The next week starts only after extraction succeeds.

Every extraction call passes Oneiros' native `--record-to` flag. The per-week event stream is written to `runs/<run_id>/logs/week_NNN_extract.jsonl`, so long-running extraction can be monitored with `tail -f`.

## Leakage Rule

Live ingestion must exclude hidden simulator state, including `world.nmdb`. Hidden state can be used after the run for scoring and analysis only.
