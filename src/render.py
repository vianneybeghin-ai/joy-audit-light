"""Render 1-pager HTML avec Jinja2."""
from __future__ import annotations
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .compact_schemas import AuditLightResult

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_html_light(result: AuditLightResult) -> str:
    tpl = _env.get_template("light.html.j2")
    return tpl.render(
        result=result,
        full_audit_base_url=os.getenv("FULL_AUDIT_BASE_URL", ""),
    )
