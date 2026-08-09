#!/usr/bin/env bash
# Build OpenSSL 3.5 (which ships the QUIC client+server API) from source into a
# local prefix, so we can run a real PQC-over-QUIC / HTTP-3 handshake for
# reviewer item #7. The system OpenSSL is 3.0.2 and has NO QUIC API; this build
# is fully self-contained and does NOT touch the system install.
set -euo pipefail
ROOT=/home/anss/random/bench/quic
PREFIX="$ROOT/openssl-install"
mkdir -p "$ROOT"
cd "$ROOT"

echo "[1/4] cloning openssl 3.5 ..."
rm -rf openssl-src
git clone --depth 1 --branch openssl-3.5 https://github.com/openssl/openssl openssl-src

echo "[2/4] configuring (prefix=$PREFIX) ..."
cd openssl-src
./Configure --prefix="$PREFIX" --libdir=lib shared

echo "[3/4] building with $(nproc) cores ..."
make -j"$(nproc)"

echo "[4/4] installing software (no docs) ..."
make install_sw

echo "DONE: $("$PREFIX/bin/openssl" version)"
