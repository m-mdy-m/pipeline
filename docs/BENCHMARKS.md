# Benchmark methodology

Use .github/workflows/benchmark.yml to run a command repeatedly and preserve its output. The benchmark runner records iteration timestamps and elapsed milliseconds, then emits a summary with minimum, median, mean, and maximum duration.

## Categories

- **Micro:** one operation repeated many times.
- **Throughput:** report MiB/s, requests/s, or operations/s; include warm-up and sustained runs.
- **Latency:** report p50/p90/p95/p99 where meaningful and distinguish cold start from steady state.
- **Memory:** report peak RSS, allocation count/bytes, heap growth, and dataset size.
- **Startup:** measure cold and warm process/build startup separately.
- **Scalability:** vary workers, concurrency, and input size; record where throughput stops scaling.
- **Regression:** compare the same runner class, commit base, compiler, flags, and fixture.
- **Size:** report binary/package/image size and distinguish compressed from uncompressed size.

## Output artifacts

Each benchmark artifact contains:

- iterations.csv: category, iteration, start time, elapsed milliseconds, and exit code.
- One log file per iteration, containing stdout and stderr.
- summary.csv: run count and min/median/mean/max milliseconds.
- environment.txt: runner OS/kernel, CPU details, and memory information.
- Intermediate duration files used to calculate the summary.

## Reproducibility rules

1. Never compare measurements from different runner types as if they were equivalent.
2. Preserve raw output alongside any aggregate statistics.
3. Use at least five repetitions for noisy workloads and more for stable statistics.
4. Record command line, version, OS, CPU, RAM, compiler/runtime, input size, and cache state.
5. Do not turn a noisy percentage change into a hard CI failure until thresholds have been calibrated.

## This repository's self-benchmark

benchmark-self.yml runs two measurements when the workflow catalog changes: five repetitions of make check, and five samples of tracked file/byte and workflow counts. The first is a CI-maintenance timing, not a microbenchmark of application code. Check the run's artifacts for the raw logs and calculated timing summary.
