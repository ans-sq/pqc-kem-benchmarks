#!/usr/bin/env bash
# Three-level chains (root -> intermediate -> leaf) per signature algorithm
# for the certificate-chain experiment. The server sends leaf+intermediate;
# the client trusts the root. All chains are made with OpenSSL 3.5, whose
# native ML-DSA (FIPS 204) the TLS and QUIC servers then use.
set -euo pipefail
mkdir -p "$(dirname "$0")/certs35" && cd "$(dirname "$0")/certs35"
O=/home/anss/random/bench/quic/openssl-install
export LD_LIBRARY_PATH=$O/lib OPENSSL_CONF=/home/anss/random/bench/v2/tls/openssl35.cnf
openssl() { "$O/bin/openssl" "$@"; }
P=""
keygen() {  # alg outfile
  case $1 in
    ecdsa) openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out $2 ;;
    rsa2048) openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out $2 ;;
    mldsa44) openssl genpkey -algorithm ML-DSA-44 -out $2 ;;
    mldsa65) openssl genpkey -algorithm ML-DSA-65 -out $2 ;;
    mldsa87) openssl genpkey -algorithm ML-DSA-87 -out $2 ;;
  esac
}
for A in ecdsa rsa2048 mldsa44 mldsa65 mldsa87; do
  keygen $A $A-root.key; keygen $A $A-int.key; keygen $A $A-leaf.key
  openssl req $P -x509 -new -key $A-root.key -subj "/CN=bench root $A" -days 3650 \
      -addext basicConstraints=critical,CA:TRUE -out $A-root.pem
  openssl req $P -new -key $A-int.key -subj "/CN=bench intermediate $A" -out $A-int.csr
  openssl x509 $P -req -in $A-int.csr -CA $A-root.pem -CAkey $A-root.key -CAcreateserial \
      -days 3650 -extfile <(printf "basicConstraints=critical,CA:TRUE\n") -out $A-int.pem
  openssl req $P -new -key $A-leaf.key -subj "/CN=pqc-bench" -out $A-leaf.csr
  openssl x509 $P -req -in $A-leaf.csr -CA $A-int.pem -CAkey $A-int.key -CAcreateserial \
      -days 3650 -extfile <(printf "subjectAltName=DNS:pqc-bench\n") -out $A-leaf.pem
  openssl verify $P -CAfile $A-root.pem -untrusted $A-int.pem $A-leaf.pem
  cat $A-leaf.pem $A-int.pem > $A-chain.pem
  printf "%s: leaf DER %s B, intermediate DER %s B\n" $A \
    $(openssl x509 $P -in $A-leaf.pem -outform DER | wc -c) $(openssl x509 $P -in $A-int.pem -outform DER | wc -c)
done
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout single.key \
    -out single.pem -subj "/CN=bench" -days 3650 -addext basicConstraints=critical,CA:TRUE \
    -addext subjectAltName=DNS:pqc-bench
