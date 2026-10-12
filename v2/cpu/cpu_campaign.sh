#!/usr/bin/env bash
# CPU-time and energy campaign. Run AFTER `sudo bash controls.sh on` (fixed
# 1.7 GHz clock, turbo off). Everything is pinned to logical CPU 2 (P-core).
# One harness source, compiled against liboqs 0.16.0 (bench_kem016) and 0.15.0
# (bench_kem), measures every liboqs build selected via LD_LIBRARY_PATH and the
# six official HQC variants (2025 spec, ref and AVX2) linked into both:
#   016     liboqs 0.16.0 as released (primary table, all families)
#   016O3   0.16.0 with Classic McEliece AVX2 at -O3 instead of -O1
#   015     liboqs 0.15.0 as released (HQC 2023 spec, reference code at -O0)
#   015O3   0.15.0 with HQC reference code at -O3

set -euo pipefail
cd "$(dirname "$0")"
D=../data
{ echo "date: $(date -Is)"; uname -a; lscpu | grep -E "Model name|MHz"
  echo "governor(cpu2)=$(cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor) no_turbo=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)"
  echo "cur_khz(cpu2)=$(cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_cur_freq)"
  gcc-11 --version | head -1; openssl version
  echo "liboqs 5a1a854 (0.16.0) and f986aea (0.15.0); official HQC 161cd4f; oqs-provider 7e9d095 (0.12.0)"; } > $D/env_cpu.txt
for rep in 1 2 3; do
  LD_LIBRARY_PATH=../install-016/lib taskset -c 2 ./bench_kem016 016_r$rep 3 31 > $D/cpu_016_r$rep.csv
  ONLY=McEliece LD_LIBRARY_PATH=../install-016-O3/lib taskset -c 2 ./bench_kem016 016O3_r$rep 3 31 > $D/cpu_016O3_r$rep.csv
  ONLY=HQC LD_LIBRARY_PATH=../install-default/lib taskset -c 2 ./bench_kem 015_r$rep 3 31 > $D/cpu_015_r$rep.csv
  ONLY=HQC LD_LIBRARY_PATH=../install-O3/lib taskset -c 2 ./bench_kem 015O3_r$rep 3 31 > $D/cpu_015O3_r$rep.csv
  echo "cpu rep $rep done"
done
ENERGY=1 LD_LIBRARY_PATH=../install-016/lib taskset -c 2 ./bench_kem016 energy_016 5 5 > $D/energy_016.csv
ENERGY=1 ONLY=McEliece LD_LIBRARY_PATH=../install-016-O3/lib taskset -c 2 ./bench_kem016 energy_016O3 5 5 > $D/energy_016O3_mceliece.csv
echo "energy done"
