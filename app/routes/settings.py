import json
import os
import io
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, send_file,
)
from app.auth import login_required
from app.services.bind_service import BindService

settings_bp = Blueprint("settings", __name__)


def _load_replication_config(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"role": "standalone", "allow_transfer": [], "also_notify": [], "masters": []}


def _save_replication_config(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


@settings_bp.route("/replication", methods=["GET", "POST"])
@login_required
def replication():
    config_path = current_app.config["REPLICATION_CONFIG"]
    bs = BindService(current_app.config)
    config = _load_replication_config(config_path)

    if request.method == "POST":
        role = request.form.get("role", "standalone")
        allow_transfer = [
            ip.strip() for ip in request.form.get("allow_transfer", "").split("\n") if ip.strip()
        ]
        also_notify = [
            ip.strip() for ip in request.form.get("also_notify", "").split("\n") if ip.strip()
        ]
        masters = [
            ip.strip() for ip in request.form.get("masters", "").split("\n") if ip.strip()
        ]

        config = {
            "role": role,
            "allow_transfer": allow_transfer,
            "also_notify": also_notify,
            "masters": masters,
        }
        _save_replication_config(config_path, config)

        try:
            bs.apply_replication_config(config)
            bs.reload()
            flash("Replication settings saved and applied.", "success")
        except Exception as e:
            flash(f"Error applying replication settings: {e}", "danger")

        return redirect(url_for("settings.replication"))

    return render_template("settings/replication.html", config=config)


@settings_bp.route("/status")
@login_required
def status():
    bs = BindService(current_app.config)
    rndc_status = bs.get_status()
    return render_template("settings/status.html", status=rndc_status)


@settings_bp.route("/logs")
@settings_bp.route("/logs/<log_name>")
@login_required
def logs(log_name=None):
    bs = BindService(current_app.config)
    log_files = bs.get_log_files()

    tail = request.args.get("tail", 200, type=int)
    full = request.args.get("full", False, type=bool)

    content = ""
    active_log = log_name

    if not active_log and log_files:
        active_log = log_files[0]["name"]

    if active_log:
        if full:
            content = bs.read_log(active_log, tail=0)
        else:
            content = bs.read_log(active_log, tail=tail)

    return render_template(
        "settings/logs.html",
        log_files=log_files,
        active_log=active_log,
        content=content,
        tail=tail,
        full=full,
    )


@settings_bp.route("/bind-action", methods=["POST"])
@login_required
def bind_action():
    bs = BindService(current_app.config)
    action = request.form.get("action", "")

    actions = {
        "reload": ("Reload", bs.reload),
        "reconfig": ("Reconfig", bs.reconfig),
        "flush": ("Flush Cache", bs.flush),
        "restart": ("Restart", bs.stop),
    }

    if action not in actions:
        flash(f"Unknown action: {action}", "danger")
        return redirect(url_for("settings.status"))

    label, func = actions[action]
    ok, msg = func()

    if action == "restart":
        # rndc stop returns success when BIND shuts down — Docker restarts it
        flash(
            f"BIND is restarting... the status below may be stale for a few seconds. "
            f"Hit Refresh in 3–5 seconds.",
            "warning",
        )
    elif ok:
        flash(f"{label} successful.", "success")
    else:
        flash(f"{label} failed: {msg}", "danger")

    return redirect(url_for("settings.status"))


@settings_bp.route("/logs/export/<log_name>")
@login_required
def export_log(log_name):
    bs = BindService(current_app.config)
    content = bs.read_log(log_name, tail=0)

    buf = io.BytesIO()
    buf.write(content.encode("utf-8"))
    buf.seek(0)

    safe_name = os.path.basename(log_name)
    return send_file(
        buf,
        mimetype="text/plain",
        as_attachment=True,
        download_name=safe_name,
    )


@settings_bp.route("/config/<config_name>", methods=["GET", "POST"])
@login_required
def config_edit(config_name):
    bs = BindService(current_app.config)
    configs = bs.get_config_paths()

    if config_name not in configs:
        flash(f"Unknown config file: {config_name}", "danger")
        return redirect(url_for("settings.status"))

    filepath = configs[config_name]

    if request.method == "POST":
        raw_content = request.form.get("raw_content", "")
        try:
            bs.write_config_file(filepath, raw_content)
            ok, msg = bs.reload()
            if ok:
                flash(f"{config_name} saved and BIND reloaded.", "success")
            else:
                flash(f"{config_name} saved but reload failed: {msg}", "warning")
            return redirect(url_for("settings.config_edit", config_name=config_name))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "settings/config_edit.html",
                config_name=config_name,
                raw_content=raw_content,
                configs=configs,
            )
        except Exception as e:
            flash(f"Error saving {config_name}: {e}", "danger")
            return render_template(
                "settings/config_edit.html",
                config_name=config_name,
                raw_content=raw_content,
                configs=configs,
            )

    raw_content = bs.read_config_file(filepath)
    return render_template(
        "settings/config_edit.html",
        config_name=config_name,
        raw_content=raw_content,
        configs=configs,
    )
