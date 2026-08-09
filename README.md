# Artifact: Post-Quantum Key Establishment After Standardization

Benchmark scripts, raw measurement data, and analysis code for the paper:

> A. Sohail, "Post-Quantum Key Establishment After Standardization: An
> Experimental Comparison of ML-KEM, NTRU, HQC, and Classic McEliece," 2026.

Every measured number, table, and figure in the paper's experimental
sections is regenerable from this repository: the scripts are the ones
that produced the shipped raw data, and the analysis stage re-derives
the reported statistics from that data.

## Repository layout

```
scripts/
  transport/   Emulated ephemeral key-exchange latency and loss (Fig. 4,
               Table XII) and the real-WAN validation run (Sec. X-E)
  tls/         TLS 1.3 handshake benchmark via openssl s_server/s_client
               with the oqs-provider (Table XIII)
  quic/        OpenSSL 3.5 QUIC build + PQC-over-QUIC handshake check (Sec. X-F)
  energy/      Intel RAPL package-energy bracketing (x86) and the
               mobile-device energy parser (Sec. X-C)
  memory/      Peak-heap profiling of one full KEM operation under
               valgrind massif (Sec. X-C)
  analysis/    Descriptive statistics, bootstrap CIs, Mann-Whitney U /
               Cliff's delta tests over the raw CSVs (Sec. X-A)
  framework/   Entropy-weighted TOPSIS selection framework, scenario
               rankings, sensitivity and crossover analysis (Sec. XI,
               Tables XIV-XV)
  figures/     Figure generation for all four paper figures
data/
  cpu-x86/     liboqs speed_kem output (16 parameter sets) and the
               official HQC AVX2 benchmark output (Table X)
  cpu-arm/     liboqs speed_kem output on a Pixel 7 Pro under Termux
               (Table XI)
  energy-arm/  Mobile per-scheme energy CSVs and idle baseline
  transport/   Per-trial latency CSVs: emulated RTT sweep, the 300-trial
               1% loss run (Table XII), and the real-WAN run
  tls/         Per-trial TLS 1.3 handshake times and byte counts
  memory/      Raw massif profiles per family
figures/       The four PDFs exactly as included in the paper
```

## Measurement environment

| Component | Version |
|---|---|
| CPU (x86) | Intel Core i7-1355U, AVX2 active |
| OS / toolchain | Linux 6.17, gcc 11.4.0 |
| liboqs | 0.15.0, commit `f986aea`, Release build, HQC re-enabled at build time |
| TLS stack | OpenSSL 3.0.2 + oqs-provider commit `8b87173` |
| QUIC stack | OpenSSL 3.5 built from source (`scripts/quic/build_openssl35.sh`) |
| Official HQC | pqc-hqc reference repository commit `161cd4f`, `HQC_ARCH=x86_64` (AVX2) |
| ARM device | Google Pixel 7 Pro (Tensor G2, AArch64), liboqs 0.15.0 in Termux |

The paper's Section X-A documents the methodology; the netem emulation
runs in an unprivileged user+network namespace (`unshare -r -n`), so no
root is required except where noted (RAPL energy counters).

## Reproducing the results

Scripts were run in place from a working directory containing liboqs
and oqs-provider builds; hardcoded paths of the form
`/home/anss/random/bench` mark those locations — adjust them (or build
into the same layout) before running. The upstream dependencies are not
vendored; pin them to the commits above:

```sh
git clone https://github.com/open-quantum-safe/liboqs && cd liboqs
git checkout f986aea
cmake -B build -DCMAKE_BUILD_TYPE=Release -DOQS_ENABLE_KEM_HQC=ON \
      -DCMAKE_INSTALL_PREFIX=../install
cmake --build build --parallel && cmake --install build
```

| Paper result | Produce with | Shipped raw data |
|---|---|---|
| Table X (CPU, x86) | `liboqs/build/tests/speed_kem`; official HQC bundled bench | `data/cpu-x86/` |
| Table XI (CPU, ARM) | same harness under Termux | `data/cpu-arm/pixel_cpu.txt` |
| Energy (Sec. X-C) | `sudo python3 scripts/energy/energy_rapl.py` | printed report; ARM CSVs in `data/energy-arm/` |
| Peak heap (Sec. X-C) | `bash scripts/memory/run_mem.sh` | `data/memory/ms_*.out` |
| Fig. 4 + Table XII | `unshare -r -n python3 scripts/transport/kex_transport_bench.py`; then `python3 scripts/transport/loss_table.py` | `data/transport/` |
| Real-WAN validation | `scripts/transport/run_wan.sh` (set `WAN_HOST`, `WAN_USER`, `WAN_KEY`) | `data/transport/wan_transport_results.csv` |
| Table XIII (TLS 1.3) | `unshare -r -n bash scripts/tls/tls_bench.sh` | `data/tls/tls_results.csv` |
| QUIC check (Sec. X-F) | `bash scripts/quic/build_openssl35.sh`, then `bash scripts/quic/run_quic.sh` | printed report |
| Reported statistics | `python3 scripts/analysis/stats_rigor.py` / `analyze_stats.py` | reads `data/` |
| Tables XIV-XV (framework) | `python3 scripts/framework/mcdm.py` / `mcdm_robust.py` | self-contained |
| Figures 1-4 | `python3 scripts/figures/make_figures.py` / `make_bench_figures.py` | `figures/` |

The TLS benchmark generates its own throwaway server certificate; no
key material ships in this repository. The statistical scripts use a
fixed RNG seed, so the bootstrap intervals reproduce exactly.

Python dependencies: `pip install -r requirements.txt`.

## Licenses

- **Code** (`scripts/`): MIT License (see `LICENSE`).
- **Data** (`data/`, `figures/`): Creative Commons Attribution 4.0
  International (CC BY 4.0, see `data/LICENSE`).

## Citing

If you use this artifact, please cite the paper above; see
`CITATION.cff` for machine-readable metadata. An archived, DOI-carrying
snapshot of each release is deposited on Zenodo.
