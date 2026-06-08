"""Python equivalent of logout.php.

This module mirrors the old logout.php behavior.
"""

from flask import Blueprint, redirect, session, url_for


logout_bp = Blueprint("legacy_logout_py", __name__)


@logout_bp.route("/logout.py", methods=["GET"])
def logout_py():
    session.clear()
    return redirect(url_for("auth.login"))
