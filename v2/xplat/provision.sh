#!/usr/bin/env bash
# Temporary VMs for the cross-platform replication: AMD EPYC (Zen 4, C3D, one
# thread per core) and Google Axion (Arm Neoverse V2, C4A).
#   bash provision.sh up       create both VMs
#   bash provision.sh push     copy the source bundle (no builds) to both
#   bash provision.sh go       start vm_build.sh then vm_campaign.sh on both (detached)
#   bash provision.sh watch    last log lines from both
#   bash provision.sh fetch    copy each VM's data/ to data/xplat/<vm>/
#   bash provision.sh down     delete both VMs
#   bash provision.sh status   list anything still carrying the label
# Everything created here carries the label purpose=pqc-bench, as in wan/.
set -euo pipefail
cd "$(dirname "$0")"
declare -A ZONE=([amd]=us-central1-a [arm]=${ARM_ZONE:-us-central1-b})
VMS=(amd arm)
declare -A MT=([amd]=c3d-standard-8 [arm]=c4a-standard-4)
declare -A IMG=([amd]=ubuntu-2404-lts-amd64 [arm]=ubuntu-2404-lts-arm64)
declare -A DISK=([amd]=pd-balanced [arm]=hyperdisk-balanced)
declare -A EXTRA=([amd]="--threads-per-core=1" [arm]="")
B=/home/anss/random/bench; V2=$B/v2
SRC=$V2/xplat/bundle_src.tar.zst; OSSL=$V2/xplat/bundle_openssl.tar.zst
on() { gcloud compute ssh pqc-xplat-$1 --zone=${ZONE[$1]} --quiet --command "$2"; }

status() {
  echo "instances with label purpose=pqc-bench:"
  gcloud compute instances list --filter="labels.purpose=pqc-bench" --format="value(name,zone.basename(),status)"
}

case "${1:-status}" in
  up)
    for v in "${VMS[@]}"; do
      gcloud compute instances create pqc-xplat-$v --zone=${ZONE[$v]} --machine-type=${MT[$v]} \
        ${EXTRA[$v]} --image-family=${IMG[$v]} --image-project=ubuntu-os-cloud \
        --boot-disk-size=30GB --boot-disk-type=${DISK[$v]} --labels=purpose=pqc-bench --quiet &
    done
    wait; status ;;
  push)
    if [ ! -s $SRC ]; then  # sources only; --long dedupes the five near-identical liboqs trees
      tar -C $B --exclude=build --exclude='build-*' --exclude=.git --exclude='*.o' \
          --exclude='bundle_*.tar.zst' -cf - \
          v2/liboqs-default v2/liboqs-O3 v2/liboqs-016 v2/liboqs-016-O3 v2/liboqs-016-hqcavx2 \
          v2/src/oqs-provider-0.12.0 hqc-official v2/cpu/bench_kem.c v2/cpu/mkobjs.sh \
          v2/tls/tls_hs.c v2/tls/tls_campaign.py v2/tls/make_certs.sh v2/tls/openssl35.cnf \
          v2/netns.py v2/xplat | zstd -q -T0 --long=27 -10 -o $SRC
      git -C $B/quic/openssl-src archive --format=tar --prefix=quic/openssl-src/ HEAD \
          | zstd -q -T0 -10 -o $OSSL
    fi
    ls -la $SRC $OSSL
    for v in "${VMS[@]}"; do
      ( gcloud compute scp $SRC $OSSL pqc-xplat-$v:~/ --zone=${ZONE[$v]} --quiet &&
        on $v "sudo apt-get install -y -q zstd >/dev/null; mkdir -p ~/random/bench &&
               zstd -dc --long=27 ~/bundle_src.tar.zst | tar -C ~/random/bench -xf - &&
               zstd -dc ~/bundle_openssl.tar.zst | tar -C ~/random/bench -xf - &&
               echo \$(hostname): \$(ls ~/random/bench/v2 | tr '\n' ' ')" ) &
    done
    wait ;;
  go)
    for v in "${VMS[@]}"; do
      on $v "setsid nohup bash -c 'bash ~/random/bench/v2/xplat/vm_build.sh && bash ~/random/bench/v2/xplat/vm_campaign.sh' \
             > ~/xplat.log 2>&1 < /dev/null & echo started on \$(hostname)"
    done ;;
  watch)
    for v in "${VMS[@]}"; do echo "== $v"; on $v "tail -3 ~/xplat.log" || true; done ;;
  fetch)
    for v in "${VMS[@]}"; do
      mkdir -p $V2/data/xplat/$v
      on $v "tar -C ~/random/bench/v2 -czf ~/xplat_data.tgz data; ls -la ~/xplat_data.tgz"
      gcloud compute scp pqc-xplat-$v:~/xplat_data.tgz $V2/data/xplat/$v/ --zone=${ZONE[$v]} --quiet
      gcloud compute scp pqc-xplat-$v:~/xplat.log $V2/data/xplat/$v/ --zone=${ZONE[$v]} --quiet
      tar -C $V2/data/xplat/$v -xzf $V2/data/xplat/$v/xplat_data.tgz data
    done ;;
  down)
    for v in "${VMS[@]}"; do
      gcloud compute instances delete pqc-xplat-$v --zone=${ZONE[$v]} --quiet &
    done
    wait; status ;;
  status) status ;;
esac
