# Benchmark methodology

Different workloads need different benchmark strategies. Keep each benchmark reproducible and report environment metadata.

## Categories

- **Microbenchmarks:** one operation, many iterations; report median, p95/p99 where meaningful, and variance.
- **Throughput:** MiB/s, requests/s, operations/s; include warm-up and sustained runs.
- **Latency:** p50/p90/p95/p99; distinguish cold-start from steady-state.
- **Memory:** peak RSS, allocation count/bytes, heap growth, and dataset size.
- **Startup/build:** cold and warm build times, clean cache before cold runs.
- **Scalability:** vary workers/concurrency and input size; record where throughput stops scaling.
- **Regression:** compare the same commit base, machine class, compiler, flags, and fixture.
- **Size:** binary/package/image size; report compressed and uncompressed sizes separately.

## Rules

1. Never compare measurements from different runner types as if they were equivalent.
2. Preserve raw JSON/CSV output as a workflow artifact.
3. Use at least 5 repetitions for noisy workloads; use more for stable statistics.
4. Include command line, version, OS, CPU, RAM, compiler/runtime, input size, and cache state.
5. Do not turn a noisy percentage change into a hard CI failure without a calibrated threshold.
