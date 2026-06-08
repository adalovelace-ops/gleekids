from __future__ import annotations

from flask import render_template


class LegacyRepository:
    def get_page_context(self) -> dict[str, str]:
        return {
            "page_path": "admin_calendar.php",
            "source": "generated-python-oop-stub",
            "zoomCloneUrl": "http://127.0.0.1:3000/",
        }


class LegacyService:
    def __init__(self, repository: LegacyRepository | None = None):
        self.repository = repository or LegacyRepository()

    def build_context(self) -> dict[str, str]:
        return self.repository.get_page_context()


class LegacyController:
    def __init__(self, service: LegacyService | None = None):
        self.service = service or LegacyService()

    def handle(self):
        context = self.service.build_context()
        return render_template("admin_calendar.html", **context)
