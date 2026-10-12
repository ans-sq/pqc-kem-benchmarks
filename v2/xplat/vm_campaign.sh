#!/usr/bin/env bash
# Cross-platform replication, step 2 (runs on the VM after vm_build.sh): the
# CPU campaign of cpu/cpu_campaign.sh pinned to vCPU 1 (VMs expose no RAPL
# energy counters and no frequency control, so neither is attempted), then
# the TLS provider-path control. Output goes to v2/data/ under the laptop's
# file names; provision.sh fetch copies it to data/xplat/<host>/.
set -uo pipefail
B=/home/anss/random/bench; V2=$B/v2; D=$V2/data; CPU=1
mkdir -p $D
cd $V2/cpu
{ echo "date: $(date -Is)"; uname -a; lscpu
  echo "--- cpufreq: $(ls /sys/devices/system/cpu/cpu$CPU/cpufreq 2>/dev/null || echo none)"
  gcc-11 --version | head -1; $B/quic/openssl-install/bin/openssl version
  echo "liboqs 5a1a854 (0.16.0) and f986aea (0.15.0); official HQC 161cd4f; oqs-provider 7e9d095 (0.12.0)"
} > $D/env_cpu.txt 2>&1
for rep in 1 2 3; do
  LD_LIBRARY_PATH=../install-016/lib taskset -c $CPU ./bench_kem016 016_r$rep 3 31 > $D/cpu_016_r$rep.csv
  if [ -d ../install-016-O3 ]; then
    ONLY=McEliece LD_LIBRARY_PATH=../install-016-O3/lib taskset -c $CPU ./bench_kem016 016O3_r$rep 3 31 \
      > $D/cpu_016O3_r$rep.csv
  fi
  ONLY=HQC LD_LIBRARY_PATH=../install-default/lib taskset -c $CPU ./bench_kem 015_r$rep 3 31 > $D/cpu_015_r$rep.csv
  ONLY=HQC LD_LIBRARY_PATH=../install-O3/lib taskset -c $CPU ./bench_kem 015O3_r$rep 3 31 > $D/cpu_015O3_r$rep.csv
  echo "$(date +%T) cpu rep $rep done"
done
cd $V2
unshare -r -n python3 -I tls/tls_campaign.py provider > $D/tls_provider.csv 2> $D/tls_provider.log
echo "$(date +%T) tls provider control done ($(grep -c . $D/tls_provider.csv) lines)"
echo "$(date +%T) ALL DONE"
