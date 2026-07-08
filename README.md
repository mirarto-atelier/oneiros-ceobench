# oneiros-ceobench

Public benchmark runner and results site for evaluating Oneiros on CEO-Bench.

This repository keeps the benchmark integration outside both upstream projects:

- `oneiros` remains a generic long-term memory system.
- `ceobench-src` remains the benchmark and simulator checkout.
- `oneiros-ceobench` owns experiment orchestration, run-scoped Oneiros state, transcript staging, compact results, and the GitHub Pages site.

## Current Scope

This is the initial scaffold. It supports:

- reproducible run manifests,
- Azure OpenAI-oriented GPT model configuration,
- run-scoped Oneiros paths,
- observed weekly transcript staging into Oneiros' canonical conversation format,
- synchronous per-week extraction barriers,
- compact result aggregation for GitHub Pages.

It does not yet patch CEObench's Codex runner. That work should live here or in a CEObench fork, not in Oneiros.

## Layout

```text
configs/              Reproducible benchmark configs
docs/                 GitHub Pages site
oneiros_ceobench/     Runner package
prompts/              Benchmark AGENTS.md prompt variants
results/              Sanitized compact summaries
runs/                 Local raw run artifacts, gitignored
```

## Quickstart

```bash
uv sync --extra dev
uv run oneiros-ceobench init --config configs/azure_gpt_oneiros_smoke.yaml
```

The command creates a local run directory under `runs/`:

```text
runs/<run_id>/
  manifest.json
  ceobench_workspace/
  oneiros/
    oneiros.db
    conversations/fresh/
    conversations/archive/
  prompts/AGENTS.md
  weeks/
```

To stage and extract one observed weekly transcript:

```bash
uv run oneiros-ceobench ingest-week \
  --run-dir runs/<run_id> \
  --week 1 \
  --jsonl examples/week_001_observed.jsonl
```

Weekly transcript input is OpenAI-style JSONL with `role`, `content`, and optional `timestamp` fields. System messages are ignored; `user`, `assistant`, `tool`, and `function` messages are kept.

## Azure OpenAI

The default config is Azure OpenAI-oriented because the intended benchmark path uses GPT deployments instead of Anthropic models.

Set the provider values expected by your CEObench/Codex adapter layer:

```bash
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_API_VERSION="..."
export AZURE_OPENAI_DEPLOYMENT="..."
```

The scaffold records this provider intent in `manifest.json`; it does not call Azure OpenAI directly yet. The CEObench agent wrapper will consume these settings when the runnable benchmark loop is added.

## Leakage Boundary

Only agent-observed weekly material should enter Oneiros during a run:

- dashboard text,
- agent decisions and rationale,
- simulator CLI/tool calls made by the agent,
- tool outputs returned to the agent,
- returned dashboard after `next-week`.

Do not ingest `world.nmdb` or hidden simulator state during the live run. Raw run artifacts stay under `runs/` and are gitignored.
