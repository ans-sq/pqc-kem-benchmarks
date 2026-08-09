#!/usr/bin/env bash
# Peak-heap per KEM (reviewer item #5): build mem_kem against the installed
# liboqs and profile one KeyGen+Encaps+Decaps under massif. Heap captures the
# large transient allocations -- notably the Classic McEliece key-gen matrix.
set -e
cd /home/anss/random/bench
gcc mem_kem.c -I install/include -L install/lib -loqs -lcrypto -o mem_kem
export LD_LIBRARY_PATH=install/lib
printf "%-26s %12s\n" "scheme (cat 1)" "peak_heap_KB"
for K in ML-KEM-512 NTRU-HPS-2048-677 HQC-128 Classic-McEliece-348864; do
  valgrind --tool=massif --massif-out-file="ms_$K.out" ./mem_kem "$K" >/dev/null 2>&1
  peak=$(grep mem_heap_B "ms_$K.out" | cut -d= -f2 | sort -n | tail -1)
  awk -v k="$K" -v p="$peak" 'BEGIN{printf "%-26s %12.1f\n", k, p/1024}'
done
