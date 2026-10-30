# Running benchmarks

The shared benchmark runner measures a command several times and saves the raw output and timing data. The same script can run locally or inside a CI workflow.

## Run it locally

From the repository root, run:

~~~sh
python scripts/benchmark.py \
  --command "python -m unittest discover -s tests" \
  --category startup \
  --repetitions 5 \
  --working-directory . \
  --output-directory benchmark-results
~~~

The command is executed by Bash. An optional `--setup-command` can prepare files or build the program before timing begins. Setup time is not included in the measured runs.

Supported categories are `micro`, `throughput`, `latency`, `memory`, `startup`, `scalability`, `regression`, and `size`. A run must complete successfully for the benchmark command to return success.

## Use the reusable workflow

A caller workflow can run the same script on a GitHub-hosted runner:

~~~yaml
jobs:
  benchmark:
    uses: m-mdy-m/pipeline/.github/workflows/benchmark.yml@main
    with:
      pipeline-ref: main
      category: startup
      repetitions: 5
      benchmark-command: python -m unittest discover -s tests
~~~

Set `pipeline-ref` to the same reviewed tag or commit used by the `uses` reference. The project being measured and the helper scripts are checked out separately.

## Result files

The runner creates a `benchmark-results/` directory containing:

- `iterations.csv` — start time, duration, and exit code for every attempt.
- `summary.csv` and `summary.json` — minimum, median, mean, maximum, and run count.
- `summary.md` — a compact report suitable for a CI run summary.
- `durations.txt` and `durations.sorted.txt` — raw and sorted timing values.
- One `<category>-<number>.log` file for each measured run.
- `setup.log` when a setup command is used.
- `environment.txt` with operating system, machine, processor, CPU count, and Python version.

The GitHub workflow uploads this directory as an artifact. The runner itself does not know how or where the artifact is stored.

## Compare results carefully

- Compare runs from the same machine class whenever possible.
- Keep inputs, build flags, and runtime versions consistent.
- Repeat noisy measurements more often.
- Read the raw logs as well as the summary.
- Treat small changes cautiously; a timing difference is not automatically a performance improvement.
