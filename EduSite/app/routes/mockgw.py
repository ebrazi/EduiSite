"""DEV-ONLY mock payment gateway pages. Registered only when DEV_MODE=1.

Simulates a real gateway: the user lands on the gateway, chooses
success/failure, and the gateway redirects (302) to the app's callback with a
signed payload.
"""
import secrets

from flask import Blueprint, abort, redirect, render_template, request, url_for

from .. import db, security
from ..jalali import format_money
from ..services.payments import MockGateway

bp = Blueprint("mockgw", __name__)


@bp.before_request
def dev_only():
    from flask import current_app
    if not current_app.config["DEV_MODE"]:
        abort(404)


@bp.route("/mock-gateway/pay/<int:payment_id>", methods=["GET"])
def pay_page(payment_id):
    conn = db.get_db()
    p = conn.execute(
        "SELECT * FROM payments WHERE id=? AND status='initiated'", (payment_id,)
    ).fetchone()
    if p is None:
        abort(404)
    return render_template("mock_pay.html", payment=p, money=format_money,
                           csrf=security.current_session("user")["csrf"])


@bp.route("/mock-gateway/pay/<int:payment_id>", methods=["POST"])
def pay_submit(payment_id):
    conn = db.get_db()
    p = conn.execute(
        "SELECT * FROM payments WHERE id=? AND status='initiated'", (payment_id,)
    ).fetchone()
    if p is None:
        abort(404)
    outcome = request.form.get("outcome")
    if outcome not in ("success", "failed"):
        abort(400)
    tx_id = "MOCK-" + secrets.token_hex(8)
    return redirect(MockGateway.callback_url(payment_id, tx_id, outcome))
