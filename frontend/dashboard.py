"""Python equivalent of dashboard.php."""

from flask import Blueprint, redirect, render_template, session, url_for

from python_app.ats.db import Database
from python_app.ats.repositories.dashboard_repository import DashboardRepository
from python_app.ats.services.dashboard_service import DashboardService


dashboard_py_bp = Blueprint("legacy_dashboard_py", __name__)
_dashboard_service = DashboardService(DashboardRepository(Database))


@dashboard_py_bp.route("/dashboard.py", methods=["GET"])
def dashboard_py():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    try:
        counts = _dashboard_service.get_dashboard_data()
        db_error = ""
    except Exception as exc:
        counts = {"new": 0, "initial": 0, "demo": 0, "endorsement": 0, "onboarding": 0}
        db_error = str(exc)

    return render_template("dashboard.html", counts=counts, db_error=db_error)
