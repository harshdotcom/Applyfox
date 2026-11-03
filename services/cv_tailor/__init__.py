"""
services.cv_tailor - Applyfox CV Customization Engine and Job Application Tracker.
"""

from services.cv_tailor.tailor_engine import tailor_cv, analyze_jd
from services.cv_tailor.tracker import (
    record_application,
    list_applications,
    get_application,
    update_application_status
)
from services.cv_tailor.html_preview import render_resume_to_html
from services.cv_tailor.web_app import run_server

__all__ = [
    "tailor_cv",
    "analyze_jd",
    "record_application",
    "list_applications",
    "get_application",
    "update_application_status",
    "render_resume_to_html",
    "run_server"
]

