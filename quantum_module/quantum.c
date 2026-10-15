// quantum.c
// Demonstration using liboqs: Dilithium2 (sign) + Kyber (KEM) + SHA256 helper.
// Compile with: gcc quantum.c -o quantum -loqs
// (If liboqs is in non-standard path, use pkg-config or adjust include/library paths)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <oqs/oqs.h>
#include <openssl/sha.h> // optional: keep SHA256 helper

// Helper: print bytes as hex
void bytes_to_hex(const uint8_t *in, size_t in_len, char *out_hex, size_t out_hex_len) {
    if (out_hex_len < (in_len * 2 + 1)) {
        if (out_hex_len > 0) out_hex[0] = '\0';
        return;
    }
    for (size_t i = 0; i < in_len; i++) {
        sprintf(out_hex + i*2, "%02x", in[i]);
    }
    out_hex[in_len*2] = '\0';
}

// SHA-256 helper (kept from your original)
void hash_message(const char* msg, char* out_hex) {
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256((unsigned char*)msg, strlen(msg), hash);
    bytes_to_hex(hash, SHA256_DIGEST_LENGTH, out_hex, 65);
}

// ------- Dilithium (signature) demo -------
int demo_dilithium(const char *message) {
    const char *alg = "Dilithium2"; // change if you want a different Dilithium variant
    OQS_SIG *sig = OQS_SIG_new(alg);
    if (sig == NULL) {
        fprintf(stderr, "Failed to create OQS_SIG for %s\n", alg);
        return 1;
    }

    // Allocate key buffers
    uint8_t *public_key = malloc(OQS_SIG_public_key_length(sig));
    uint8_t *secret_key = malloc(OQS_SIG_secret_key_length(sig));
    if (!public_key || !secret_key) {
        fprintf(stderr, "Memory alloc failed\n");
        OQS_SIG_free(sig);
        return 1;
    }

    // Keypair
    if (OQS_SIG_keypair(sig, public_key, secret_key) != OQS_SUCCESS) {
        fprintf(stderr, "OQS_SIG_keypair failed\n");
        free(public_key); free(secret_key); OQS_SIG_free(sig);
        return 1;
    }

    // Sign
    size_t msg_len = strlen(message);
    size_t sig_len = OQS_SIG_bytes(sig);
    uint8_t *signature = malloc(sig_len);
    size_t actual_sig_len = 0;
    if (OQS_SIG_sign(sig, signature, &actual_sig_len, (const uint8_t *)message, msg_len, secret_key) != OQS_SUCCESS) {
        fprintf(stderr, "OQS_SIG_sign failed\n");
        free(public_key); free(secret_key); free(signature); OQS_SIG_free(sig);
        return 1;
    }

    // Verify
    int verify_ok = OQS_SIG_verify(sig, (const uint8_t *)message, msg_len, signature, actual_sig_len, public_key) == OQS_SUCCESS;

    // Print results (hex)
    char hex_pk[OQS_SIG_public_key_length(sig)*2 + 1];
    char hex_sk[OQS_SIG_secret_key_length(sig)*2 + 1];
    char hex_sig[actual_sig_len*2 + 1];
    bytes_to_hex(public_key, OQS_SIG_public_key_length(sig), hex_pk, sizeof(hex_pk));
    bytes_to_hex(secret_key, OQS_SIG_secret_key_length(sig), hex_sk, sizeof(hex_sk));
    bytes_to_hex(signature, actual_sig_len, hex_sig, sizeof(hex_sig));

    printf("== Dilithium2 Signature Demo ==\n");
    printf("Algorithm: %s\n", alg);
    printf("Message: %s\n", message);
    printf("Public key (%zu bytes): %s\n", OQS_SIG_public_key_length(sig), hex_pk);
    printf("Secret key (%zu bytes): %s\n", OQS_SIG_secret_key_length(sig), hex_sk);
    printf("Signature (%zu bytes): %s\n", actual_sig_len, hex_sig);
    printf("Signature verification: %s\n\n", verify_ok ? "OK" : "FAILED");

    // cleanup
    free(public_key); free(secret_key); free(signature);
    OQS_SIG_free(sig);
    return verify_ok ? 0 : 2;
}

