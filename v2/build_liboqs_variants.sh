#!/usr/bin/env bash
# Build the two liboqs 0.15.0 variants used in the revision, with the same
# compiler (gcc-11) and options as the original build (Release, dist build,
# OpenSSL-backed SHA-3/AES), differing only in the patched HQC/McEliece parts.
set -euo pipefail
cd "$(dirname "$0")"
for V in O3 hqcavx2; do
  cmake -S liboqs-$V -B liboqs-$V/build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DOQS_DIST_BUILD=ON \
        -DOQS_USE_OPENSSL=ON -DOQS_ENABLE_KEM_HQC=ON -DOQS_BUILD_ONLY_LIB=ON \
        -DCMAKE_INSTALL_PREFIX=$PWD/install-$V > liboqs-$V.cfg.log 2>&1
  cmake --build liboqs-$V/build -j10 > liboqs-$V.build.log 2>&1
  cmake --install liboqs-$V/build >> liboqs-$V.build.log 2>&1
  echo "$V built: $(ls install-$V/lib/liboqs.so*)"
done
