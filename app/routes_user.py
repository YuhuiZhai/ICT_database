from datetime import datetime
from io import BytesIO

import pandas as pd
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    session,
    current_app,
)
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import SignatureExpired, BadSignature
from sqlalchemy.exc import IntegrityError

from . import db, mail
from .models import User, VehicleRequestForm
from .utils import parse_date_or_none, audit_vehicle_mileage_and_alert

bp = Blueprint("user", __name__)


@bp.route("/")
def home():
    return render_template("user_front_page.html")


@bp.route("/user_register", methods=["GET", "POST"])
def user_register():
    error = None
    message = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            return render_template(
                "user_register.html",
                error="Email and password are required.",
                message=None,
            )

        if User.query.filter_by(email=email).first():
            return render_template(
                "user_register.html",
                error="Email already registered",
                message=None,
            )

        hashed_pw = generate_password_hash(password)
        user = User(email=email, password=hashed_pw, is_confirmed=False)
        db.session.add(user)

        try:
            # Reserve uniqueness now; do NOT commit until email sent
            db.session.flush()

            serializer = current_app.config["SERIALIZER"]
            token = serializer.dumps(email, salt="email-confirm")
            confirm_link = url_for("user.user_confirm_email", token=token, _external=True)

            msg = Message(subject="Confirm your account", recipients=[email])
            msg.body = (
                "Hi,\n\n"
                "Please click the link below to confirm your account:\n"
                f"{confirm_link}\n\n"
                "If you did not register this account, you can ignore this email."
            )

            mail.send(msg)

            db.session.commit()

            message = "Registration successful. Please check your email to confirm your account."
            return render_template("user_register.html", error=None, message=message)

        except IntegrityError:
            db.session.rollback()
            error = "Email already registered."
            return render_template("user_register.html", error=error, message=None)

        except Exception:
            db.session.rollback()
            current_app.logger.exception("[Register] Email send failed")
            error = "Could not send confirmation email right now. Please try again later."
            return render_template("user_register.html", error=error, message=None)

    return render_template("user_register.html", error=error, message=message)


@bp.route("/user_confirm_email/<token>")
def user_confirm_email(token):
    serializer = current_app.config["SERIALIZER"]
    try:
        email = serializer.loads(token, salt="email-confirm", max_age=86400)  # 24h
    except SignatureExpired:
        return "Confirmation link has expired.", 400
    except BadSignature:
        return "Invalid confirmation link.", 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return "User not found.", 404

    user.is_confirmed = True
    db.session.commit()
    return redirect(url_for("user.user_my_forms"))


@bp.route("/user_login", methods=["GET", "POST"])
def user_login():
    error = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            error = "Invalid email or password"
        elif not user.is_confirmed:
            error = "Please confirm your email before logging in. Check your email inbox."
        else:
            login_user(user)
            return redirect(url_for("user.user_my_forms"))

    return render_template("user_login.html", error=error)


@bp.route("/user_logout")
def user_logout():
    logout_user()
    return redirect(url_for("user.home"))


# ---------- Password Reset ----------
@bp.route("/user_forgot_password", methods=["GET", "POST"])
def user_forgot_password():
    message = None
    success = False

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            message = "No account found with that email"
        else:
            serializer = current_app.config["SERIALIZER"]
            token = serializer.dumps(email, salt="password-reset")
            link = url_for("user.user_reset_password", token=token, _external=True)

            msg = Message("Reset your password", recipients=[email])
            msg.body = f"Click here to reset your password: {link}\n\n(This link expires in 1 hour.)"

            try:
                mail.send(msg)
                message = "A reset link has been sent to your email"
                success = True
            except Exception as e:
                print("[Mail] password reset send failed:", repr(e))
                message = (
                    "We could not send the reset email from the server right now. "
                    "Please try again later or contact the admin."
                )
                success = False

    return render_template("user_forgot_password.html", message=message, success=success)


@bp.route("/user_reset_password/<token>", methods=["GET", "POST"])
def user_reset_password(token):
    serializer = current_app.config["SERIALIZER"]
    try:
        email = serializer.loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        return render_template("user_reset_password.html", message="Link expired", success=False)
    except BadSignature:
        return render_template("user_reset_password.html", message="Invalid link", success=False)

    if request.method == "POST":
        new_pw = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()

        if user:
            user.password = generate_password_hash(new_pw)
            db.session.commit()
            return redirect(url_for("user.user_login"))

        return render_template("user_reset_password.html", message="User not found", success=False)

    return render_template("user_reset_password.html", message=None, success=False)


