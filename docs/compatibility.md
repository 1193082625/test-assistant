# Compatibility support

> Release: `v0.6.2`
> Generated from `docs/compatibility.json`; do not edit manually.

States: `supported` is release-blocking evidence, `experimental` is
non-blocking observation, and `unsupported` is outside the release claim.

## Operating systems

| Capability | State | Evidence or reason |
| --- | --- | --- |
| macOS (GitHub macos-latest) | `supported` | Python 3.13 wheel consumption and Doctor smoke in CI |
| Ubuntu (GitHub ubuntu-latest) | `supported` | Python 3.13 wheel consumption and Doctor smoke in CI |
| Windows | `unsupported` | No Windows runner or process interruption certification |

## Python

| Capability | State | Evidence or reason |
| --- | --- | --- |
| Python 3.13 | `supported` | Package metadata, full test suite and wheel smoke |
| Python 3.14 | `experimental` | Non-blocking Doctor probe; package installation is rejected |

## pytest

| Capability | State | Evidence or reason |
| --- | --- | --- |
| pytest 9.0 | `supported` | Validated in fitstyle-backend with pytest 9.0.2 |
| pytest 9.1 | `supported` | Validated by clean wheel smoke with pytest 9.1.1 |

## Paths and filesystems

| Capability | State | Evidence or reason |
| --- | --- | --- |
| Paths containing spaces | `supported` | Real CLI subprocess and no-write assertions |
| Chinese/Unicode paths | `supported` | Real CLI subprocess and JSON round trip |
| Long nested paths | `supported` | Deterministic nested-path CLI test within platform limits |
| Project directory symlink | `supported` | Resolved to the canonical directory without writes |
| Broken project symlink | `supported` | Rejected before workflow execution with exit code 2 |
| Non-Git project | `supported` | Git capability degrades without failing core Doctor status |
| Read-only project directory | `supported` | Text and JSON Doctor complete without project writes |
