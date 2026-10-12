// In-process TLS 1.3 handshake timer (revision of the 10-ms-resolution
// s_client/time measurement). For each trial: fresh TCP connection, one
// TLS 1.3 handshake restricted to a single key-exchange group, timed with
// CLOCK_MONOTONIC_RAW from just before connect() to SSL_connect() returning
// (client Finished sent), so process start-up is excluded. Per-connection
// TCP counters (bytes, segments, retransmissions) come from TCP_INFO.
//
// Modes: "full" (every trial a full handshake) or "resume" (a priming full
// handshake stores the session; each trial then resumes it with PSK-DHE, so
// the group's key exchange still runs, but certificates are not sent).
//
// Built against OpenSSL 3.5 (native ML-KEM, X25519MLKEM768, ML-DSA); HQC
// groups additionally load oqs-provider (pass "oqs" as the 7th argument).
//
// Usage: tls_hs host port group ntrials mode cafile [oqs] > csv
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <netinet/in.h>
#include <linux/tcp.h>
#include <openssl/err.h>
#include <openssl/provider.h>
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

static SSL_SESSION *saved;
static int new_session_cb(SSL *s, SSL_SESSION *sess) {
    (void)s;
    if (saved) SSL_SESSION_free(saved);
    saved = sess;  // keep the reference
    return 1;
}

static int tcp_connect(const char *host, int port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(port)};
    inet_pton(AF_INET, host, &a.sin_addr);
    if (connect(fd, (struct sockaddr *)&a, sizeof a)) { perror("connect"); exit(2); }
    return fd;
}

int main(int argc, char **argv) {
    if (argc < 7) {
        fprintf(stderr, "usage: %s host port group ntrials full|resume cafile\n", argv[0]);
        return 1;
    }
    const char *host = argv[1], *group = argv[3], *mode = argv[5], *ca = argv[6];
    int port = atoi(argv[2]), n = atoi(argv[4]);
    int resume = !strcmp(mode, "resume");
    if (argc > 7 && !strcmp(argv[7], "oqs") &&
        (!OSSL_PROVIDER_load(NULL, "oqsprovider") || !OSSL_PROVIDER_load(NULL, "default"))) {
        ERR_print_errors_fp(stderr);
        return 1;
    }
    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);
    SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION);
    if (!SSL_CTX_set1_groups_list(ctx, group)) { ERR_print_errors_fp(stderr); return 1; }
    if (!SSL_CTX_load_verify_locations(ctx, ca, NULL)) { ERR_print_errors_fp(stderr); return 1; }
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
    SSL_CTX_set_session_cache_mode(ctx, SSL_SESS_CACHE_CLIENT | SSL_SESS_CACHE_NO_INTERNAL_STORE);
    SSL_CTX_sess_set_new_cb(ctx, new_session_cb);

    printf("group,mode,trial,hs_us,tcp_us,bytes_acked,bytes_received,segs_out,segs_in,"
           "data_segs_out,data_segs_in,total_retrans,hs_bytes_sent,hs_bytes_received,hs_segs_in,"
           "hs_retrans,reused,negotiated\n");
    for (int t = resume ? -1 : 0; t < n; t++) {
        double t0 = now_us();
        int fd = tcp_connect(host, port);
        double t1 = now_us();
        SSL *ssl = SSL_new(ctx);
        SSL_set_fd(ssl, fd);
        SSL_set_tlsext_host_name(ssl, "pqc-bench");
        if (resume && saved) SSL_set_session(ssl, saved);
        if (SSL_connect(ssl) != 1) {
            fprintf(stderr, "handshake failed trial %d\n", t);
            ERR_print_errors_fp(stderr);
            return 3;
        }
        double t2 = now_us();
        struct tcp_info hi;  // counters at handshake completion: server flight + ClientHello/Finished
        socklen_t hl = sizeof hi;
        memset(&hi, 0, sizeof hi);
        getsockopt(fd, IPPROTO_TCP, TCP_INFO, &hi, &hl);
        // One short application exchange (not timed) so the server's
        // NewSessionTicket is processed and the server sees a clean close.
        char buf[256];
        SSL_write(ssl, "ping\n", 5);
        SSL_read(ssl, buf, sizeof buf);
        struct tcp_info ti;
        socklen_t tl = sizeof ti;
        memset(&ti, 0, sizeof ti);
        getsockopt(fd, IPPROTO_TCP, TCP_INFO, &ti, &tl);
        const char *neg = SSL_group_to_name(ssl, SSL_get_negotiated_group(ssl));
        if (t >= 0)
            printf("%s,%s,%d,%.1f,%.1f,%llu,%llu,%u,%u,%u,%u,%u,%llu,%llu,%u,%u,%d,%s\n", group, mode, t,
                   t2 - t0, t1 - t0, (unsigned long long)ti.tcpi_bytes_acked,
                   (unsigned long long)ti.tcpi_bytes_received, ti.tcpi_segs_out,
                   ti.tcpi_segs_in, ti.tcpi_data_segs_out, ti.tcpi_data_segs_in,
                   ti.tcpi_total_retrans, (unsigned long long)hi.tcpi_bytes_sent,
                   (unsigned long long)hi.tcpi_bytes_received, hi.tcpi_segs_in,
                   hi.tcpi_total_retrans, SSL_session_reused(ssl), neg ? neg : "?");
        fflush(stdout);
        SSL_shutdown(ssl);
        SSL_free(ssl);
        close(fd);
    }
    SSL_CTX_free(ctx);
    return 0;
}
