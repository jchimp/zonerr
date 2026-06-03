from functools import wraps

from flask import (
    Blueprint, request, redirect, url_for, render_template,
    session, flash, current_app,
)
from werkzeug.security import check_password_hash

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        password_hash = current_app.config["ADMIN_PASSWORD_HASH"]
        if (
            username == current_app.config["ADMIN_USERNAME"]
            and password_hash
            and check_password_hash(password_hash, password)
        ):
            session["logged_in"] = True
            session["username"] = username
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next") or url_for("main.dashboard")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))