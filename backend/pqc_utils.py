import oqs

# --- Post-Quantum Signature (Dilithium3) ---
def pqc_sign(message: bytes):
    """
    Signs a message using Dilithium3 (PQC signature).
    Returns the public key and signature.
    """
    with oqs.Signature("Dilithium3") as sig:
        pk = sig.generate_keypair()
        signature = sig.sign(message)
    return pk, signature

def pqc_verify(message: bytes, signature: bytes, public_key: bytes):
    """
    Verifies a PQC signature.
    """
    with oqs.Signature("Dilithium3") as sig:
        return sig.verify(message, signature, public_key)

# --- Post-Quantum Key Encapsulation (Kyber768) ---
def pqc_kem():
    """
    Performs a PQC key encapsulation using Kyber768.
    Returns all values, but only the last two are needed for the shared secret.
    """
    with oqs.KeyEncapsulation("Kyber768") as kem:
        pk = kem.generate_keypair()
        ct, ss_b = kem.encap_secret(pk)
        ss_a = kem.decap_secret(ct)
    # Return everything; caller can ignore unwanted values
    return pk, ct, ss_a, ss_b
