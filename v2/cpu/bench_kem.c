// One timing harness for every KEM in the paper (review item P0, "control
// benchmarking confounders"). Every operation of every implementation is
// timed individually with the same clock (CLOCK_MONOTONIC_RAW), the same
// warm-up and stopping rule, in the same process, so that liboqs schemes and
// the official HQC reference/AVX2 code differ only in the code under test.
//
// liboqs schemes come from whichever liboqs.so is on LD_LIBRARY_PATH (so one
// binary measures the default build and the uniform -O3 rebuild); the six
// official HQC variants (2025 spec, commit 161cd4f) are linked statically as
// namespaced objects produced by mkobjs.sh.
//
// Usage: taskset -c 2 ./bench_kem [label] [min_seconds] [min_iters] > out.csv
#define _GNU_SOURCE
#include <oqs/oqs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <time.h>

#define DECL(p)                                                                  \
    int p##_crypto_kem_keypair(unsigned char *, unsigned char *);                \
    int p##_crypto_kem_enc(unsigned char *, unsigned char *, const unsigned char *); \
    int p##_crypto_kem_dec(unsigned char *, const unsigned char *, const unsigned char *); \
    void p##_prng_init(uint8_t *, uint8_t *, uint32_t, uint32_t);
DECL(hqc1_ref) DECL(hqc3_ref) DECL(hqc5_ref)
DECL(hqc1_avx2) DECL(hqc3_avx2) DECL(hqc5_avx2)

typedef struct {
    const char *impl, *name;
    size_t pk, sk, ct, ss;
    int (*kp)(unsigned char *, unsigned char *);
    int (*enc)(unsigned char *, unsigned char *, const unsigned char *);
    int (*dec)(unsigned char *, const unsigned char *, const unsigned char *);
    void (*seed)(uint8_t *, uint8_t *, uint32_t, uint32_t);
    OQS_KEM *oqs;
} kem_t;

static double now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3;
}

static long cur_khz(void) {
    FILE *f = fopen("/sys/devices/system/cpu/cpu2/cpufreq/scaling_cur_freq", "r");
    long v = -1;
    if (f) { if (fscanf(f, "%ld", &v) != 1) v = -1; fclose(f); }
    return v;
}

