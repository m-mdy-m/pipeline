# Running benchmarks

A benchmark measures how long something takes or how much of a resource it uses. The reusable [benchmark workflow](../.github/workflows/benchmark.yml) runs a command several times and saves the results so you can inspect them later.

## Basic idea

1. Choose one command to measure.
2. Choose a category, such as `startup`, `throughput`, `latency`, or `size`.
3. Choose how many times to repeat it.
4. Review both the summary and the raw logs.

The summary reports minimum, median, mean, and maximum time. The raw files help you understand unusual results.

## What gets saved?

The workflow uploads an artifact containing:

- `iterations.csv`: one row for each run, including duration and exit code.
- One log per run: the command's output.
- `summary.csv`: a short timing summary.
- Environment details: information about the runner.

## Make results useful

- Compare runs on the same type of machine whenever possible.
- Keep the command, input, compiler/runtime, and build settings the same.
- Repeat noisy measurements more times.
- Keep raw logs; averages alone can hide a failure or an unusual run.
- Treat small differences carefully. Do not fail CI on a percentage threshold until you know normal variation.

## This repository's benchmark

The self-benchmark workflow measures the time needed to run this repository's checks and records the size of the tracked source and workflow catalog. It is a maintenance measurement, not a benchmark of an application.
