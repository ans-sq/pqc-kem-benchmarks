#!/usr/bin/env bash
# Queued after run_all_local.sh: provider-path TLS control and the X25519
# reference timing at the controlled clock (P-core 2).
set -u
cd "$(dirname "$0")"
D=data
until grep -q "ALL LOCAL DONE" $D/campaign.log; do sleep 20; done
echo "$(date +%T) tls provider control" >> $D/campaign.log
unshare -r -n python3 -I tls/tls_campaign.py provider > $D/tls_provider.csv 2>> $D/campaign.log
O=/home/anss/random/bench/quic/openssl-install
OPENSSL_CONF=tls/openssl35.cnf LD_LIBRARY_PATH=$O/lib taskset -c 2 $O/bin/openssl speed -seconds 5 x25519 ecdhp256 > $D/openssl_speed_x25519.txt 2>&1
echo "$(date +%T) FOLLOWUP DONE" >> $D/campaign.log