// ------- Kyber (KEM) demo -------
int demo_kyber() {
    // choose variant (Kyber512, Kyber768, Kyber1024). Use whichever liboqs supports.
    const char *kem_alg = NULL;
    // prefer Kyber512 if available (for demo)
    if (OQS_KEM_alg_is_enabled("Kyber512")) kem_alg = "Kyber512";
    else if (OQS_KEM_alg_is_enabled("Kyber768")) kem_alg = "Kyber768";
    else if (OQS_KEM_alg_is_enabled("Kyber1024")) kem_alg = "Kyber1024";
    else {
        fprintf(stderr, "No Kyber KEM algorithms are enabled in this liboqs build.\n");
        return 1;
    }

    OQS_KEM *kem = OQS_KEM_new(kem_alg);
    if (kem == NULL) {
        fprintf(stderr, "Failed to create OQS_KEM for %s\n", kem_alg);
        return 1;
    }

    // Allocate buffers
    uint8_t *pk = malloc(OQS_KEM_length_public_key(kem));
    uint8_t *sk = malloc(OQS_KEM_length_secret_key(kem));
    uint8_t *ct = malloc(OQS_KEM_length_ciphertext(kem));
    uint8_t *ss = malloc(OQS_KEM_length_shared_secret(kem));
    uint8_t *ss2 = malloc(OQS_KEM_length_shared_secret(kem));
    if (!pk || !sk || !ct || !ss || !ss2) {
        fprintf(stderr, "Memory alloc failed\n");
        OQS_KEM_free(kem);
        return 1;
    }

    // Keypair
    if (OQS_KEM_keypair(kem, pk, sk) != OQS_SUCCESS) {
        fprintf(stderr, "OQS_KEM_keypair failed\n");
        goto kem_cleanup;
    }

    // Encapsulate (by sender)
    if (OQS_KEM_encaps(kem, ct, ss, pk) != OQS_SUCCESS) {
        fprintf(stderr, "OQS_KEM_encaps failed\n");
        goto kem_cleanup;
    }

    // Decapsulate (by receiver)
    if (OQS_KEM_decaps(kem, ss2, ct, sk) != OQS_SUCCESS) {
        fprintf(stderr, "OQS_KEM_decaps failed\n");
        goto kem_cleanup;
    }

    // Compare shared secrets
    int equal = (memcmp(ss, ss2, OQS_KEM_length_shared_secret(kem)) == 0);

    // Print hex outputs
    char hex_pk[OQS_KEM_length_public_key(kem)*2 + 1];
    char hex_sk[OQS_KEM_length_secret_key(kem)*2 + 1];
    char hex_ct[OQS_KEM_length_ciphertext(kem)*2 + 1];
    char hex_ss[OQS_KEM_length_shared_secret(kem)*2 + 1];
    bytes_to_hex(pk, OQS_KEM_length_public_key(kem), hex_pk, sizeof(hex_pk));
    bytes_to_hex(sk, OQS_KEM_length_secret_key(kem), hex_sk, sizeof(hex_sk));
    bytes_to_hex(ct, OQS_KEM_length_ciphertext(kem), hex_ct, sizeof(hex_ct));
    bytes_to_hex(ss, OQS_KEM_length_shared_secret(kem), hex_ss, sizeof(hex_ss));

    printf("== %s KEM Demo ==\n", kem_alg);
    printf("Public key (%zu bytes): %s\n", OQS_KEM_length_public_key(kem), hex_pk);
    printf("Secret key (%zu bytes): %s\n", OQS_KEM_length_secret_key(kem), hex_sk);
    printf("Ciphertext (%zu bytes): %s\n", OQS_KEM_length_ciphertext(kem), hex_ct);
    printf("Shared secret (%zu bytes): %s\n", OQS_KEM_length_shared_secret(kem), hex_ss);
    printf("Shared secrets match: %s\n\n", equal ? "YES" : "NO");

kem_cleanup:
    free(pk); free(sk); free(ct); free(ss); free(ss2);
    OQS_KEM_free(kem);
    return equal ? 0 : 2;
}

// ------- CLI usage -------
void print_usage(const char *prog) {
    printf("Usage: %s <command> [args]\n", prog);
    printf("Commands:\n");
    printf("  hash <message>           - SHA256 hex of message\n");
    printf("  sign <message>           - Dilithium2 keypair, sign and verify message\n");
    printf("  kem                      - Kyber KEM demo (keypair, encaps, decaps)\n");
    printf("\nExamples:\n  %s hash \"hello\"\n  %s sign \"hello\"\n  %s kem\n", prog, prog, prog);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    const char *cmd = argv[1];

    if (strcmp(cmd, "hash") == 0) {
        if (argc < 3) { print_usage(argv[0]); return 1; }
        char hex[65] = {0};
        hash_message(argv[2], hex);
        printf("%s\n", hex);
        return 0;
    } else if (strcmp(cmd, "sign") == 0) {
        if (argc < 3) { print_usage(argv[0]); return 1; }
        return demo_dilithium(argv[2]);
    } else if (strcmp(cmd, "kem") == 0) {
        return demo_kyber();
    } else {
        print_usage(argv[0]);
        return 1;
    }
}
