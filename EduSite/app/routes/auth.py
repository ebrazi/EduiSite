"""Registration (multi-step, OTP-first) and login."""
from flask import (Blueprint, current_app, make_response, redirect,
                   render_template, request, url_for)

from .. import db, security
from ..services import otp as otp_service

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Step 1: phone + send OTP."""
    sess = security.current_session("user")
    if request.method == "POST":
        phone = otp_service.normalize_phone(request.form.get("phone", ""))
        if not phone:
            return render_template("register_phone.html", csrf=sess["csrf"],
                                   error="شماره موبایل معتبر نیست."), 400
        ok, result = otp_service.issue_otp(phone)
        if not ok:
            return render_template("register_phone.html", error=result,
                                   csrf=sess["csrf"]), 429
        security.session_put(sess, "otp_phone", phone)
        if current_app.config["DEV_MODE"] and result:
            security.session_put(sess, "dev_code", result)
        return redirect(url_for("auth.register_otp"))
    return render_template("register_phone.html", error=None, csrf=sess["csrf"])


@bp.route("/register/otp", methods=["GET", "POST"])
def register_otp():
    sess = security.current_session("user")
    phone = security.session_get(sess, "otp_phone")
    if not phone:
        return redirect(url_for("auth.register"))
    dev_code = security.session_get(sess, "dev_code")
    if request.method == "POST":
        ok, err = otp_service.verify_otp(phone, request.form.get("code", ""))
        if not ok:
            return render_template("register_otp.html", phone=phone,
                                   dev_code=dev_code, error=err,
                                   csrf=sess["csrf"]), 400
        user = db.get_db().execute(
            "SELECT id FROM users WHERE phone=?", (phone,)
        ).fetchone()
        if user:
            security.session_put(sess, "user_id", user["id"])
            return redirect(url_for("user.dashboard"))
        security.session_put(sess, "reg_phone", phone)
        return redirect(url_for("auth.register_relation"))
    return render_template("register_otp.html", phone=phone,
                           dev_code=dev_code, error=None, csrf=sess["csrf"])


@bp.route("/register/relation", methods=["GET", "POST"])
def register_relation():
    """Step 2: whose number is this? (+ student name)"""
    sess = security.current_session("user")
    phone = security.session_get(sess, "reg_phone")
    if not phone:
        return redirect(url_for("auth.register"))
    if request.method == "POST":
        relation = request.form.get("relation", "")
        name = (request.form.get("name") or "").strip()[:80]
        valid = [r[0] for r in current_app.config["RELATION_CHOICES"]]
        if relation not in valid:
            return render_template("register_relation.html",
                                   choices=current_app.config["RELATION_CHOICES"],
                                   error="یکی از گزینه‌ها را انتخاب کنید.",
                                   csrf=sess["csrf"]), 400
        security.session_put(sess, "reg_relation", relation)
        security.session_put(sess, "reg_name", name)
        return redirect(url_for("auth.register_grade"))
    return render_template("register_relation.html",
                           choices=current_app.config["RELATION_CHOICES"],
                           error=None, csrf=sess["csrf"])


@bp.route("/register/grade", methods=["GET", "POST"])
def register_grade():
    sess = security.current_session("user")
    if not security.session_get(sess, "reg_phone"):
        return redirect(url_for("auth.register"))
    if request.method == "POST":
        grade = request.form.get("grade", "")
        if grade not in current_app.config["GRADE_CHOICES"]:
            return render_template("register_grade.html",
                                   grades=current_app.config["GRADE_CHOICES"],
                                   error="مقطع را انتخاب کنید.",
                                   csrf=sess["csrf"]), 400
        security.session_put(sess, "reg_grade", grade)
        return redirect(url_for("auth.register_goal"))
    return render_template("register_grade.html",
                           grades=current_app.config["GRADE_CHOICES"],
                           error=None, csrf=sess["csrf"])


@bp.route("/register/goal", methods=["GET", "POST"])
def register_goal():
    sess = security.current_session("user")
    if not security.session_get(sess, "reg_phone"):
        return redirect(url_for("auth.register"))
    if request.method == "POST":
        goals = [g for g in request.form.getlist("goal")
                 if g in current_app.config["GOAL_CHOICES"]]
        if not goals:
            return render_template("register_goal.html",
                                   goals=current_app.config["GOAL_CHOICES"],
                                   error="حداقل یک هدف را انتخاب کنید.",
                                   csrf=sess["csrf"]), 400
        phone = security.session_get(sess, "reg_phone")
        relation = security.session_get(sess, "reg_relation")
        grade = security.session_get(sess, "reg_grade")
        name = security.session_get(sess, "reg_name", "")
        conn = db.get_db()
        with db.immediate_tx(conn):
            cur = conn.execute(
                "INSERT INTO users(phone, name, owner_relation, grade, goals) "
                "VALUES (?,?,?,?,?)",
                (phone, name, relation, grade, ",".join(goals)),
            )
            conn.execute(
                "INSERT INTO wallets(user_id, balance) VALUES (?, 0)",
                (cur.lastrowid,),
            )
            security.session_put(sess, "user_id", cur.lastrowid)
        for k in ("reg_phone", "reg_relation", "reg_grade", "reg_goal",
                  "otp_phone", "dev_code"):
            security.session_put(sess, k, None)
        return redirect(url_for("user.dashboard"))
    return render_template("register_goal.html",
                           goals=current_app.config["GOAL_CHOICES"],
                           error=None, csrf=sess["csrf"])


@bp.route("/login", methods=["GET", "POST"])
def login():
    sess = security.current_session("user")
    if request.method == "POST":
        phone = otp_service.normalize_phone(request.form.get("phone", ""))
        if not phone:
            return render_template("register_phone.html", csrf=sess["csrf"],
                                   error="شماره موبایل معتبر نیست.",
                                   login_mode=True), 400
        ok, result = otp_service.issue_otp(phone)
        if not ok:
            return render_template("register_phone.html", error=result,
                                   csrf=sess["csrf"], login_mode=True), 429
        security.session_put(sess, "otp_phone", phone)
        if current_app.config["DEV_MODE"] and result:
            security.session_put(sess, "dev_code", result)
        return redirect(url_for("auth.register_otp"))
    return render_template("register_phone.html", error=None,
                           csrf=sess["csrf"], login_mode=True)


@bp.route("/logout", methods=["POST"])
def logout():
    sess = security.current_session("user")
    security.destroy_session(sess)
    resp = make_response(redirect(url_for("public.index")))
    resp.delete_cookie(current_app.config["SESSION_COOKIE_NAME"], path="/")
    return resp
