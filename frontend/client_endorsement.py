"""Python equivalent of client_endorsement.php."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, session, url_for

from python_app.ats.db import Database


client_endorsement_py_bp = Blueprint("legacy_client_endorsement_py", __name__)


def _resolve_pk(cursor) -> str:
    try:
        cursor.execute("DESCRIBE applicants")
        cols = [str(row[0]) for row in cursor.fetchall()]
    except Exception:
        cols = []

    if "id" in cols:
        return "id"
    if "applicant_number" in cols:
        return "applicant_number"
    return cols[0] if cols else "id"


@client_endorsement_py_bp.route("/client_endorsement.py", methods=["GET"])
def client_endorsement_py():
    if "admin_id" not in session:
        return redirect(url_for("auth.login"))

    rows: list[dict] = []
    db_error = ""

    conn = Database.get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            pk = _resolve_pk(cursor)
            cursor.execute(
                """
                SELECT *
                FROM applicants
                WHERE (LOWER(status) LIKE '%endor%' OR LOWER(status) LIKE '%client%')
                ORDER BY created_at DESC
                LIMIT 1000
                """
            )
            apps = cursor.fetchall() or []

            for app in apps:
                aid = app.get(pk) or app.get("applicant_number")
                aid_str = str(aid or "")

                schedule_data = None
                has_schedule = False
                try:
                    cursor.execute(
                        "SELECT scheduled_at, meeting_link FROM applicant_schedules WHERE applicant_identifier = %s LIMIT 1",
                        (aid_str,),
                    )
                    schedule_data = cursor.fetchone()
                    has_schedule = bool(schedule_data and schedule_data.get("scheduled_at"))
                except Exception:
                    schedule_data = None

                eval_score = None
                has_eval = False
                try:
                    cursor.execute(
                        "SELECT total_score FROM client_evaluations WHERE applicant_identifier = %s LIMIT 1",
                        (aid_str,),
                    )
                    eval_row = cursor.fetchone()
                    if eval_row:
                        has_eval = True
                        eval_score = eval_row.get("total_score")
                except Exception:
                    pass

                rows.append(
                    {
                        "aid": aid_str,
                        "name": f"{(app.get('first_name') or '').strip()} {(app.get('last_name') or '').strip()}".strip(),
                        "email": app.get("email") or "",
                        "status": app.get("status") or "Client Endorsement",
                        "created_at": app.get("created_at"),
                        "has_schedule": has_schedule,
                        "schedule_data": schedule_data,
                        "has_eval": has_eval,
                        "eval_score": eval_score,
                    }
                )
    except Exception as exc:
        db_error = str(exc)
    finally:
        conn.close()

    return render_template("client_endorsement.html", rows=rows, db_error=db_error)
