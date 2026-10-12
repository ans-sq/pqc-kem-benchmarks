#!/usr/bin/env bash
# WAN campaign for all three regions, one after another (10 interleaved
# rounds each). Started once the loopback CPU micro-benchmarks are finished.
set -u
cd "$(dirname "$0")"
for r in frankfurt iowa mumbai; do
  echo "$(date +%T) WAN $r start" >> ../data/campaign.log
  python3 -I run_wan.py $r 10 2>> ../data/wan_campaign.log
  echo "$(date +%T) WAN $r done" >> ../data/campaign.log
done
echo "$(date +%T) ALL WAN DONE" >> ../data/campaign.log
