# Run a benchmark

The benchmark runner measures how long a command takes, repeats it, and saves the results. It works locally and can also be called by the reusable GitHub workflow.

A benchmark is only useful when you compare the same command, data, and machine conditions. The runner records the environment to make those comparisons easier.

## Run it from a terminal

The benchmark runner uses Bash to execute the command, so Bash must be available. This is normally the case on Linux and macOS. On Windows, use WSL or Git Bash.

From the repository root:

~~~sh
python scripts/benchmark.py \
  --command "python -m unittest discover -s tests" \
  --category startup \
  --repetitions 5
~~~

The command is executed five times. Each run is timed separately.

## Prepare before measuring

Use `--setup-command` for work that should happen once before the timer starts. For example, compile an application before measuring its startup:

~~~sh
python scripts/benchmark.py \
  --setup-command "make build" \
  --command "./build/my-app --version" \
  --category startup \
  --repetitions 10
~~~

The setup command is not included in the measured durations. If setup fails, no benchmark iteration starts.

## Options

| Option | Required? | Meaning |
|---|---|---|
| `--command` | Yes | Command to run for every measurement |
| `--category` | Yes | Label for the result, such as `startup` or `throughput` |
| `--repetitions` | Yes | Number of runs, from 1 to 1000 |
| `--working-directory` | No | Directory where setup and benchmark commands run; defaults to `.` |
| `--output-directory` | No | Where reports are written; defaults to `benchmark-results` inside the working directory |
| `--setup-command` | No | One-time setup command that runs before measurements |

Categories are labels. Choosing `memory` does not automatically measure RAM; the benchmark command must collect the metric you care about and print or save it.

If one measured run returns a non-zero exit code, the runner stops repeating the command, writes the results collected so far, and exits with that code.

## Files it creates

The default `benchmark-results/` directory contains:

| File | Contents |
|---|---|
| `iterations.csv` | One row per attempt, including start time, duration, and exit code |
| `summary.csv` | Minimum, median, mean, and maximum duration, plus the run count |
| `summary.json` | The same summary in JSON format, including the final exit code |
| `summary.md` | A short Markdown summary |
| `durations.txt` | Durations in run order |
| `durations.sorted.txt` | The same durations sorted from shortest to longest |
| `environment.txt` | Operating system, machine, processor, CPU count, and Python version |
| `startup-1.log` | Example log for the first `startup` run; the category and number change |
| `setup.log` | Created only when a setup command is used |

The command's output and error output are written to its log file. The runner does not upload anything; a CI workflow can upload the result directory as an artifact.

## Use the GitHub workflow

~~~yaml
jobs:
  benchmark:
    uses: m-mdy-m/pipeline/.github/workflows/benchmark.yml@v1.0.0
    with:
      pipeline-ref: v1.0.0
      category: startup
      repetitions: 5
      benchmark-command: python -m unittest discover -s tests
~~~

The workflow runs the shared script and uploads the reports. Keep `pipeline-ref` on the same reviewed tag or commit as the `uses` reference. That way, the workflow and the script it calls come from the same version.

## Compare results fairly

- Use the same machine class when comparing versions.
- Keep compiler flags, input data, and runtime versions unchanged.
- Repeat noisy measurements more times.
- Read the run logs, not just the average.
- Do not treat a small timing difference as proof of an improvement.
