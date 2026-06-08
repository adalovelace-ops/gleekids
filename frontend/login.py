"""Python equivalent of login.php.

This module mirrors the old login.php behavior and can be used as a
standalone Flask blueprint or as reference for migrated logic.
"""

from flask import Blueprint, redirect, render_template, request, session, url_for

from python_app.ats.db import Database
from python_app.ats.repositories.admin_repository import AdminRepository
from python_app.ats.services.auth_service import AuthService


login_bp = Blueprint("legacy_login_py", __name__)
_auth_service = AuthService(AdminRepository(Database))


@login_bp.route("/login.py", methods=["GET", "POST"])
def login_py():
    error = ""
    email = ""
    oauth_error = session.pop("oauth_error", "")

    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        if not email or not password:
            error = "Please provide both email and password."
        else:
            user = _auth_service.authenticate(email=email, password=password)
            if user:
                session["admin_id"] = user.id
                session["admin_email"] = user.email
                session["admin_role"] = user.role
                return redirect(url_for("dashboard.view_dashboard"))
            error = "Invalid email or password."

    return render_template(
        "login.html",
        error=error,
        oauth_error=oauth_error,
        email=email,
    )
