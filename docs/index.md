# Oneiros on CEO-Bench

This site tracks public results for running CEO-Bench with Oneiros as an external long-term memory system.

## Goal

CEO-Bench already reports baseline results for frontier models operating out of the box. This project asks a narrower question:

> How does a comparable GPT model perform when given Oneiros as a persistent, run-scoped memory system across weekly reset boundaries?

## Method

- Run CEO-Bench with the standard simulator and scoring.
- Use Azure OpenAI-hosted GPT deployments for the benchmarked agent path.
- Start each simulated week as a fresh agent conversation.
- Persist only the CEO-Bench workspace and run-scoped Oneiros state across weeks.
- Ingest only agent-observed weekly transcripts into Oneiros.
- Extract after each successful `next-week` before the next week starts.
- Compare the resulting score against the published CEO-Bench paper baselines.

## Current Status

The repository currently contains configs, prompt, run manifest tooling, Oneiros transcript staging, CEO-Bench Codex loop orchestration, and result aggregation. Full benchmark result summaries will appear here after runs are completed.

## Run The Benchmark

Prerequisites:

- A local `oneiros-ceobench` checkout.
- Local sibling checkouts of `ceobench-src` and `oneiros`, or updated paths in `configs/azure_gpt_oneiros_smoke.yaml`.
- Azure OpenAI settings available through your Oneiros config, typically `~/.oneiros/config.toml`.
- `uv`, `codex`, and `oneiros` available on `PATH`.

Install local dependencies:

```bash
uv sync --extra dev
```

Validate the resolved config without printing secrets:

```bash
uv run oneiros-ceobench doctor --config configs/azure_gpt_oneiros_smoke.yaml
```

Validate the CEO-Bench path, model, and Codex config overrides without launching the benchmark:

```bash
uv run oneiros-ceobench run-codex \
  --config configs/azure_gpt_oneiros_smoke.yaml \
  --run-id smoke-codex-oneiros \
  --dry-run
```

Start the smoke benchmark:

```bash
uv run oneiros-ceobench run-codex \
  --config configs/azure_gpt_oneiros_smoke.yaml \
  --run-id smoke-codex-oneiros
```

Tail the orchestration log:

```bash
tail -f runs/smoke-codex-oneiros/logs/pipeline.jsonl
```

Each successful week writes `runs/<run_id>/weeks/week_NNN_observed.jsonl`, stages it into run-scoped Oneiros state, runs `oneiros extract --record-to runs/<run_id>/logs/week_NNN_extract.jsonl`, and only then starts the next week.

## Data

The site data file is [`data/runs.json`](data/runs.json). It contains compact, sanitized result summaries only.
