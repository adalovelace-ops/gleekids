"""Python equivalent of create_applicant.php.

The PHP file is currently empty, so this routes to the migrated Flask OOP page.
"""

from flask import Blueprint, redirect, url_for


create_applicant_py_bp = Blueprint("legacy_create_applicant_py", __name__)


@create_applicant_py_bp.route("/create_applicant.py", methods=["GET"])
def create_applicant_py():
    return redirect(url_for("applicant_admin.create_applicant"))
