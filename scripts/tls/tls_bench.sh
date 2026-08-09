#!/bin/bash
# TLS 1.3 handshake benchmark under emulated RTT.
# Run inside an unprivileged user+network namespace:
#   unshare -r -n bash tls_bench.sh
#
# For each (RTT, group): starts openssl s_server on loopback (MTU 1500,
# netem delay), runs N s_client handshakes, records wall time and the
# handshake byte counts that s_client itself reports.
# Output CSV: group,rtt_ms,trial,seconds,read_bytes,written_bytes
set -u
BENCH=/home/anss/random/bench
export OPENSSL_MODULES=$BENCH/oqs-provider/build/lib
export LD_LIBRARY_PATH=$BENCH/install/lib
PROV="-provider oqsprovider -provider default"
GROUPS_LIST="x25519 X25519MLKEM768 mlkem512 mlkem768 mlkem1024 hqc128 hqc192 hqc256"
RTTS="10 50 100"
TRIALS=20
PORT=44330

# generate a throwaway ECDSA P-256 server certificate on first run; no
# key material is (or should be) committed to the artifact repository
if [ ! -f "$BENCH/tls_cert.pem" ]; then
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
        -keyout "$BENCH/tls_key.pem" -out "$BENCH/tls_cert.pem" \
        -subj "/CN=pqc-bench" -days 30 2>/dev/null
fi

ip link set lo up
ip link set lo mtu 1500

echo "group,rtt_ms,trial,seconds,read_bytes,written_bytes"
for rtt in $RTTS; do
    tc qdisc del dev lo root 2>/dev/null
    half=$(python3 -c "print($rtt/2)")
    tc qdisc add dev lo root netem delay ${half}ms
    for grp in $GROUPS_LIST; do
        openssl s_server $PROV -tls1_3 -groups $grp \
            -cert $BENCH/tls_cert.pem -key $BENCH/tls_key.pem \
            -accept $PORT -quiet -naccept $TRIALS 2>/dev/null &
        SRV=$!
        sleep 0.5
        for t in $(seq 1 $TRIALS); do
            out=$( { /usr/bin/time -f "WALL %e" \
                openssl s_client $PROV -tls1_3 -groups $grp \
                    -connect 127.0.0.1:$PORT < /dev/null 2>&1; } )
            secs=$(echo "$out" | grep -oE "WALL [0-9.]+" | cut -d' ' -f2)
            rb=$(echo "$out" | grep -oE "read [0-9]+ bytes" | grep -oE "[0-9]+")
            wb=$(echo "$out" | grep -oE "written [0-9]+ bytes" | grep -oE "[0-9]+")
            echo "$grp,$rtt,$t,${secs:-NA},${rb:-NA},${wb:-NA}"
        done
        kill $SRV 2>/dev/null
        wait $SRV 2>/dev/null
        sleep 0.3
    done
done
tc qdisc del dev lo root 2>/dev/null
