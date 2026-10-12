#!/usr/bin/env bash
# Measurement controls for the CPU and energy runs (needs root).
#   sudo bash controls.sh on    fix the clock: performance governor + EPP,
#                               turbo off (P-cores at 1.7 GHz base), keep the
#                               P-cores (cpu0-3) out of the deep idle states
#                               C2/C3 (127 us / 1 ms exit latency) that would
#                               otherwise add wake-up delay after every RTT
#                               wait, and make the RAPL counters readable
#   sudo bash controls.sh off   restore the saved state exactly
#   sudo bash controls.sh show  print the current state
set -euo pipefail
STATE=/var/tmp/pqc_bench_controls.state
CPUS=/sys/devices/system/cpu
RAPL=$(ls -d /sys/class/powercap/intel-rapl:*/ /sys/class/powercap/intel-rapl:*:*/ 2>/dev/null)

PCORES="0 1 2 3"
DEEP="2 3"   # cpuidle states to hold off on the P-cores (C2_ACPI, C3_ACPI)

show() {
  echo "governor(cpu2)=$(cat $CPUS/cpu2/cpufreq/scaling_governor)" \
       "epp(cpu2)=$(cat $CPUS/cpu2/cpufreq/energy_performance_preference 2>/dev/null)" \
       "no_turbo=$(cat $CPUS/intel_pstate/no_turbo)"
  for z in $RAPL; do echo "$z energy_uj mode $(stat -c %a $z/energy_uj)"; done
  for c in $PCORES; do for st in $DEEP; do
    echo -n "cpu$c state$st disable=$(cat $CPUS/cpu$c/cpuidle/state$st/disable) "; done; echo; done
}

case "${1:-show}" in
  on)
    [ -f $STATE ] || {
      { echo "NO_TURBO=$(cat $CPUS/intel_pstate/no_turbo)"
        for c in $CPUS/cpu[0-9]*; do
          n=$(basename $c)
          echo "GOV_$n=$(cat $c/cpufreq/scaling_governor)"
          echo "EPP_$n=$(cat $c/cpufreq/energy_performance_preference 2>/dev/null || echo none)"
        done
        for c in $PCORES; do for st in $DEEP; do
          echo "IDLE_${c}_${st}=$(cat $CPUS/cpu$c/cpuidle/state$st/disable)"; done; done; } > $STATE
    }
    for c in $CPUS/cpu[0-9]*; do
      echo performance > $c/cpufreq/scaling_governor
      [ -w $c/cpufreq/energy_performance_preference ] && \
        echo performance > $c/cpufreq/energy_performance_preference 2>/dev/null || true
    done
    echo 1 > $CPUS/intel_pstate/no_turbo
    for c in $PCORES; do for st in $DEEP; do echo 1 > $CPUS/cpu$c/cpuidle/state$st/disable; done; done
    for z in $RAPL; do chmod o+r $z/energy_uj; done
    show ;;
  off)
    [ -f $STATE ] || { echo "no saved state"; exit 1; }
    . $STATE
    for c in $CPUS/cpu[0-9]*; do
      n=$(basename $c); g=GOV_$n; e=EPP_$n
      echo ${!g} > $c/cpufreq/scaling_governor
      [ "${!e}" != none ] && echo ${!e} > $c/cpufreq/energy_performance_preference 2>/dev/null || true
    done
    echo $NO_TURBO > $CPUS/intel_pstate/no_turbo
    for c in $PCORES; do for st in $DEEP; do v=IDLE_${c}_${st}
      echo ${!v} > $CPUS/cpu$c/cpuidle/state$st/disable; done; done
    for z in $RAPL; do chmod o-r $z/energy_uj; done
    rm -f $STATE
    show ;;
  show) show ;;
esac
