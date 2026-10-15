from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import time
import uuid
import csv
import io
import refund
import transaction
from refund import load_state, save_state
from refund import load_blockchain, add_block

app = Flask(__name__)
CORS(app)


# -------------------------
# Utility Helpers
# -------------------------
def truncate(val, length=40):
    """Truncate long strings for display."""
    if not val:
        return val
    return val[:length] + "..." if len(val) > length else val


def enrich_tx(tx: dict):
    """Add RBI-demo friendly fields (truncated keys, verification, metadata)."""
    tx_copy = tx.copy()

    # PQ verification
    try:
        tx_copy["pq_verified"] = transaction.verify_transaction(tx)
    except Exception:
        tx_copy["pq_verified"] = False

    # Truncate heavy fields if they exist
    if "pq_signature" in tx_copy:
        tx_copy["pq_signature_display"] = truncate(str(tx_copy["pq_signature"]))
    if "public_key" in tx_copy:
        tx_copy["public_key_display"] = truncate(str(tx_copy["public_key"]))

    # Add RBI-required metadata
    tx_copy["upi_reference_id"] = "UPI-" + str(uuid.uuid4())[:8]
    tx_copy["blockchain_hash"] = "blk_" + str(uuid.uuid4())[:12]

    return tx_copy


# -------------------------
# Routes
# -------------------------

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "running", "time": time.strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/balances", methods=["GET"])
def balances():
    state = load_state()
    return jsonify(state.get("balances", {}))


@app.route("/history", methods=["GET"])
def history():
    state = load_state()
    return jsonify([enrich_tx(tx) for tx in state.get("history", [])])


@app.route("/chain", methods=["GET"])
def chain():
    chain_data = load_blockchain()
    return jsonify(chain_data)


@app.route("/send", methods=["POST"])
def send():
    """
    Single transaction.
    Expected: {sender, receiver, amount, upi_pin, simulate_fail}
    """
    data = request.get_json(force=True)
    sender = data.get("sender")
    receiver = data.get("receiver")
    amount = float(data.get("amount", 0))
    simulate_fail = bool(data.get("simulate_fail", False))

    if not sender or not receiver or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid input"}), 400

    state = load_state()
    state["balances"].setdefault(sender, 1000.0)  # init balance
    state["balances"].setdefault(receiver, 1000.0)

    if state["balances"][sender] < amount:
        return jsonify({"status": "error", "message": "Insufficient funds"}), 400

    # create PQC-signed transaction
    tx = transaction.create_transaction(sender, receiver, amount, status="pending")

    # debit
    state["balances"][sender] -= amount
    state["history"].append(tx)
    save_state(state)

    if simulate_fail:
        # Refund will go through blockchain
        refund.process_refund(tx, delay=5)
        return jsonify({"status": "failed_refund_scheduled", "transaction": enrich_tx(tx)})

    # success
    state["balances"][receiver] += amount
    tx["status"] = "success"
    tx = transaction.create_transaction(sender, receiver, amount, status="success")
    state["history"].append(tx)
    save_state(state)

    # ✅ Normal send does NOT call add_block
    return jsonify({"status": "success", "transaction": enrich_tx(tx)})


