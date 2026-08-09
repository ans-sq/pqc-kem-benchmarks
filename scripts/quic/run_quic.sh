#!/usr/bin/env bash
# PQC-over-QUIC handshake demonstration (reviewer item #7): OpenSSL 3.5's QUIC
# (the demo QUIC server + `s_client -quic`) with oqs-provider PQC groups, over
# loopback. Confirms a post-quantum key exchange completes a real QUIC/TLS-1.3
# handshake; per-group it reports success and the negotiated group.
set -u
Q=/home/anss/random/bench/quic
OSSL=$Q/openssl-install/bin/openssl
SRV=$Q/openssl-src/demos/quic/server/server
CERT=$Q/openssl-src/test/certs/servercert.pem
KEY=$Q/openssl-src/test/certs/serverkey.pem
PROVDIR=$(dirname "$(find "$Q/oqsprov-build" -name oqsprovider.so | head -1)")
export LD_LIBRARY_PATH="$Q/openssl-install/lib"
export OPENSSL_MODULES="$PROVDIR"
export OPENSSL_CONF="$Q/oqs.cnf"
PORT=4455

printf "%-18s %-7s %s\n" "group" "result" "negotiated"
for G in x25519 X25519MLKEM768 mlkem768 hqc128; do
  "$SRV" "$PORT" "$CERT" "$KEY" >/dev/null 2>&1 &
  SP=$!
  python3 -c "import time;time.sleep(0.6)"
  out=$(printf 'GET /\r\n\r\n' | "$OSSL" s_client -quic -alpn ossltest -groups "$G" \
        -connect 127.0.0.1:$PORT 2>&1)
  kill "$SP" 2>/dev/null; wait "$SP" 2>/dev/null
  neg=$(printf '%s' "$out" | grep -iE "Negotiated TLS1.3 group|Server Temp Key" | head -1 | sed 's/^ *//')
  if printf '%s' "$out" | grep -qiE "Cipher is|Protocol *: *TLSv1.3|SSL handshake has read"; then
    res=OK; else res=FAIL; fi
  printf "%-18s %-7s %s\n" "$G" "$res" "${neg:-?}"
done
