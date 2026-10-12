// QUIC v1 handshake timer (OpenSSL 3.5 client API). For each trial: a fresh
// UDP socket and QUIC connection restricted to one key-exchange group, timed
// with CLOCK_MONOTONIC_RAW from just before SSL_connect() to its return
// (handshake complete), then one short echo on a stream (not timed) and a
// clean shutdown. Packet and byte counts per direction come from the packet
// trace (quic_pcap.py), keyed by the client port printed here.
//
// Usage: quic_hs host port group ntrials cafile [oqs]
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <netinet/in.h>
#include <openssl/err.h>
#include <openssl/provider.h>
#include <openssl/quic.h>
#include <openssl/ssl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static double now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3;
}

int main(int argc, char **argv) {
    if (argc < 6) {
        fprintf(stderr, "usage: %s host port group ntrials cafile [oqs]\n", argv[0]);
        return 1;
    }
    const char *host = argv[1], *group = argv[3], *ca = argv[5];
    int port = atoi(argv[2]), n = atoi(argv[4]);
    if (argc > 6 && !strcmp(argv[6], "oqs")) {
        if (!OSSL_PROVIDER_load(NULL, "oqsprovider") || !OSSL_PROVIDER_load(NULL, "default")) {
            ERR_print_errors_fp(stderr);
            return 1;
        }
    }
    SSL_CTX *ctx = SSL_CTX_new(OSSL_QUIC_client_method());
    if (!ctx || !SSL_CTX_set1_groups_list(ctx, group) ||
        !SSL_CTX_load_verify_locations(ctx, ca, NULL)) {
        ERR_print_errors_fp(stderr);
        return 1;
    }
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
    static const unsigned char alpn[] = {8, 'o', 's', 's', 'l', 't', 'e', 's', 't'};
    struct sockaddr_in peer = {.sin_family = AF_INET, .sin_port = htons(port)};
    inet_pton(AF_INET, host, &peer.sin_addr);
    BIO_ADDR *pa = BIO_ADDR_new();
    BIO_ADDR_rawmake(pa, AF_INET, &peer.sin_addr, sizeof peer.sin_addr, htons(port));

    printf("group,trial,hs_us,client_port,negotiated\n");
    for (int t = 0; t < n; t++) {
        int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (connect(fd, (struct sockaddr *)&peer, sizeof peer)) { perror("connect"); return 2; }
        struct sockaddr_in me;
        socklen_t ml = sizeof me;
        getsockname(fd, (struct sockaddr *)&me, &ml);
        SSL *s = SSL_new(ctx);
        SSL_set_fd(s, fd);
        SSL_set1_initial_peer_addr(s, pa);
        SSL_set_alpn_protos(s, alpn, sizeof alpn);
        SSL_set_tlsext_host_name(s, "pqc-bench");
        double t0 = now_us();
        if (SSL_connect(s) != 1) {
            fprintf(stderr, "QUIC handshake failed trial %d\n", t);
            ERR_print_errors_fp(stderr);
            return 3;
        }
        double t1 = now_us();
        size_t w, r;
        char buf[64];
        SSL_write_ex2(s, "ping\n", 5, SSL_WRITE_FLAG_CONCLUDE, &w);
        while (SSL_read_ex(s, buf, sizeof buf, &r) > 0) continue;
        const char *neg = SSL_group_to_name(s, SSL_get_negotiated_group(s));
        printf("%s,%d,%.1f,%d,%s\n", group, t, t1 - t0, ntohs(me.sin_port), neg ? neg : "?");
        fflush(stdout);
        while (SSL_shutdown(s) != 1) continue;
        SSL_free(s);
        close(fd);
    }
    BIO_ADDR_free(pa);
    SSL_CTX_free(ctx);
    return 0;
}
