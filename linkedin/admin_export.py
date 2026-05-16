# linkedin/admin_export.py
"""Reusable 'Export selected to Excel' admin action.

Usage on a ModelAdmin:

    actions = [export_xlsx_action(
        filename="deals",
        columns=[
            ("Lead", "lead.public_identifier"),
            ("LinkedIn URL", "lead.linkedin_url"),
            ("Source", "source"),
            ...
        ],
    )]

Each ``columns`` entry is ``(header, attr_path)``. ``attr_path`` is a
dotted Python path resolved on each row (e.g. ``lead.public_identifier``
calls ``obj.lead.public_identifier``). JSON/list/dict values are
serialized; datetimes are ISO-8601; everything else is str()-coerced.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Iterable

import openpyxl
from django.http import HttpResponse


def _resolve(obj: Any, path: str) -> Any:
    """Walk a dotted attribute path. Returns None on any None segment."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def _cell_value(val: Any) -> Any:
    """Coerce a Python value into something openpyxl can write directly."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (_dt.datetime, _dt.date)):
        # Strip tzinfo — openpyxl rejects timezone-aware datetimes by default.
        return val.replace(tzinfo=None) if isinstance(val, _dt.datetime) else val
    if isinstance(val, (list, dict)):
        return json.dumps(val, default=str)
    return str(val)


def export_xlsx_action(*, filename: str, columns: Iterable[tuple[str, str]]):
    """Return a Django admin action that exports the selected queryset to .xlsx.

    ``filename`` is the basename without extension. ``columns`` is an
    iterable of ``(header, attr_path)`` tuples — the same order is used in
    the spreadsheet.
    """
    cols = list(columns)
    headers = [h for h, _ in cols]
    paths = [p for _, p in cols]

    def action(modeladmin, request, queryset):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = filename[:31] or "export"

        ws.append(headers)
        for obj in queryset:
            ws.append([_cell_value(_resolve(obj, p)) for p in paths])

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        wb.save(response)
        return response

    action.short_description = "Export selected to Excel (.xlsx)"
    action.__name__ = f"export_{filename}_xlsx"
    return action
