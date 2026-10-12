/* One KeyGen+Encaps+Decaps for a named KEM, for peak-heap profiling under
 * massif (reviewer item #5). Build/run via run_mem.sh. */
#include <oqs/oqs.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    OQS_KEM *kem = OQS_KEM_new(argv[1]);
    if (!kem) return 1;
    uint8_t *pk = malloc(kem->length_public_key);
    uint8_t *sk = malloc(kem->length_secret_key);
    uint8_t *ct = malloc(kem->length_ciphertext);
    uint8_t *ss1 = malloc(kem->length_shared_secret);
    uint8_t *ss2 = malloc(kem->length_shared_secret);
    if (!pk || !sk || !ct || !ss1 || !ss2) return 3;
    OQS_KEM_keypair(kem, pk, sk);
    OQS_KEM_encaps(kem, ct, ss1, pk);
    OQS_KEM_decaps(kem, ss2, ct, sk);
    free(pk); free(sk); free(ct); free(ss1); free(ss2);
    OQS_KEM_free(kem);
    return 0;
}
