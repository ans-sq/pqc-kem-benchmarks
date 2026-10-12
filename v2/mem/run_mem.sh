#!/usr/bin/env bash
# Peak memory of one complete ephemeral exchange (KeyGen+Encaps+Decaps) per
# category-1 set under valgrind massif, heap AND stack (--stacks=yes; liboqs
# documents Classic McEliece as a large-stack implementation). Pinned to an
# efficiency core so it cannot disturb the P-core campaigns.
set -euo pipefail
cd "$(dirname "$0")"
gcc-11 -O2 mem_kem.c -I ../install-016/include -L ../install-016/lib -loqs -lcrypto -o mem_kem
echo "build,scheme,peak_heap_B,peak_stack_B,peak_total_B"
for spec in "016 ML-KEM-512" "016 NTRU-HPS-2048-677" "016 HQC-1" "016-hqcavx2 HQC-1" "016 Classic-McEliece-348864"; do
  set -- $spec
  out=ms_${1}_$2.out
  LD_LIBRARY_PATH=../install-$1/lib taskset -c 10 valgrind --tool=massif --stacks=yes \
      --massif-out-file=$out ./mem_kem $2 >/dev/null 2>&1
  python3 -I - "$out" "$1" "$2" <<'PY'
import sys
snaps, cur = [], {}
for line in open(sys.argv[1]):
    if line.startswith("snapshot="):
        if cur: snaps.append(cur)
        cur = {}
    for k in ("mem_heap_B", "mem_heap_extra_B", "mem_stacks_B"):
        if line.startswith(k + "="):
            cur[k] = int(line.split("=")[1])
if cur: snaps.append(cur)
heap = max(s.get("mem_heap_B", 0) + s.get("mem_heap_extra_B", 0) for s in snaps)
stack = max(s.get("mem_stacks_B", 0) for s in snaps)
tot = max(s.get("mem_heap_B", 0) + s.get("mem_heap_extra_B", 0) + s.get("mem_stacks_B", 0) for s in snaps)
print(f"{sys.argv[2]},{sys.argv[3]},{heap},{stack},{tot}")
PY
done
