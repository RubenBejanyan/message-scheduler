from fastapi import APIRouter, Depends, HTTPException, status

from ..models import ScheduledTask
from ..scheduler import (
    cancel_task,
    fire_task_now,
    get_next_run_time,
    get_task,
    get_task_history,
    list_all_active_tasks,
    pause_task,
    resume_task,
)
from .deps import require_api_key
from .schemas import ScheduleOut, SentMessageOut

router = APIRouter(
    prefix="/api/schedules",
    tags=["schedules"],
    dependencies=[Depends(require_api_key)],
)


def _enrich(task: ScheduledTask) -> ScheduleOut:
    return ScheduleOut.model_validate(task).model_copy(
        update={"next_run_at": get_next_run_time(task.job_id)}
    )


@router.get("", response_model=list[ScheduleOut])
async def list_schedules() -> list[ScheduleOut]:
    return [_enrich(t) for t in await list_all_active_tasks()]


@router.get("/{task_id}", response_model=ScheduleOut)
async def get_schedule(task_id: int) -> ScheduleOut:
    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return _enrich(task)


@router.delete("/{task_id}")
async def cancel_schedule(task_id: int) -> dict[str, bool]:
    if not await cancel_task(task_id, 0, force=True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return {"ok": True}


@router.post("/{task_id}/pause")
async def pause_schedule(task_id: int) -> dict[str, bool]:
    if not await pause_task(task_id, 0, force=True):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found or already paused",
        )
    return {"ok": True}


@router.post("/{task_id}/resume")
async def resume_schedule(task_id: int) -> dict[str, bool]:
    if not await resume_task(task_id, 0, force=True):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found or not paused",
        )
    return {"ok": True}


@router.post("/{task_id}/fire")
async def fire_schedule(task_id: int) -> dict[str, str]:
    try:
        text = await fire_task_now(task_id)
        return {"text": text}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/{task_id}/history", response_model=list[SentMessageOut])
async def schedule_history(task_id: int) -> list[SentMessageOut]:
    entries = await get_task_history(task_id, limit=20)
    return [SentMessageOut.model_validate(e) for e in entries]
