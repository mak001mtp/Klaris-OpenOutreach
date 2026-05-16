# linkedin/tasks/scheduler.py
"""Single source of truth for Task row creation.

The daemon's task queue has one task type — QUALIFY. One QUALIFY task
per campaign runs discovery + LLM qualification and self-reschedules.

There is no state-transition hook anymore: once a Deal is QUALIFIED or
FAILED, no downstream task is enqueued.
"""
from __future__ import annotations

import datetime
import logging
from datetime import timedelta

from django.utils import timezone

from linkedin.conf import CAMPAIGN_CONFIG
from linkedin.models import Task

logger = logging.getLogger(__name__)


# ── Low-level enqueue ─────────────────────────────────────────────────


def _insert_task(
    task_type: "Task.TaskType",
    payload: dict,
    delay_seconds: float,
    dedup_keys: list[str] | None = None,
) -> bool:
    """Insert a PENDING Task row, skipping if a duplicate already exists.

    Duplicate = same ``task_type``, status=PENDING, and matching payload on
    ``dedup_keys`` (defaults to all payload keys). Returns True if a row
    was inserted.
    """
    filter_kwargs = {
        "task_type": task_type,
        "status": Task.Status.PENDING,
    }
    for key in (dedup_keys if dedup_keys is not None else payload):
        filter_kwargs[f"payload__{key}"] = payload[key]

    if Task.objects.filter(**filter_kwargs).exists():
        return False

    Task.objects.create(
        task_type=task_type,
        scheduled_at=timezone.now() + timedelta(seconds=delay_seconds),
        payload=payload,
    )
    return True


def enqueue_qualify(campaign_id: int, delay_seconds: float = 10) -> None:
    """Enqueue a qualify task for the given campaign."""
    _insert_task(
        task_type=Task.TaskType.QUALIFY,
        payload={"campaign_id": campaign_id},
        delay_seconds=delay_seconds,
    )


# ── Delay helpers ─────────────────────────────────────────────────────


def seconds_until_tomorrow() -> float:
    """Seconds until 00:00 local time — used for daily rate-limit waits."""
    now = timezone.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return (tomorrow - now).total_seconds()


# ── Reconciliation ────────────────────────────────────────────────────


def _recover_stale_running_tasks() -> int:
    """Reset RUNNING tasks to PENDING. RUNNING rows can only linger if the
    daemon crashed mid-task, so they are always stale at reconcile time."""
    count = Task.objects.filter(status=Task.Status.RUNNING).update(
        status=Task.Status.PENDING,
    )
    if count:
        logger.info("Recovered %d stale running tasks", count)
    return count


def _seed_qualify_tasks(session) -> None:
    """Ensure every campaign has a pending qualify task."""
    for campaign in session.campaigns:
        enqueue_qualify(campaign.pk, delay_seconds=0)


def reconcile(session) -> None:
    """Reconcile the Task queue with CRM state.

    Runs on daemon startup and when the queue drains. Ensures one
    qualify task per campaign and recovers any stale RUNNING rows.
    """
    _recover_stale_running_tasks()
    _seed_qualify_tasks(session)

    pending_count = Task.objects.pending().count()
    logger.info("Task queue reconciled: %d pending tasks", pending_count)
