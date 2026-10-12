#!/usr/bin/env bash
# Build one namespaced, self-contained relocatable object per official HQC
# variant (2025 spec, commit 161cd4f): hqc{1,3,5}_{ref,avx2}. LTO is applied
# at this incremental link (the official AVX2 build uses -flto), then every
# symbol except the KEM API and prng_init is localized and the survivors are
# prefixed, so all six variants and liboqs can coexist in one binary.
set -euo pipefail
H=/home/anss/random/bench/hqc-official
OUT=$(dirname "$0")/obj
mkdir -p "$OUT"
IMPLS="ref avx2"; XFLAGS="-mavx2 -mbmi -mpclmul"
if [ "$(uname -m)" != x86_64 ]; then IMPLS=ref; XFLAGS=""; fi  # ARM: official ref code only
for impl in $IMPLS; do
  if [ $impl = ref ]; then B=$H/build-pic-ref; A=ref; else B=$H/build-pic-x86_64; A=x86_64; fi
  for L in 1 3 5; do
    o=$OUT/hqc${L}_${impl}.o
    gcc-11 -O3 -fPIC -flto $XFLAGS -r -nostdlib -flinker-output=nolto-rel -o $o.tmp \
        -Wl,--whole-archive $B/src/libhqc_${L}_${A}.a $B/lib/libfips202.a -Wl,--no-whole-archive
    p=hqc${L}_${impl}_
    objcopy --keep-global-symbol=crypto_kem_keypair --keep-global-symbol=crypto_kem_enc \
            --keep-global-symbol=crypto_kem_dec --keep-global-symbol=prng_init $o.tmp $o.loc
    objcopy --redefine-sym crypto_kem_keypair=${p}crypto_kem_keypair \
            --redefine-sym crypto_kem_enc=${p}crypto_kem_enc \
            --redefine-sym crypto_kem_dec=${p}crypto_kem_dec \
            --redefine-sym prng_init=${p}prng_init $o.loc $o
    rm $o.tmp $o.loc
    echo "$o: $(nm $o | grep -c ' T ') global text syms"
  done
done
