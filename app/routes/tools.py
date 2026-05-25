from flask import (
    Blueprint, render_template, request, current_app,
)
from app.auth import login_required
from app.services.bind_service import BindService

tools_bp = Blueprint("tools", __name__)


@tools_bp.route("/query", methods=["GET", "POST"])
@login_required
def query():
    result = None
    qname = ""
    qtype = "A"
    server = ""
    short_mode = False
    reverse = False

    if request.method == "POST":
        qname = request.form.get("qname", "").strip()
        qtype = request.form.get("qtype", "A")
        server = request.form.get("server", "").strip()
        short_mode = request.form.get("short_mode") == "on"
        reverse = request.form.get("reverse") == "on"

        if qname:
            bs = BindService(current_app.config)
            result = bs.dig_query(
                name=qname,
                qtype=qtype,
                server=server or None,
                short=short_mode,
                reverse=reverse,
            )

            # +short returns empty on NXDOMAIN — re-run without +short to get status
            if short_mode and not result.strip():
                full_result = bs.dig_query(
                    name=qname,
                    qtype=qtype,
                    server=server or None,
                    short=False,
                    reverse=reverse,
                )
                if "NXDOMAIN" in full_result:
                    result = "NXDOMAIN"
                elif "SERVFAIL" in full_result:
                    result = "SERVFAIL"
                elif "REFUSED" in full_result:
                    result = "REFUSED"
                else:
                    result = "(no answer)"

    return render_template(
        "tools/query.html",
        result=result,
        qname=qname,
        qtype=qtype,
        server=server,
        short_mode=short_mode,
        reverse=reverse,
    )
