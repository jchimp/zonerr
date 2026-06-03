from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint, request, redirect, url_for, render_template,
    session, flash, current_app,
)
from werkzeug.security import check_password_hash


def _is_safe_redirect(url: str) -> bool:
    """Return True only if the URL is relative or points to the same host."""
    parsed = urlparse(url)
    return not parsed.netloc or parsed.netloc == request.host

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
            next_url = request.args.get("next", "")
            if not next_url or not _is_safe_redirect(next_url):
                next_url = url_for("main.dashboard")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))