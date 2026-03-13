from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from . import db
from .models import AdminAccount
import os

bp = Blueprint("auth", __name__)

def _ensure_second_admin():
    username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME_2")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD_2")

    if not username or not password:
        return

    acc = AdminAccount.query.filter_by(username=username).first()
    if acc is None:
        acc = AdminAccount(
            username=username,
            password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
        )
        db.session.add(acc)
        db.session.commit()

        
@bp.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        _ensure_second_admin()

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        admin_acc = AdminAccount.query.filter_by(username=username).first()

        if admin_acc is None:
            user = os.environ.get("ADMIN_BOOTSTRAP_USERNAME")
            pwd = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
            user2 = os.environ.get("ADMIN_BOOTSTRAP_USERNAME_2")
            pwd2 = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD_2")
            error = f"Invalid username {username}; account does not exist; \
                keys: {os.environ.keys()}"
            
        elif check_password_hash(admin_acc.password_hash, password):
            session["logged_in"] = True
            session["admin_username"] = username
            return redirect("/admin/")
        else:
            error = f"Invalid password for username {username}"

    return render_template("admin_login.html", error=error)

# @bp.route("/admin_login", methods=["GET", "POST"])
# def admin_login():
#     error = None

#     if request.method == "POST":
#         username = (request.form.get("username") or "").strip()
#         password = request.form.get("password") or ""

#         admin_acc = AdminAccount.query.filter_by(username=username).first()
#         if admin_acc and check_password_hash(admin_acc.password_hash, password):
#             session["logged_in"] = True
#             session["admin_username"] = username
#             return redirect("/admin/")

#         error = f"Invalid admin username {username} or password {password}."

#     return render_template("admin_login.html", error=error)


@bp.route("/admin_reset_password", methods=["GET", "POST"])
def admin_reset_password():
    error = None
    success = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        current_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""

        admin_acc = AdminAccount.query.filter_by(username=username).first()

        if not admin_acc or not check_password_hash(admin_acc.password_hash, current_pw):
            error = "Current password is incorrect."
        elif new_pw != confirm_pw:
            error = "New passwords do not match."
        else:
            admin_acc.password_hash = generate_password_hash(new_pw, method="pbkdf2:sha256")
            db.session.commit()
            success = "Password updated successfully. You can now log in with the new password."

    return render_template("admin_reset_password.html", error=error, success=success)


@bp.route("/logout_admin")
def logout_admin():
    session.clear()
    # return redirect(url_for("auth.admin_login"))
    return redirect(url_for("user.home"))