static int cmpd(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static double MIN_SEC = 3.0;
static int MIN_IT = 31, MAX_IT = 20000;
static const char *LABEL = "run";

enum { KP, ENC, DEC };

static int run_op(kem_t *k, int op, unsigned char *pk, unsigned char *sk,
                  unsigned char *ct, unsigned char *ss) {
    if (k->oqs) {
        if (op == KP) return OQS_KEM_keypair(k->oqs, pk, sk) != OQS_SUCCESS;
        if (op == ENC) return OQS_KEM_encaps(k->oqs, ct, ss, pk) != OQS_SUCCESS;
        return OQS_KEM_decaps(k->oqs, ss, ct, sk) != OQS_SUCCESS;
    }
    if (op == KP) return k->kp(pk, sk);
    if (op == ENC) return k->enc(ct, ss, pk);
    return k->dec(ss, ct, sk);
}

static void bench(kem_t *k) {
    unsigned char *pk = malloc(k->pk), *sk = malloc(k->sk), *ct = malloc(k->ct);
    unsigned char *s1 = malloc(k->ss), *s2 = malloc(k->ss);
    double *t = malloc(sizeof(double) * MAX_IT);
    // correctness check before timing
    if (run_op(k, KP, pk, sk, ct, s1) || run_op(k, ENC, pk, sk, ct, s1) ||
        run_op(k, DEC, pk, sk, ct, s2) || memcmp(s1, s2, k->ss)) {
        fprintf(stderr, "FAIL correctness %s %s\n", k->impl, k->name);
        exit(1);
    }
    static const char *opn[] = {"keygen", "encaps", "decaps"};
    for (int op = KP; op <= DEC; op++) {
        double w0 = now_us();  // warm-up: 0.3 s or 5 iterations, whichever is later
        for (int i = 0; i < 5 || now_us() - w0 < 3e5; i++) run_op(k, op, pk, sk, ct, s1);
        if (op == DEC) run_op(k, ENC, pk, sk, ct, s1);  // fresh ct for decaps
        long f0 = cur_khz();
        int n = 0;
        double start = now_us();
        while (n < MAX_IT && (n < MIN_IT || now_us() - start < MIN_SEC * 1e6)) {
            double a = now_us();
            run_op(k, op, pk, sk, ct, s2);
            t[n++] = now_us() - a;
        }
        long f1 = cur_khz();
        double sum = 0, sq = 0;
        for (int i = 0; i < n; i++) sum += t[i];
        double mean = sum / n;
        for (int i = 0; i < n; i++) sq += (t[i] - mean) * (t[i] - mean);
        qsort(t, n, sizeof(double), cmpd);
        printf("%s,%s,%s,%s,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%ld,%ld\n", LABEL, k->impl,
               k->name, opn[op], n, t[n / 2], mean, t[(int)(0.05 * n)],
               t[(int)(0.95 * n)], n > 1 ? __builtin_sqrt(sq / (n - 1)) : 0, f0, f1);
        fflush(stdout);
    }
    free(pk); free(sk); free(ct); free(s1); free(s2); free(t);
}

// ---- energy mode (ENERGY=1): RAPL package and core domains around a loop of
// complete ephemeral exchanges (keygen + encaps + decaps), with an idle
// baseline of the same length measured immediately before and subtracted.
static long long rapl(const char *zone) {
    char p[128];
    snprintf(p, sizeof p, "/sys/class/powercap/%s/energy_uj", zone);
    FILE *f = fopen(p, "r");
    long long v = -1;
    if (f) { if (fscanf(f, "%lld", &v) != 1) v = -1; fclose(f); }
    return v;
}
static long long rapl_range(const char *zone) {
    char p[128];
    snprintf(p, sizeof p, "/sys/class/powercap/%s/max_energy_range_uj", zone);
    FILE *f = fopen(p, "r");
    long long v = 1LL << 62;
    if (f) { if (fscanf(f, "%lld", &v) != 1) v = 1LL << 62; fclose(f); }
    return v;
}
static double pkg_temp(void) {
    for (int i = 0; i < 32; i++) {
        char p[96], ty[64] = {0};
        snprintf(p, sizeof p, "/sys/class/thermal/thermal_zone%d/type", i);
        FILE *f = fopen(p, "r");
        if (!f) continue;
        int ok = fscanf(f, "%63s", ty) == 1;
        fclose(f);
        if (!ok || strcmp(ty, "x86_pkg_temp")) continue;
        snprintf(p, sizeof p, "/sys/class/thermal/thermal_zone%d/temp", i);
        f = fopen(p, "r");
        long t = 0;
        if (f) { if (fscanf(f, "%ld", &t) != 1) t = 0; fclose(f); }
        return t / 1000.0;
    }
    return -1;
}
static double delta_j(long long a, long long b, long long range) {
    return (b >= a ? b - a : b - a + range) / 1e6;
}
static void sleep_s(double s) {
    struct timespec ts = {(time_t)s, (long)((s - (time_t)s) * 1e9)};
    nanosleep(&ts, NULL);
}
static void energy(kem_t *k) {
    const char *PKG = "intel-rapl:0", *CORE = "intel-rapl:0:0";
    long long rp = rapl_range(PKG), rc = rapl_range(CORE);
    unsigned char *pk = malloc(k->pk), *sk = malloc(k->sk), *ct = malloc(k->ct);
    unsigned char *s1 = malloc(k->ss), *s2 = malloc(k->ss);
    sleep_s(5.0);  // cool-down so every scheme starts from the same thermal state
    double T0 = pkg_temp();
    long long ip0 = rapl(PKG), ic0 = rapl(CORE);
    double it0 = now_us();
    sleep_s(MIN_SEC);
    long long ip1 = rapl(PKG), ic1 = rapl(CORE);
    double idle_s = (now_us() - it0) / 1e6;
    double Pp_idle = delta_j(ip0, ip1, rp) / idle_s, Pc_idle = delta_j(ic0, ic1, rc) / idle_s;
    long long p0 = rapl(PKG), c0 = rapl(CORE);
    double t0 = now_us();
    int n = 0;
    while (n < 5 || now_us() - t0 < MIN_SEC * 1e6) {
        run_op(k, KP, pk, sk, ct, s1);
        run_op(k, ENC, pk, sk, ct, s1);
        run_op(k, DEC, pk, sk, ct, s2);
        n++;
    }
    double dt = (now_us() - t0) / 1e6;
    long long p1 = rapl(PKG), c1 = rapl(CORE);
    double Ep = delta_j(p0, p1, rp), Ec = delta_j(c0, c1, rc);
    printf("%s,%s,%s,handshake,%d,%.3f,%.6e,%.6e,%.6e,%.6e,%.3f,%.3f,%.3f,%.1f,%.1f,%ld\n", LABEL,
           k->impl, k->name, n, dt, Ep / n, (Ep - Pp_idle * dt) / n, Ec / n,
           (Ec - Pc_idle * dt) / n, Ep / dt, Pp_idle, Pc_idle, T0, pkg_temp(), cur_khz());
    fflush(stdout);
    free(pk); free(sk); free(ct); free(s1); free(s2);
}

#define OFF(p, nm, PK, SK, CT, impl)                                              \
    {impl, nm, PK, SK, CT, 32, p##_crypto_kem_keypair, p##_crypto_kem_enc,        \
     p##_crypto_kem_dec, p##_prng_init, NULL}

int main(int argc, char **argv) {
    if (argc > 1) LABEL = argv[1];
    if (argc > 2) MIN_SEC = atof(argv[2]);
    if (argc > 3) MIN_IT = atoi(argv[3]);
    OQS_init();
    const char *oqs_names[] = {
        "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
        "NTRU-HPS-2048-677", "NTRU-HRSS-701", "NTRU-HPS-4096-821", "sntrup761",
        "HQC-128", "HQC-192", "HQC-256",   // liboqs <= 0.15 (2023 spec)
        "HQC-1", "HQC-3", "HQC-5",         // liboqs 0.16 (2025 spec)
        "Classic-McEliece-348864", "Classic-McEliece-460896", "Classic-McEliece-8192128"};
    kem_t off[] = {
        OFF(hqc1_ref, "HQC-1", 2241, 2321, 4433, "official-ref"),
        OFF(hqc3_ref, "HQC-3", 4514, 4602, 8978, "official-ref"),
        OFF(hqc5_ref, "HQC-5", 7237, 7333, 14421, "official-ref"),
        OFF(hqc1_avx2, "HQC-1", 2241, 2321, 4433, "official-avx2"),
        OFF(hqc3_avx2, "HQC-3", 4514, 4602, 8978, "official-avx2"),
        OFF(hqc5_avx2, "HQC-5", 7237, 7333, 14421, "official-avx2"),
    };
    const char *only = getenv("ONLY");  // optional substring filter
    int emode = getenv("ENERGY") != NULL;
    void (*measure)(kem_t *) = emode ? energy : bench;
    printf("# liboqs %s, min_sec=%.1f min_iters=%d\n", OQS_version(), MIN_SEC, MIN_IT);
    if (emode)
        printf("label,impl,scheme,op,n,seconds,pkg_J_gross,pkg_J_net,core_J_gross,core_J_net,"
               "pkg_W_gross,pkg_W_idle,core_W_idle,temp_start_C,temp_end_C,khz\n");
    else
        printf("label,impl,scheme,op,n,median_us,mean_us,p05_us,p95_us,sd_us,khz_start,khz_end\n");
    for (size_t i = 0; i < sizeof(oqs_names) / sizeof(*oqs_names); i++) {
        if (only && !strstr(oqs_names[i], only)) continue;
        OQS_KEM *o = OQS_KEM_new(oqs_names[i]);
        if (!o) { fprintf(stderr, "skip %s (not enabled)\n", oqs_names[i]); continue; }
        kem_t k = {"liboqs", oqs_names[i], o->length_public_key, o->length_secret_key,
                   o->length_ciphertext, o->length_shared_secret, 0, 0, 0, 0, o};
        measure(&k);
        OQS_KEM_free(o);
    }
    for (size_t i = 0; i < sizeof(off) / sizeof(*off); i++) {
        if (only && !strstr(off[i].name, only)) continue;
        uint8_t seed[48];
        if (getrandom(seed, sizeof seed, 0) != sizeof seed) return 1;
        off[i].seed(seed, NULL, sizeof seed, 0);
        measure(&off[i]);
    }
    OQS_destroy();
    return 0;
}
