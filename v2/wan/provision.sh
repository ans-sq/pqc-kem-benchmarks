#!/usr/bin/env bash
# Temporary measurement VMs for the inter-network runs.
#   bash provision.sh up       firewall rule (this machine's IP only) + 3 VMs
#   bash provision.sh bundle   copy the server bundle to every VM
#   bash provision.sh down     delete the VMs and the firewall rule
#   bash provision.sh status   list anything still carrying the label
# Everything created here carries the label purpose=pqc-bench and the
# network tag pqc-bench, so teardown can verify nothing is left behind.
set -euo pipefail
cd "$(dirname "$0")"
FW=pqc-bench-allow
TAG=pqc-bench
MT=e2-small
declare -A ZONE=([mumbai]=asia-south1-a [frankfurt]=europe-west3-a [iowa]=us-central1-a)
V2=/home/anss/random/bench/v2

status() {
  echo "instances with label purpose=pqc-bench:"
  gcloud compute instances list --filter="labels.purpose=pqc-bench" --format="value(name,zone.basename(),status)"
  echo "firewall rules named $FW:"
  gcloud compute firewall-rules list --filter="name=$FW" --format="value(name)"
}

case "${1:-status}" in
  up)
    myip=$(curl -s https://api.ipify.org)
    echo "client public IP: $myip"
    gcloud compute firewall-rules create $FW --network=default --direction=INGRESS \
      --allow=tcp:47101,tcp:44330-44332,udp:4455-4457 --source-ranges="$myip/32" \
      --target-tags=$TAG --description="temporary PQC benchmark (delete after use)" --quiet
    for r in "${!ZONE[@]}"; do
      gcloud compute instances create pqc-bench-$r --zone=${ZONE[$r]} --machine-type=$MT \
        --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
        --boot-disk-size=10GB --tags=$TAG --labels=purpose=pqc-bench --quiet &
    done
    wait
    gcloud compute instances list --filter="labels.purpose=pqc-bench" \
      --format="table(name,zone.basename(),status,networkInterfaces[0].accessConfigs[0].natIP)" ;;
  bundle)
    B=$(mktemp -d)
    mkdir -p $B/pqc/{ossl/bin,ossl/lib,oqsprov,oqs,certs}
    O=/home/anss/random/bench/quic/openssl-install
    cp $O/bin/openssl $B/pqc/ossl/bin/
    cp -a $O/lib/libssl.so* $O/lib/libcrypto.so* $B/pqc/ossl/lib/
    cp $V2/oqsprov35-012/lib/oqsprovider.so $B/pqc/oqsprov/
    cp -a $V2/install-016-hqcavx2/lib/liboqs.so* $B/pqc/oqs/
    cp $V2/tls/certs35/single.* $V2/tls/certs35/mldsa65-* $B/pqc/certs/
    cp $V2/tls/openssl35.cnf $V2/quic/quic_srv wan_transport.py vm_servers.sh $B/pqc/
    tar -C $B -czf $B/pqc.tgz pqc
    for r in "${!ZONE[@]}"; do
      gcloud compute scp $B/pqc.tgz pqc-bench-$r:~/ --zone=${ZONE[$r]} --quiet &
    done
    wait
    for r in "${!ZONE[@]}"; do
      gcloud compute ssh pqc-bench-$r --zone=${ZONE[$r]} --quiet --command \
        "tar xzf pqc.tgz && which tcpdump python3 && nproc && grep -c avx2 /proc/cpuinfo | head -1 && grep -m1 'model name' /proc/cpuinfo" &
    done
    wait
    rm -rf $B ;;
  down)
    for r in "${!ZONE[@]}"; do
      gcloud compute instances delete pqc-bench-$r --zone=${ZONE[$r]} --quiet &
    done
    wait || true
    gcloud compute firewall-rules delete $FW --quiet || true
    status ;;
  status) status ;;
esac
