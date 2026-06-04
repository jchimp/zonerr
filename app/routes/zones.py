import io
import logging

import dns.exception

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, send_file,
)

from app.auth import login_required
from app.services.zone_service import ZoneService
from app.services.bind_service import BindService
from app.services.stats_service import StatsService

logger = logging.getLogger(__name__)

zones_bp = Blueprint("zones", __name__)


@zones_bp.route("/")
@login_required
def list_zones():
    zs = ZoneService(current_app.config)
    zones = zs.list_zones()
    return render_template("zones/list.html", zones=zones)


@zones_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_zone():
    if request.method == "POST":
        zone_name = request.form.get("zone_name", "").strip().rstrip(".")
        zone_type = request.form.get("zone_type", "forward")
        soa_ns = request.form.get("soa_ns", "ns1." + zone_name).strip().rstrip(".")
        soa_email = request.form.get("soa_email", "admin." + zone_name).strip().rstrip(".")
        default_ttl = request.form.get("default_ttl", "86400").strip()
        ns_ip = request.form.get("ns_ip", "").strip()

        if not zone_name:
            flash("Zone name is required.", "danger")
            return render_template("zones/create.html")

        zs = ZoneService(current_app.config)
        bs = BindService(current_app.config)

        try:
            zs.create_zone(zone_name, zone_type, soa_ns, soa_email, int(default_ttl), ns_ip)
            bs.add_zone_to_config(zone_name, zone_type)
        except ValueError as e:
            # Validation error before or during write — nothing to clean up
            flash(str(e), "danger")
            return render_template("zones/create.html")
        except Exception:
            # Write failed — roll back whatever was committed, then re-sync BIND
            logger.exception("Error writing zone '%s' — rolling back", zone_name)
            try:
                zs.delete_zone(zone_name)
            except Exception:
                pass
            try:
                bs.remove_zone_from_config(zone_name)
            except Exception:
                pass
            bs.reload()  # best-effort re-sync after cleanup
            flash("An unexpected error occurred while creating the zone.", "danger")
            return render_template("zones/create.html")

        # Zone is on disk and in named.conf.local — now tell BIND about it.
        # A reload failure doesn't undo a valid zone; user can reload manually.
        ok, msg = bs.reload()
        if ok:
            flash(f"Zone '{zone_name}' created successfully.", "success")
        else:
            logger.warning("Zone '%s' created but rndc reload failed: %s", zone_name, msg)
            flash(
                f"Zone '{zone_name}' created but BIND reload failed: {msg} — "
                f"use BIND Status → Reload to activate it.",
                "warning",
            )
        return redirect(url_for("zones.view_zone", zone_name=zone_name))

    return render_template("zones/create.html")


@zones_bp.route("/<zone_name>")
@login_required
def view_zone(zone_name):
    zs = ZoneService(current_app.config)
    try:
        zone_meta = zs.get_zone_meta(zone_name)
        records = zs.list_records(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))
    except Exception:
        logger.exception("Error parsing zone '%s'", zone_name)
        flash("Zone file could not be parsed. Check the server logs.", "danger")
        try:
            zone_meta = zs.get_zone_meta(zone_name)
        except Exception:
            return redirect(url_for("zones.list_zones"))
        return render_template("zones/view.html", zone=zone_meta, records=[], zone_stats=None)

    ss = StatsService(current_app.config)
    zone_stats = ss.get_zone_stats(zone_name)

    return render_template(
        "zones/view.html",
        zone=zone_meta,
        records=records,
        zone_stats=zone_stats,
    )


@zones_bp.route("/<zone_name>/edit", methods=["GET", "POST"])
@login_required
def edit_zone(zone_name):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    try:
        zone_meta = zs.get_zone_meta(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))

    if request.method == "POST":
        default_ttl = int(request.form.get("default_ttl", 86400))
        soa_ns = request.form.get("soa_ns", "").strip().rstrip(".")
        soa_email = request.form.get("soa_email", "").strip().rstrip(".")
        try:
            zs.update_zone_soa(zone_name, soa_ns, soa_email, default_ttl)
            bs.reload()
            flash(f"Zone '{zone_name}' updated.", "success")
            return redirect(url_for("zones.view_zone", zone_name=zone_name))
        except ValueError as e:
            flash(str(e), "danger")
        except Exception:
            logger.exception("Unexpected error updating zone '%s'", zone_name)
            flash("An unexpected error occurred while updating the zone.", "danger")

    return render_template("zones/edit.html", zone=zone_meta)


