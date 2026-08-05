# Performance baseline

This document records repeatable evidence for the v0.7.0 `large` profile. It
is an engineering baseline from one fixed machine, not a speed SLA for other
machines or repositories.

## Measurement contract

- The generator seed and repository contents are deterministic.
- Every benchmark is warmed once and then measured three times.
- Wall time uses `time.perf_counter_ns()` and the table reports the median.
- Traced peak memory uses `tracemalloc`; the table reports the largest sample.
- RSS uses `ru_maxrss`. On macOS it is already bytes; on Linux it is converted
  from KiB to bytes. RSS is a process-lifetime peak and can carry a previous
  benchmark's high-water mark.
- Every measured invocation verifies its output count and logical digest.
- CI checks every `ci` sample against broad safety limits of 30 seconds and
  512 MiB traced peak memory. It does not compare exact timing constants.

Run the profiles with:

```bash
poetry run python scripts/run_benchmarks.py --profile ci --json
poetry run python scripts/run_benchmarks.py --profile large --json
```

## Fixed-machine large baseline

Measured on 2026-08-05 with:

- Machine: MacBook Pro (`MacBookPro17,1`)
- CPU: Apple M1, 8 cores
- Memory: 16 GB
- OS: macOS 26.5.2, arm64
- Python: CPython 3.13.12
- Git base SHA: `366d747c5aad985ac6ca1885df40dc73791cfc8e`
- Profile: 1,000 modules, 10 functions per module, 2,000 pytest tests,
  25 Git commits, and 100,000 JSONL events

Times are seconds. Memory values are bytes.

| Benchmark | Raw wall times | Median | Raw traced peaks | Max traced | Raw RSS peaks | Max RSS |
| --- | --- | ---: | --- | ---: | --- | ---: |
| `snapshot_and_symbols` | 5.119888, 5.064129, 5.032380 | 5.064129 | 5,943,749; 5,935,657; 7,853,312 | 7,853,312 | 48,168,960; 50,135,040; 52,248,576 | 52,248,576 |
| `test_index_and_selection` | 13.330789, 13.317088, 13.107924 | 13.317088 | 8,616,591; 8,467,783; 8,467,308 | 8,616,591 | 60,702,720; 66,011,136; 66,011,136 | 66,011,136 |
| `git_symbol_history` | 0.032158, 0.035517, 0.031862 | 0.032158 | 91,804; 91,772; 91,595 | 91,804 | 66,011,136; 66,011,136; 66,011,136 | 66,011,136 |
| `pytest_jsonl_parser` | 0.496324, 0.489740, 0.481086 | 0.489740 | 22,228; 22,252; 22,252 | 22,252 | 66,011,136; 66,011,136; 66,011,136 | 66,011,136 |
| `repository_persistence` | 0.005822, 0.005183, 0.005494 | 0.005494 | 35,455; 35,271; 35,239 | 35,455 | 66,011,136; 66,011,136; 66,011,136 | 66,011,136 |

Stable output digests from this run:

| Benchmark | Output digest |
| --- | --- |
| `snapshot_and_symbols` | `87cd3329376ac911f2b8ba8f5dc865604444965c5fa3951a1d74729f110b6466` |
| `test_index_and_selection` | `67b8ba919d0c3155fd5b3baec503f41b9389ecf885367736fc07353752cfff45` |
| `git_symbol_history` | `cf576f5805f08b66f1997a6c95677e4db97bdb17ba403fbe893059e322d98fb1` |
| `pytest_jsonl_parser` | `4d4d14cc7c8648cd0166d1d04d3069d69a7785d06ef2b7f44551ec24d36697ff` |
| `repository_persistence` | `86989e6952a977161dcd5b9c441a0e6c58df4b76abfb6b93a4e62bf2bf9f4d55` |

The generated fixture and raw temporary report are intentionally not tracked.
The report contains counts, measurements, and digests only; it contains no
fixture absolute path or project source text.
