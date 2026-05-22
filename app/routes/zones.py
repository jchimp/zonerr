from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app,
)
from app.auth import login_required
from app.services.zone_service import ZoneService
from app.services.bind_service import BindService

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
            bs.reload()
            flash(f"Zone '{zone_name}' created successfully.", "success")
            return redirect(url_for("zones.view_zone", zone_name=zone_name))
        except Exception as e:
            flash(f"Error creating zone: {e}", "danger")

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
    return render_template("zones/view.html", zone=zone_meta, records=records)


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
        except Exception as e:
            flash(f"Error updating zone: {e}", "danger")

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
    except Exception as e:
        flash(f"Error deleting zone: {e}", "danger")
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
        except Exception as e:
            flash(f"Error saving zone: {e}", "danger")
            return render_template(
                "zones/raw_edit.html", zone=zone_meta, raw_content=raw_content
            )

    raw_content = zs.read_raw_zone(zone_name)
    return render_template("zones/raw_edit.html", zone=zone_meta, raw_content=raw_content)