#!/usr/bin/env bash
# liboqs 0.16.0 (commit 5a1a854) in three builds with gcc-11 and the original
# options: unmodified ("016"), Classic McEliece AVX2 at -O3 instead of -O1
# ("016-O3", CPU runs only), and HQC wired to the official AVX2 code
# ("016-hqcavx2"). Then oqs-provider 0.12.0 (commit 7e9d095) for OpenSSL 3.5.
set -euo pipefail
cd "$(dirname "$0")"
for V in 016 016-O3 016-hqcavx2; do
  cmake -S liboqs-$V -B liboqs-$V/build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DOQS_DIST_BUILD=ON \
        -DOQS_USE_OPENSSL=ON -DOQS_BUILD_ONLY_LIB=ON \
        -DCMAKE_INSTALL_PREFIX=$PWD/install-$V > liboqs-$V.cfg.log 2>&1
  cmake --build liboqs-$V/build -j10 > liboqs-$V.build.log 2>&1
  cmake --install liboqs-$V/build >> liboqs-$V.build.log 2>&1
  echo "$V: $(ls install-$V/lib/ | tr '\n' ' ')"
done
O=/home/anss/random/bench/quic/openssl-install
cmake -S src/oqs-provider-0.12.0 -B oqsprov35-012-build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
      -DCMAKE_BUILD_TYPE=Release -DOPENSSL_ROOT_DIR=$O \
      -Dliboqs_DIR=$PWD/install-016/lib/cmake/liboqs > oqsprov35-012.cfg.log 2>&1
cmake --build oqsprov35-012-build -j10 > oqsprov35-012.build.log 2>&1
mkdir -p oqsprov35-012/lib && cp oqsprov35-012-build/lib/oqsprovider.so oqsprov35-012/lib/
echo "provider 0.12.0 built"