@bp.route("/user_my_forms")
@login_required
def user_my_forms():
    page = request.args.get("page", 1, type=int)
    per_page = 10

    pagination = (
        VehicleRequestForm.query
        .filter_by(email=current_user.email)
        .order_by(VehicleRequestForm.status.desc(), VehicleRequestForm.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    records = pagination.items
    return render_template("user_my_forms.html", records=records, pagination=pagination)


@bp.route("/user_view_form/<int:form_id>")
@login_required
def user_view_form(form_id):
    record = VehicleRequestForm.query.get_or_404(form_id)
    if record.email != current_user.email:
        return "❌ Unauthorized", 403
    return render_template("form_readonly.html", model=record)


# ---------- User Form Submit ----------
@bp.route("/submit_form", methods=["GET", "POST"])
@login_required
def vehicle_form():
    draft_id = request.args.get("draft_id", type=int) or request.form.get("draft_id", type=int)

    if request.method == "POST":
        action = request.form.get("action")
        dep_date = parse_date_or_none(request.form.get("dep_date"))
        ret_date = parse_date_or_none(request.form.get("ret_date"))

        if draft_id:
            record = VehicleRequestForm.query.get(draft_id)
            if not record or record.email != current_user.email:
                return "❌ Unauthorized draft", 403
        else:
            record = VehicleRequestForm(email=current_user.email)

        record.name = request.form.get("name", "")
        record.phone = request.form.get("phone", "")
        record.vehicle = request.form.get("vehicle", "")
        record.dep_date = dep_date
        record.ret_date = ret_date
        record.start_mileage = request.form.get("start_mileage", "")
        record.end_mileage = request.form.get("end_mileage", "")
        record.destination = request.form.get("destination", "")
        record.purpose = request.form.get("purpose", "")
        record.project = request.form.get("project", "")
        record.comments = request.form.get("comments", "")
        record.submitted_time = datetime.now().strftime("%m-%d-%Y")
        record.admin_comment = ""
        record.status = "draft" if action == "save" else "submitted"

        db.session.add(record)
        db.session.commit()

        if action != "save":
            try:
                audit_vehicle_mileage_and_alert(record.id)
            except Exception as e:
                # Never block submission
                print("[MileageAudit] Audit failed:", repr(e))

        if action == "save":
            return redirect(url_for("user.user_my_forms"))
        return redirect(url_for("user.form_submitted"))

    # GET
    record = None
    if draft_id:
        record = VehicleRequestForm.query.get(draft_id)
        if not record or record.email != current_user.email:
            return "❌ Unauthorized draft", 403

    last = (
        VehicleRequestForm.query
        .filter_by(status="submitted")
        .order_by(VehicleRequestForm.id.desc())
        .first()
    )
    last_end_mileage = last.end_mileage if last else ""
    return render_template(
        "form.html",
        last_end_mileage=last_end_mileage,
        user_email=current_user.email,
        record=record,
    )


@bp.route("/delete_and_new")
@login_required
def delete_and_new():
    return redirect(url_for("user.vehicle_form"))


@bp.route("/form_submitted")
@login_required
def form_submitted():
    return render_template("form_submitted.html")


@bp.route("/download_excel")
def download_excel():
    # Admin only (same behavior as your admin portal design)
    if not session.get("logged_in"):
        return "❌ Admin only", 403

    records = VehicleRequestForm.query.all()
    df = pd.DataFrame([r.__dict__ for r in records])
    if not df.empty:
        df = df.drop(columns=["_sa_instance_state"])

    column_order = [
        "id",
        "name",
        "phone",
        "email",
        "vehicle",
        "dep_date",
        "ret_date",
        "start_mileage",
        "end_mileage",
        "destination",
        "purpose",
        "project",
        "comments",
        "submitted_time",
        "status",
    ]
    df = df[[col for col in column_order if col in df.columns]]

    df = df.rename(
        columns={
            "name": "Name",
            "phone": "Phone #",
            "email": "E-Mail",
            "vehicle": "Vehicle",
            "dep_date": "Departure Date",
            "ret_date": "Return Date",
            "start_mileage": "Start Mileage",
            "end_mileage": "End Mileage",
            "destination": "Destination",
            "purpose": "Purpose",
            "project": "Project",
            "comments": "Comments",
            "status": "Status",
            "submitted_time": "Submitted Time",
        }
    )

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Vehicle_Requests")
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="vehicle_request_form.xlsx",
    )