@zones_bp.route("/<zone_name>/delete", methods=["POST"])
@login_required
def delete_zone(zone_name):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)
    try:
        zs.delete_zone(zone_name)
        bs.remove_zone_from_config(zone_name)
        bs.reload()
        flash(f"Zone '{zone_name}' deleted.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception:
        logger.exception("Unexpected error deleting zone '%s'", zone_name)
        flash("An unexpected error occurred while deleting the zone.", "danger")
    return redirect(url_for("zones.list_zones"))


@zones_bp.route("/<zone_name>/raw", methods=["GET", "POST"])
@login_required
def raw_edit(zone_name):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    try:
        zone_meta = zs.get_zone_meta(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))

    if request.method == "POST":
        raw_content = request.form.get("raw_content", "")
        try:
            zs.write_raw_zone(zone_name, raw_content)
            bs.reload()
            flash(f"Zone '{zone_name}' updated from raw edit.", "success")
            return redirect(url_for("zones.view_zone", zone_name=zone_name))
        except ValueError as e:
            flash(f"Validation error: {e}", "danger")
            return render_template(
                "zones/raw_edit.html", zone=zone_meta, raw_content=raw_content
            )
        except Exception:
            logger.exception("Unexpected error saving raw zone '%s'", zone_name)
            flash("An unexpected error occurred while saving the zone.", "danger")
            return render_template(
                "zones/raw_edit.html", zone=zone_meta, raw_content=raw_content
            )

    raw_content = zs.read_raw_zone(zone_name)
    return render_template("zones/raw_edit.html", zone=zone_meta, raw_content=raw_content)


@zones_bp.route("/<zone_name>/export")
@login_required
def export_zone(zone_name):
    zs = ZoneService(current_app.config)

    try:
        raw = zs.read_raw_zone(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))

    buf = io.BytesIO()
    buf.write(raw.encode("utf-8"))
    buf.seek(0)

    filename = "db." + zone_name + ".txt"
    return send_file(
        buf,
        mimetype="text/plain",
        as_attachment=True,
        download_name=filename,
    )


@zones_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_zone():
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    if request.method == "POST":
        zone_name = request.form.get("zone_name", "").strip().rstrip(".")
        zone_type = request.form.get("zone_type", "forward")

        if not zone_name:
            flash("Zone name is required.", "danger")
            return render_template("zones/import.html")

        # Get content: prefer file upload, fall back to paste
        content = ""
        uploaded = request.files.get("zone_file")
        if uploaded and uploaded.filename:
            content = uploaded.read().decode("utf-8", errors="replace")
        else:
            content = request.form.get("paste_content", "")

        if not content.strip():
            flash("No zone content provided. Upload a file or paste the zone data.", "danger")
            return render_template(
                "zones/import.html",
                zone_name=zone_name,
                zone_type=zone_type,
            )

        # Normalize line endings (Windows paste sends \r\n)
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        try:
            zs.import_zone(zone_name, zone_type, content)
            bs.add_zone_to_config(zone_name, zone_type)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "zones/import.html",
                zone_name=zone_name,
                zone_type=zone_type,
                paste_content=content,
            )
        except Exception:
            logger.exception("Error writing zone '%s' — rolling back", zone_name)
            try:
                zs.delete_zone(zone_name)
            except Exception:
                pass
            try:
                bs.remove_zone_from_config(zone_name)
            except Exception:
                pass
            bs.reload()  # best-effort re-sync after cleanup
            flash("An unexpected error occurred while importing the zone.", "danger")
            return render_template(
                "zones/import.html",
                zone_name=zone_name,
                zone_type=zone_type,
                paste_content=content,
            )

        ok, msg = bs.reload()
        if ok:
            flash(f"Zone '{zone_name}' imported successfully.", "success")
        else:
            logger.warning("Zone '%s' imported but rndc reload failed: %s", zone_name, msg)
            flash(
                f"Zone '{zone_name}' imported but BIND reload failed: {msg} — "
                f"use BIND Status → Reload to activate it.",
                "warning",
            )
        return redirect(url_for("zones.view_zone", zone_name=zone_name))

    return render_template("zones/import.html")