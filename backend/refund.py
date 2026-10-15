import os
import json
import time
import hashlib
import threading
import oqs  # Post-Quantum crypto (Dilithium)

STATE_FILE = "state.json"
CHAIN_FILE = "chain.json"

# -------------------------
# PQC Signature (Dilithium2)
# -------------------------
def generate_pq_signature(message: bytes):
    """Generate a Dilithium2 PQC signature for a message (returns dict)."""
    with oqs.Signature("Dilithium2") as signer:
        public_key = signer.generate_keypair()
        signature = signer.sign(message)
        return {
            "algorithm": "Dilithium2",
            "public_key": public_key.hex(),
            "signature": signature.hex(),
        }


def verify_pq_signature(message: bytes, sigdict: dict) -> bool:
    """Verify a PQC signature dict created with generate_pq_signature()."""
    try:
        algorithm = sigdict.get("algorithm")
        public_key = bytes.fromhex(sigdict["public_key"])
        signature = bytes.fromhex(sigdict["signature"])
        with oqs.Signature(algorithm) as verifier:
            return verifier.verify(message, signature, public_key)
    except Exception:
        return False


# -------------------------
# State Helpers
# -------------------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"balances": {}, "history": [], "refunds": []}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# -------------------------
# Blockchain Helpers
# -------------------------
def _hash_block(block: dict) -> str:
    block_copy = block.copy()
    block_copy.pop("hash", None)
    return hashlib.sha256(json.dumps(block_copy, sort_keys=True).encode()).hexdigest()


def load_blockchain():
    if not os.path.exists(CHAIN_FILE):
        # initialize chain with genesis block
        genesis = {
            "index": 0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "transactions": [],
            "previous_hash": "0",
        }
        genesis["hash"] = _hash_block(genesis)
        with open(CHAIN_FILE, "w") as f:
            json.dump([genesis], f, indent=2)
        return [genesis]
    with open(CHAIN_FILE, "r") as f:
        return json.load(f)


def save_blockchain(chain):
    with open(CHAIN_FILE, "w") as f:
        json.dump(chain, f, indent=2)


def add_block(transaction: dict):
    """Each transaction = new block in this simplified demo blockchain."""
    chain = load_blockchain()
    block = {
        "index": len(chain),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "transactions": [transaction],
        "previous_hash": chain[-1]["hash"],
    }
    block["hash"] = _hash_block(block)
    chain.append(block)
    save_blockchain(chain)
    return block


# -------------------------
# Refund System
# -------------------------
def process_refund(tx: dict, delay: int = 5):
    """
    Schedule a blockchain-backed refund.
    tx must include {"tx_id", "sender", "amount"}.
    Optional "refund_reason" will be used in history and PQC signature.
    """

    # 1. Mark refund as pending in state
    state = load_state()
    refund_entry = {
        "original_tx_id": tx.get("tx_id"),
        "sender": tx.get("sender"),
        "amount": tx.get("amount"),
        "refund_reason": tx.get("refund_reason", "auto-refund"),
        "status": "pending",
        "scheduled_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "execute_after_sec": delay,
    }
    state.setdefault("refunds", []).append(refund_entry)
    save_state(state)

    def _do_refund():
        state = load_state()
        reason = tx.get("refund_reason", "auto-refund")

        refund_tx = {
            "tx_id": f"refund-{tx['tx_id']}",
            "sender": "system",
            "receiver": tx["sender"],
            "amount": tx["amount"],
            "status": "refund",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "meta": {"reason": reason},
            "refund_reason": reason,
        }

        # PQC sign refund including refund reason
        signed_view = (
            f"{refund_tx['tx_id']}|{refund_tx['receiver']}|"
            f"{refund_tx['amount']}|refund|{refund_tx['timestamp']}|{refund_tx['refund_reason']}"
        ).encode()

        pq_sig = generate_pq_signature(signed_view)
        refund_tx["pq_signature"] = pq_sig
        refund_tx["pq_verified"] = verify_pq_signature(signed_view, pq_sig)

        # Add refund block
        block = add_block(refund_tx)
        refund_tx["block_number"] = block["index"]
        refund_tx["blockchain_hash"] = block["hash"]

        # credit sender
        state["balances"].setdefault(tx["sender"], 0.0)
        state["balances"][tx["sender"]] += tx["amount"]

        # update history
        state["history"].append(refund_tx)

        # update refund status
        for r in state.get("refunds", []):
            if r["original_tx_id"] == tx.get("tx_id") and r["status"] == "pending":
                r["status"] = "completed"
                r["completed_at"] = refund_tx["timestamp"]
                r["block_number"] = refund_tx["block_number"]
                break

        save_state(state)

        print(f"💸 Refund executed: {refund_tx}")

    # background thread for async refund
    threading.Timer(delay, _do_refund).start()
