from flask import Blueprint, render_template, current_app
from app.auth import login_required
from app.services.zone_service import ZoneService

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    zs = ZoneService(current_app.config)
    zones = zs.list_zones()
    forward = [z for z in zones if z["type"] == "forward"]
    reverse = [z for z in zones if z["type"] == "reverse"]
    total_records = 0
    for z in zones:
        try:
            records = zs.list_records(z["name"])
            total_records += len(records)
        except Exception:
            pass
    return render_template(
        "dashboard.html",
        zones=zones,
        forward_zones=forward,
        reverse_zones=reverse,
        total_records=total_records,
    )
