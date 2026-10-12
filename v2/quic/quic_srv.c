// Minimal blocking QUIC echo server for the PQ-QUIC measurements, derived
// from OpenSSL 3.5 demos/guide/quic-server-block.c. Adds: a restricted
// key-exchange group list, a certificate chain file (leaf first), optional
// oqs-provider loading, exit after N connections, and the choice of address
// validation: by default the listener runs with SSL_LISTENER_FLAG_NO_VALIDATE
// (no Retry round trip, so RFC 9000's 3x anti-amplification limit governs
// the server's first flight, as on a server not under attack); "retry" keeps
// OpenSSL 3.5's default of validating every client with a Retry packet.
//
// Usage: quic_srv port chain.pem key.pem groups nconn [oqs|-] [retry]
#include <netinet/in.h>
#include <openssl/err.h>
#include <openssl/provider.h>
#include <openssl/quic.h>
#include <openssl/ssl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static const unsigned char alpn[] = {8, 'o', 's', 's', 'l', 't', 'e', 's', 't'};

static int select_alpn(SSL *s, const unsigned char **out, unsigned char *outlen,
                       const unsigned char *in, unsigned int inlen, void *arg) {
    (void)s; (void)arg;
    if (SSL_select_next_proto((unsigned char **)out, outlen, alpn, sizeof alpn, in, inlen) ==
        OPENSSL_NPN_NEGOTIATED)
        return SSL_TLSEXT_ERR_OK;
    return SSL_TLSEXT_ERR_ALERT_FATAL;
}

int main(int argc, char **argv) {
    if (argc < 6) {
        fprintf(stderr, "usage: %s port chain.pem key.pem groups nconn [oqs]\n", argv[0]);
        return 1;
    }
    int port = atoi(argv[1]), nconn = atoi(argv[5]);
    if (argc > 6 && !strcmp(argv[6], "oqs")) {
        if (!OSSL_PROVIDER_load(NULL, "oqsprovider") || !OSSL_PROVIDER_load(NULL, "default")) {
            ERR_print_errors_fp(stderr);
            return 1;
        }
    }
    SSL_CTX *ctx = SSL_CTX_new(OSSL_QUIC_server_method());
    if (!ctx || SSL_CTX_use_certificate_chain_file(ctx, argv[2]) <= 0 ||
        SSL_CTX_use_PrivateKey_file(ctx, argv[3], SSL_FILETYPE_PEM) <= 0 ||
        !SSL_CTX_set1_groups_list(ctx, argv[4])) {
        ERR_print_errors_fp(stderr);
        return 1;
    }
    SSL_CTX_set_verify(ctx, SSL_VERIFY_NONE, NULL);
    SSL_CTX_set_alpn_select_cb(ctx, select_alpn, NULL);

    int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    struct sockaddr_in sa = {.sin_family = AF_INET, .sin_port = htons(port)};
    if (bind(fd, (struct sockaddr *)&sa, sizeof sa)) { perror("bind"); return 1; }
    int retry = argc > 7 && !strcmp(argv[7], "retry");
    SSL *ls = SSL_new_listener(ctx, retry ? 0 : SSL_LISTENER_FLAG_NO_VALIDATE);
    if (!ls || !SSL_set_fd(ls, fd) || !SSL_listen(ls)) { ERR_print_errors_fp(stderr); return 1; }
    for (int i = 0; i < nconn; i++) {
        ERR_clear_error();
        SSL *c = SSL_accept_connection(ls, 0);
        if (!c) { ERR_print_errors_fp(stderr); return 2; }
        unsigned char buf[4096];
        size_t n, w;
        while (SSL_read_ex(c, buf, sizeof buf, &n) > 0)
            if (!SSL_write_ex(c, buf, n, &w)) break;
        SSL_stream_conclude(c, 0);
        while (SSL_shutdown(c) != 1) continue;
        SSL_free(c);
    }
    SSL_free(ls);
    SSL_CTX_free(ctx);
    close(fd);
    return 0;
}
