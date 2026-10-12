#!/usr/bin/env bash
# Regenerate every summary used in the manuscript from the raw data.
#   bash analysis/analyze_all.sh            (from bench/v2)
set -u
cd "$(dirname "$0")/.."
D=data; A=$D/analysis; P=$D/pcapsum
mkdir -p $A $P
PY=python3
MPL=~/.pyenv/versions/3.12.12/bin/python3   # interpreter with matplotlib (figures)
run() { taskset -c 4-11 "$@"; }

run $PY -I analysis/cpu_analysis.py $D > $A/cpu.txt
run $PY -I analysis/mcdm_v2.py $D > $A/mcdm_v2.txt
run $PY -I analysis/mcdm_static.py $D > $A/mcdm_static.txt

# packet traces -> per-connection summaries
declare -A RTT=([rtt10]=10 [rtt50]=50 [rtt100]=100 [rtt50_loss1]=50 [rtt50_retry]=50 [chain_rtt50]=50
                [bw10_bulk_rtt50]=50 [bw1_rtt100]=100 [resume_rtt50]=50 [prov_rtt10]=10 [prov_rtt50]=50)
for f in $D/pcap/quic_*.pcap; do
  [ -e "$f" ] || continue
  t=$(basename $f .pcap); t=${t#quic_}
  run $PY -I pcap_flights.py quic $f 4455 ${RTT[$t]:-50} > $P/quicpcap_$t.csv
done
for f in $D/pcap/tls_*.pcap; do
  [ -e "$f" ] || continue
  t=$(basename $f .pcap); t=${t#tls_}
  run $PY -I pcap_flights.py tcp $f 44330 ${RTT[$t]:-50} > $P/tlspcap_$t.csv
done
for f in $D/pcap/transport_*.pcap; do
  [ -e "$f" ] || continue
  t=$(basename $f .pcap); t=${t#transport_}
  run $PY -I pcap_flights.py tcp $f 47101 ${RTT[$t]:-50} > $P/tcppcap_transport_$t.csv
done

# protocol summaries
for f in tls_main tls_resume tls_chain tls_provider; do
  [ -s $D/$f.csv ] && run $PY -I analysis/net_stats.py tls $D/$f.csv > $A/$f.csv
done
for f in quic_main quic_chain; do
  [ -s $D/$f.csv ] && run $PY -I analysis/net_stats.py quic $D/$f.csv x25519 $P > $A/${f}_stats.csv
done
for c in latency loss congestion; do  # trials joined to their traces in execution order
  [ -s $D/transport_$c.csv ] && \
    run $PY -I analysis/transport_stats.py --pcap $P $D/transport_$c.csv > $A/transport_${c}_stats.csv
done
[ -s $A/transport_congestion_stats.csv ] && \
  run $PY -I analysis/transport_table.py $A/transport_latency_stats.csv $A/transport_loss_stats.csv \
      $A/transport_congestion_stats.csv > $A/transport_table.tex

# inter-network
for r in frankfurt iowa mumbai; do
  [ -s $D/wan/transport_$r.csv ] && run $PY -I analysis/transport_stats.py $D/wan/transport_$r.csv > $A/wan_transport_$r.csv
  if [ -s $D/wan/wan_$r.pcap ]; then  # server-side traces: Frankfurt and Iowa (Mumbai capture failed)
    for port in 4455 4456 4457; do
      run $PY -I pcap_flights.py quic $D/wan/wan_$r.pcap $port 150 > $P/wanquic_${r}_$port.csv
    done
  fi
done
run $MPL analysis/make_figures_v2.py $D /home/anss/random/paper_v2/figures

run $PY -I analysis/wan_stats.py $D > $A/wan_protocols.csv
# cross-platform replication (data/xplat/{amd,arm}/data, from xplat/provision.sh fetch)
[ -d $D/xplat ] && run $PY -I analysis/xplat_analysis.py $D > $A/xplat.txt
echo "analysis written to $A"