@app.route("/batch_send", methods=["POST"])
def batch_send():
    """
    Batch transaction.
    Expected: {sender, upi_pin, transfers:[{receiver,amount}], simulate_fail}
    """
    data = request.get_json(force=True)
    sender = data.get("sender")
    transfers = data.get("transfers", [])
    simulate_fail = bool(data.get("simulate_fail", False))

    if not sender or not transfers:
        return jsonify({"status": "error", "message": "Invalid input"}), 400

    state = load_state()
    state["balances"].setdefault(sender, 1000.0)

    total_amount = sum(float(t.get("amount", 0)) for t in transfers)
    if state["balances"][sender] < total_amount:
        return jsonify({"status": "error", "message": "Insufficient funds"}), 400

    batch_id = str(uuid.uuid4())
    batch_tx = {
        "batch_id": batch_id,
        "sender": sender,
        "transfers": transfers,
        "total_amount": total_amount,
        "status": "pending",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # debit
    state["balances"][sender] -= total_amount
    state["history"].append(batch_tx)
    save_state(state)
    # ✅ Batch transactions go through blockchain
    add_block(batch_tx)

    if simulate_fail:
        refund.process_refund(
            {"tx_id": batch_id, "sender": sender, "amount": total_amount}, delay=5
        )
        return jsonify({"status": "failed_refund_scheduled", "batch": enrich_tx(batch_tx)})

    # success
    for t in transfers:
        rcv = t.get("receiver")
        amt = float(t.get("amount", 0))
        if amt > 0 and rcv:
            state["balances"].setdefault(rcv, 1000.0)
            state["balances"][rcv] += amt

    batch_tx["status"] = "success"
    signed_view = f"{batch_tx['batch_id']}|{batch_tx['sender']}|{batch_tx['total_amount']}|{batch_tx['status']}|{batch_tx['timestamp']}".encode()
    batch_tx["pq_signature"] = transaction.generate_pq_signature(signed_view)

    state["history"].append(batch_tx)
    save_state(state)
    add_block(batch_tx)

    return jsonify({"status": "success", "batch": enrich_tx(batch_tx)})


# -------------------------
# Extra Features
# -------------------------

@app.route("/search_tx", methods=["GET"])
def search_tx():
    """Search/filter transactions by sender, receiver, status, amount range."""
    args = request.args
    sender = args.get("sender")
    receiver = args.get("receiver")
    status = args.get("status")
    min_amt = float(args.get("min_amount", 0))
    max_amt = float(args.get("max_amount", 1e18))

    state = load_state()
    results = []
    for tx in state.get("history", []):
        amt = float(tx.get("amount", tx.get("total_amount", 0)))
        if sender and tx.get("sender") != sender:
            continue
        if receiver and tx.get("receiver") != receiver:
            continue
        if status and tx.get("status") != status:
            continue
        if not (min_amt <= amt <= max_amt):
            continue
        results.append(enrich_tx(tx))
    return jsonify(results)


@app.route("/refund_status", methods=["GET"])
def refund_status():
    """Check pending/processed refunds."""
    state = load_state()
    refunds = state.get("refunds", [])
    return jsonify(refunds)


@app.route("/export_report", methods=["GET"])
def export_report():
    """Export balances and history as JSON or CSV."""
    export_type = request.args.get("type", "json")
    state = load_state()

    if export_type == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["tx_id", "sender", "receiver", "amount", "status", "timestamp"])
        for tx in state.get("history", []):
            writer.writerow([
                tx.get("tx_id", tx.get("batch_id", "")),
                tx.get("sender", ""),
                tx.get("receiver", ""),
                tx.get("amount", tx.get("total_amount", "")),
                tx.get("status", ""),
                tx.get("timestamp", ""),
            ])
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=report.csv"})

    return jsonify(state)


@app.route("/verify_chain", methods=["GET"])
def verify_chain():
    """Verify blockchain integrity by checking hashes."""
    chain = load_blockchain()
    for i in range(1, len(chain)):
        if chain[i]["prev_hash"] != chain[i - 1]["hash"]:
            return jsonify({"status": "corrupted", "at_block": i})
    return jsonify({"status": "valid", "blocks": len(chain)})


@app.route("/analytics", methods=["GET"])
def analytics():
    """Basic analytics about transactions."""
    state = load_state()
    history = state.get("history", [])
    total_tx = len(history)
    success_tx = sum(1 for tx in history if tx.get("status") == "success")
    failed_tx = sum(1 for tx in history if tx.get("status") == "failed")
    total_volume = sum(float(tx.get("amount", tx.get("total_amount", 0))) for tx in history)
    refunds = len(state.get("refunds", []))

    return jsonify({
        "total_transactions": total_tx,
        "successful_transactions": success_tx,
        "failed_transactions": failed_tx,
        "total_volume": total_volume,
        "refunds_count": refunds,
    })


# -------------------------
# Run Server
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
