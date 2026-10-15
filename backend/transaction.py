import uuid
import time
from refund import generate_pq_signature, verify_pq_signature


def _now_utc():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


# -------------------------
# Single Transaction
# -------------------------
def create_transaction(sender, receiver, amount, status="success", meta=None, refund_reason=None):
    """Create a PQC-signed single transaction dict with optional refund reason."""
    tx = {
        "tx_id": str(uuid.uuid4()),
        "sender": sender,
        "receiver": receiver,
        "amount": float(amount),
        "status": status,
        "timestamp": _now_utc(),
        "meta": meta or {},
        "pq_signature": None,
        "refund_reason": refund_reason,  # store refund reason
    }

    signed_view = (
        f"{tx['tx_id']}|{tx['sender']}|{tx['receiver']}|"
        f"{tx['amount']}|{tx['status']}|{tx['timestamp']}|{tx['refund_reason']}"
    ).encode()

    tx["pq_signature"] = generate_pq_signature(signed_view)
    return tx


def verify_transaction(tx: dict) -> bool:
    """Verify PQC signature of a single transaction dict."""
    try:
        signed_view = (
            f"{tx['tx_id']}|{tx['sender']}|{tx['receiver']}|"
            f"{tx['amount']}|{tx['status']}|{tx['timestamp']}|{tx.get('refund_reason')}"
        ).encode()
        return verify_pq_signature(signed_view, tx["pq_signature"])
    except Exception:
        return False


# -------------------------
# Batch Transaction
# -------------------------
def create_batch_transaction(sender, transfers, status="success", meta=None, refund_reason=None):
    """
    Create a PQC-signed batch transaction dict.
    transfers: list of {receiver, amount}
    """
    batch = {
        "batch_id": str(uuid.uuid4()),
        "sender": sender,
        "transfers": transfers,
        "total_amount": sum(float(t.get("amount", 0)) for t in transfers),
        "status": status,
        "timestamp": _now_utc(),
        "meta": meta or {},
        "pq_signature": None,
        "refund_reason": refund_reason,
    }

    # Create a signed string representation of the batch
    transfers_repr = ";".join([f"{t['receiver']}:{t['amount']}" for t in transfers])
    signed_view = (
        f"{batch['batch_id']}|{batch['sender']}|{batch['total_amount']}|"
        f"{batch['status']}|{batch['timestamp']}|{transfers_repr}|{batch['refund_reason']}"
    ).encode()

    batch["pq_signature"] = generate_pq_signature(signed_view)
    return batch


def verify_batch_transaction(batch: dict) -> bool:
    """Verify PQC signature of a batch transaction dict."""
    try:
        transfers = batch.get("transfers", [])
        transfers_repr = ";".join([f"{t['receiver']}:{t['amount']}" for t in transfers])
        signed_view = (
            f"{batch['batch_id']}|{batch['sender']}|{batch['total_amount']}|"
            f"{batch['status']}|{batch['timestamp']}|{transfers_repr}|{batch.get('refund_reason')}"
        ).encode()
        return verify_pq_signature(signed_view, batch["pq_signature"])
    except Exception:
        return False
