#!/usr/bin/env bash
# Unmodified liboqs 0.15.0 (commit f986aea) rebuilt with the same gcc-11 as the
# variants, then oqs-provider (commit 8b87173) rebuilt against it and the
# system OpenSSL 3.0.13. HQC is enabled at build time (it is off by default).
set -euo pipefail
cd "$(dirname "$0")"
cmake -S liboqs-default -B liboqs-default/build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
      -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DOQS_DIST_BUILD=ON \
      -DOQS_USE_OPENSSL=ON -DOQS_ENABLE_KEM_HQC=ON -DOQS_BUILD_ONLY_LIB=ON \
      -DCMAKE_INSTALL_PREFIX=$PWD/install-default > liboqs-default.cfg.log 2>&1
cmake --build liboqs-default/build -j10 > liboqs-default.build.log 2>&1
cmake --install liboqs-default/build >> liboqs-default.build.log 2>&1
cmake -S ../oqs-provider -B oqsprov-build -G Ninja -DCMAKE_C_COMPILER=gcc-11 \
      -DCMAKE_BUILD_TYPE=Release -Dliboqs_DIR=$PWD/install-default/lib/cmake/liboqs \
      > oqsprov.cfg.log 2>&1
cmake --build oqsprov-build -j10 > oqsprov.build.log 2>&1
mkdir -p oqsprov/lib && cp oqsprov-build/lib/oqsprovider.so oqsprov/lib/
echo "default+provider built"; ldd oqsprov/lib/oqsprovider.so | grep -E "oqs|crypto"
