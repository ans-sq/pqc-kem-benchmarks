#!/usr/bin/env bash
# All loopback campaigns of the revision, in sequence, under the controls of
# cpu/controls.sh (fixed 1.7 GHz clock, turbo off, P-cores out of C2/C3).
# The CPU micro-benchmarks run first and alone; the network campaigns follow.
set -uo pipefail
cd "$(dirname "$0")"
D=data
mkdir -p $D
bash cpu/controls.sh show > $D/controls_state.txt 2>&1
grep -q "no_turbo=1" $D/controls_state.txt || { echo "controls are not on"; exit 1; }
log() { echo "$(date +%T) $*" | tee -a $D/campaign.log; }
log "cpu+energy start";   cpu/cpu_campaign.sh >> $D/campaign.log 2>&1
log "tls main";           unshare -r -n python3 -I tls/tls_campaign.py main   > $D/tls_main.csv   2>> $D/campaign.log
log "tls resume";         unshare -r -n python3 -I tls/tls_campaign.py resume > $D/tls_resume.csv 2>> $D/campaign.log
log "tls chain";          unshare -r -n python3 -I tls/tls_campaign.py chain  > $D/tls_chain.csv  2>> $D/campaign.log
log "quic main";          unshare -r -n python3 -I quic/quic_campaign.py main  > $D/quic_main.csv  2>> $D/campaign.log
log "quic chain";         unshare -r -n python3 -I quic/quic_campaign.py chain > $D/quic_chain.csv 2>> $D/campaign.log
log "transport latency";  unshare -r -n python3 -I transport/transport_v2.py latency    > $D/transport_latency.csv    2>> $D/campaign.log
log "transport loss";     unshare -r -n python3 -I transport/transport_v2.py loss       > $D/transport_loss.csv       2>> $D/campaign.log
log "transport congestion"; unshare -r -n python3 -I transport/transport_v2.py congestion > $D/transport_congestion.csv 2>> $D/campaign.log
log "ALL LOCAL DONE"
