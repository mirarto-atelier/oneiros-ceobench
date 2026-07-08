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

The repository currently contains the public scaffold: configs, prompt, run manifest tooling, Oneiros transcript staging, and result aggregation. Full benchmark runs will appear here after the CEOBench agent wrapper is wired.

## Data

The site data file is [`data/runs.json`](data/runs.json). It contains compact, sanitized result summaries only.
