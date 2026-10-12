#!/usr/bin/env bash
# Copy the revision's harnesses, patches, raw data, and analysis outputs into
# the artifact repository (pqc-kem-benchmarks/v2). Local copy only: nothing is
# committed or pushed. Library source trees, builds, binaries, and the test
# certificates' private keys are excluded (make_certs.sh regenerates them).
set -euo pipefail
cd "$(dirname "$0")"
DST=/home/anss/random/pqc-kem-benchmarks/v2
mkdir -p "$DST"
rsync -a --delete --exclude='__pycache__' \
  --include='/analysis/***' --include='/patches/***' \
  --include='/cpu/' --include='/cpu/*.c' --include='/cpu/*.sh' \
  --include='/tls/' --include='/tls/*.c' --include='/tls/*.py' --include='/tls/*.sh' --include='/tls/*.cnf' \
  --include='/quic/' --include='/quic/*.c' --include='/quic/*.py' \
  --include='/transport/' --include='/transport/*.py' \
  --include='/mem/' --include='/mem/*.c' --include='/mem/*.sh' --include='/mem/ms_*.out' \
  --include='/wan/' --include='/wan/*.sh' --include='/wan/*.py' \
  --include='/xplat/' --include='/xplat/*.sh' \
  --include='/data/' --include='/data/*.csv' --include='/data/*.txt' --include='/data/*.log' \
  --include='/data/analysis/***' --include='/data/pcapsum/***' \
  --exclude='/data/xplat/*/xplat_data.tgz' --exclude='/data/xplat/*/data/pcap/' --include='/data/xplat/***' \
  --include='/data/wan/' --include='/data/wan/*.csv' \
  --include='/*.sh' --include='/*.py' --include='/ARTIFACT_README.md' \
  --exclude='*' \
  ./ "$DST/"
# packet traces, compressed (xz -9 keeps every file well under 100 MB)
mkdir -p "$DST/data/pcap" "$DST/data/wan"
for f in data/pcap/*.pcap data/wan/*.pcap; do
  out="$DST/${f}.xz"
  [ "$out" -nt "$f" ] || xz -9 -T4 -c "$f" > "$out"
done
mv "$DST/ARTIFACT_README.md" "$DST/README.md"
du -sh "$DST"
