#!/usr/bin/env bash
# Cross-platform replication, step 1 (runs on the VM): build everything with
# the laptop's compiler (gcc-11) and options. x86-64: all builds of the CPU
# campaign. aarch64: no official AVX2 HQC (none exists) and no Classic
# McEliece -O3 variant (liboqs's -O1 setting applies only to its AVX2 code,
# so on ARM the released build already is the -O3 build).
set -euo pipefail
B=/home/anss/random/bench; V2=$B/v2; J=$(nproc); ARCH=$(uname -m)
log() { echo "$(date +%T) $*"; }

log "packages ($ARCH, $J CPUs)"
sudo apt-get update -q >/dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q gcc-11 g++-11 cmake ninja-build libssl-dev \
  python3-numpy git perl make zstd iproute2 ethtool tcpdump >/dev/null
if ! sudo modprobe sch_netem 2>/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q "linux-modules-extra-$(uname -r)" >/dev/null || true
  sudo modprobe sch_netem || true
fi
lsmod | grep -q sch_netem && log "netem available" || log "WARNING: netem unavailable"
# `unshare -r -n` needs unprivileged user namespaces, which Ubuntu 24.04 restricts
sudo sysctl -q kernel.apparmor_restrict_unprivileged_userns=0 || true

log "OpenSSL 3.5 (23b0396)"
if [ ! -x $B/quic/openssl-install/bin/openssl ]; then
  cd $B/quic/openssl-src
  ./Configure --prefix=$B/quic/openssl-install --libdir=lib shared > ../ossl.cfg.log 2>&1
  make -j$J > ../ossl.build.log 2>&1
  make install_sw >> ../ossl.build.log 2>&1
fi

log "official HQC (161cd4f)"
cd $B/hqc-official
ARCHS="ref"; [ "$ARCH" = x86_64 ] && ARCHS="ref x86_64"
# the reference code includes <immintrin.h> in three headers without using it, which
# fails on non-x86 hosts; drop those includes there (patches/hqc-official-161cd4f-aarch64-unused-immintrin.patch)
[ "$ARCH" = x86_64 ] || sed -i '/#include <immintrin.h>/d' src/ref/hqc.h src/ref/vector.h src/ref/parsing.h
for A in $ARCHS; do
  X86=""; [ $A = x86_64 ] && X86="-DHQC_X86_IMPL=avx256"  # as in the laptop build
  cmake -S . -B build-pic-$A -G Ninja -DCMAKE_C_COMPILER=gcc-11 -DCMAKE_CXX_COMPILER=g++-11 \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DHQC_ARCH=$A $X86 \
        > cfg-$A.log 2>&1
  # only the libraries mkobjs.sh links (the official benchmark program is x86 assembly)
  cmake --build build-pic-$A -j$J --target hqc_1_$A hqc_3_$A hqc_5_$A fips202 > build-$A.log 2>&1
done
bash $V2/cpu/mkobjs.sh

log "liboqs builds"
cd $V2
VARS="default O3 016"; [ "$ARCH" = x86_64 ] && VARS="$VARS 016-O3 016-hqcavx2"
for V in $VARS; do
  HQC=""; case $V in default|O3) HQC="-DOQS_ENABLE_KEM_HQC=ON" ;; esac  # off by default in 0.15
  cmake -S liboqs-$V -B liboqs-$V/build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DOQS_DIST_BUILD=ON \
        -DOQS_USE_OPENSSL=ON $HQC -DOQS_BUILD_ONLY_LIB=ON \
        -DCMAKE_INSTALL_PREFIX=$V2/install-$V > liboqs-$V.cfg.log 2>&1
  cmake --build liboqs-$V/build -j$J > liboqs-$V.build.log 2>&1
  cmake --install liboqs-$V/build >> liboqs-$V.build.log 2>&1
  log "  liboqs-$V"
done

log "oqs-provider 0.12.0 and harnesses"
O=$B/quic/openssl-install
cmake -S src/oqs-provider-0.12.0 -B oqsprov35-012-build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
      -DCMAKE_BUILD_TYPE=Release -DOPENSSL_ROOT_DIR=$O \
      -Dliboqs_DIR=$V2/install-016/lib/cmake/liboqs > oqsprov35-012.cfg.log 2>&1
cmake --build oqsprov35-012-build -j$J > oqsprov35-012.build.log 2>&1
mkdir -p oqsprov35-012/lib && cp oqsprov35-012-build/lib/oqsprovider.so oqsprov35-012/lib/
cd cpu
X=""; [ "$ARCH" = x86_64 ] || X="-DNO_OFFICIAL_AVX2"
gcc-11 -O2 -std=gnu11 -Wall $X -o bench_kem016 bench_kem.c obj/*.o -I../install-016/include \
       -L../install-016/lib -loqs -lcrypto -Wl,-rpath,$V2/install-016/lib -lm
gcc-11 -O2 -std=gnu11 -Wall $X -o bench_kem bench_kem.c obj/*.o -I../install-default/include \
       -L../install-default/lib -loqs -lcrypto -Wl,-rpath,$V2/install-default/lib -lm
cd ../tls
gcc-11 -O2 -o tls_hs tls_hs.c -I$O/include -L$O/lib -lssl -lcrypto -Wl,-rpath,$O/lib
bash make_certs.sh > certs.log 2>&1
log "BUILD DONE"
