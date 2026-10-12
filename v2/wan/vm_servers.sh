#!/usr/bin/env bash
# Runs on each measurement VM, in the foreground of an ssh session (the VM
# ends background jobs at logout, so the session's lifetime bounds the run).
# Starts every server the WAN runner needs plus a header-only packet capture,
# and stops them all when the session ends.
#   transport  tcp 47101   python framed echo (wan_transport.py)
#   TLS        tcp 44330   OpenSSL 3.5 s_server, native groups, ECDSA cert
#              tcp 44331   s_server with oqs-provider, HQC groups (official AVX2)
#              tcp 44332   s_server, native groups, ML-DSA-65 chain
#   QUIC       udp 4455    quic_srv native groups, ECDSA cert
#              udp 4456    quic_srv with oqs-provider, HQC groups
#              udp 4457    quic_srv native groups, ML-DSA-65 chain
set -u
P=$HOME/pqc
export LD_LIBRARY_PATH=$P/ossl/lib:$P/oqs OPENSSL_MODULES=$P/oqsprov OPENSSL_CONF=$P/openssl35.cnf
NATIVE="x25519:X25519MLKEM768:MLKEM512:MLKEM768:MLKEM1024"
HQC="hqc1:hqc3:hqc5"
C=$P/certs
pids=()
sudo tcpdump -i any -s 128 -U -w /tmp/wan.pcap \
  'tcp port 47101 or tcp portrange 44330-44332 or udp portrange 4455-4457' >/dev/null 2>&1 &
pids+=($!)
python3 -I $P/wan_transport.py server 47101 & pids+=($!)
$P/ossl/bin/openssl s_server -tls1_3 -groups $NATIVE -cert $C/single.pem -key $C/single.key \
  -accept 44330 -rev -quiet </dev/null >/dev/null 2>&1 & pids+=($!)
$P/ossl/bin/openssl s_server -provider oqsprovider -provider default -tls1_3 -groups $HQC \
  -cert $C/single.pem -key $C/single.key -accept 44331 -rev -quiet </dev/null >/dev/null 2>&1 & pids+=($!)
$P/ossl/bin/openssl s_server -tls1_3 -groups $NATIVE -cert $C/mldsa65-leaf.pem \
  -key $C/mldsa65-leaf.key -cert_chain $C/mldsa65-int.pem -accept 44332 -rev -quiet \
  </dev/null >/dev/null 2>&1 & pids+=($!)
$P/quic_srv 4455 $C/single.pem $C/single.key $NATIVE 1000000 - & pids+=($!)
$P/quic_srv 4456 $C/single.pem $C/single.key $HQC 1000000 oqs & pids+=($!)
$P/quic_srv 4457 $C/mldsa65-chain.pem $C/mldsa65-leaf.key $NATIVE 1000000 - & pids+=($!)
trap 'kill ${pids[@]} 2>/dev/null; sudo pkill tcpdump; exit 0' INT TERM HUP EXIT
echo "SERVERS UP"
# hold until the controlling ssh session closes stdin
cat >/dev/null
