from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app,
)
from app.auth import login_required
from app.services.zone_service import ZoneService
from app.services.bind_service import BindService

records_bp = Blueprint("records", __name__)

SUPPORTED_TYPES = ["A", "AAAA", "CNAME", "TXT", "SRV", "MX", "NS", "PTR"]


@records_bp.route("/<zone_name>/add", methods=["GET", "POST"])
@login_required
def add_record(zone_name):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    try:
        zone_meta = zs.get_zone_meta(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))

    reverse_zones = [z["name"] for z in zs.list_zones() if z["type"] == "reverse"]

    if request.method == "POST":
        rtype = request.form.get("rtype", "A").upper()
        name = request.form.get("name", "").strip()
        ttl = int(request.form.get("ttl", 3600))
        value = request.form.get("value", "").strip()
        create_ptr = request.form.get("create_ptr") == "on"

        priority = request.form.get("priority", "0").strip()
        weight = request.form.get("weight", "0").strip()
        port = request.form.get("port", "0").strip()
        mx_priority = request.form.get("mx_priority", "10").strip()

        if not name or not value:
            flash("Name and Value are required.", "danger")
            return render_template(
                "records/add.html", zone=zone_meta,
                record_types=SUPPORTED_TYPES, reverse_zones=reverse_zones,
            )

        try:
            if rtype == "SRV":
                srv_data = f"{priority} {weight} {port} {value}"
                zs.add_record(zone_name, name, ttl, rtype, srv_data)
            elif rtype == "MX":
                mx_data = f"{mx_priority} {value}"
                zs.add_record(zone_name, name, ttl, rtype, mx_data)
            elif rtype == "TXT":
                if not value.startswith('"'):
                    value = f'"{value}"'
                zs.add_record(zone_name, name, ttl, rtype, value)
            else:
                zs.add_record(zone_name, name, ttl, rtype, value)

            if rtype == "A" and create_ptr:
                _handle_auto_ptr(zs, zone_name, name, value, ttl, reverse_zones)

            bs.reload()
            flash(f"{rtype} record added successfully.", "success")
            return redirect(url_for("zones.view_zone", zone_name=zone_name))
        except Exception as e:
            flash(f"Error adding record: {e}", "danger")

    return render_template(
        "records/add.html", zone=zone_meta,
        record_types=SUPPORTED_TYPES, reverse_zones=reverse_zones,
    )


def _handle_auto_ptr(zs, zone_name, hostname, ip, ttl, reverse_zones):
    """Create a matching PTR record in the appropriate reverse zone."""
    parts = ip.split(".")
    if len(parts) != 4:
        flash("Cannot create PTR: invalid IPv4 address.", "warning")
        return

    reverse_zone = f"{parts[2]}.{parts[1]}.{parts[0]}.in-addr.arpa"
    ptr_name = parts[3]

    if hostname.endswith("."):
        fqdn = hostname
    else:
        fqdn = f"{hostname}.{zone_name}."

    if reverse_zone in reverse_zones:
        try:
            zs.add_record(reverse_zone, ptr_name, ttl, "PTR", fqdn)
            flash(f"PTR record created in {reverse_zone}.", "success")
        except Exception as e:
            flash(f"PTR record creation failed: {e}", "warning")
    else:
        flash(
            f"Reverse zone '{reverse_zone}' does not exist. PTR record was NOT created. "
            f"Create the reverse zone first, then add the PTR manually.",
            "warning",
        )


@records_bp.route("/<zone_name>/edit/<int:record_index>", methods=["GET", "POST"])
@login_required
def edit_record(zone_name, record_index):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    try:
        zone_meta = zs.get_zone_meta(zone_name)
        records = zs.list_records(zone_name)
    except FileNotFoundError:
        flash(f"Zone '{zone_name}' not found.", "danger")
        return redirect(url_for("zones.list_zones"))

    if record_index < 0 or record_index >= len(records):
        flash("Record not found.", "danger")
        return redirect(url_for("zones.view_zone", zone_name=zone_name))

    record = records[record_index]

    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        new_ttl = int(request.form.get("ttl", 3600))
        new_value = request.form.get("value", "").strip()
        rtype = record["type"]

        priority = request.form.get("priority", "0").strip()
        weight = request.form.get("weight", "0").strip()
        port = request.form.get("port", "0").strip()
        mx_priority = request.form.get("mx_priority", "10").strip()

        try:
            if rtype == "SRV":
                new_value = f"{priority} {weight} {port} {new_value}"
            elif rtype == "MX":
                new_value = f"{mx_priority} {new_value}"
            elif rtype == "TXT":
                if not new_value.startswith('"'):
                    new_value = f'"{new_value}"'

            zs.update_record(zone_name, record_index, new_name, new_ttl, rtype, new_value)
            bs.reload()
            flash("Record updated.", "success")
            return redirect(url_for("zones.view_zone", zone_name=zone_name))
        except Exception as e:
            flash(f"Error updating record: {e}", "danger")

    return render_template(
        "records/edit.html", zone=zone_meta, record=record,
        record_index=record_index, record_types=SUPPORTED_TYPES,
    )


@records_bp.route("/<zone_name>/delete/<int:record_index>", methods=["POST"])
@login_required
def delete_record(zone_name, record_index):
    zs = ZoneService(current_app.config)
    bs = BindService(current_app.config)

    try:
        zs.delete_record(zone_name, record_index)
        bs.reload()
        flash("Record deleted.", "success")
    except Exception as e:
        flash(f"Error deleting record: {e}", "danger")

    return redirect(url_for("zones.view_zone", zone_name=zone_name))
