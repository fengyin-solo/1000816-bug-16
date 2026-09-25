"""堆存记录接口：维护堆存单，覆盖确认进场、确认提离、撤销堆存等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.yardstore import YardstoreService

router = APIRouter(prefix="/api/yardstore", tags=["堆存记录"])

service = YardstoreService()

LIST_FIELDS = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
STATUSES = ["待进场", "堆存中", "待提离", "已提离"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按堆存单号检索"),
    status: str | None = Query(default=None, description="待进场、堆存中、待提离、已提离"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按堆存单号与状态过滤堆存记录列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """导出与列表相同口径、相同过滤条件下的全量堆存记录。"""
    items, total = service.list_entries(keyword=keyword, status=status, page=1, size=10000)
    return {"module": "yardstore", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条堆存单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"堆存单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条堆存单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing_or_message = service.create_entry(payload.values)
    if not entry:
        message = missing_or_message if isinstance(missing_or_message, str) else f"缺少必填字段：{'、'.join(missing_or_message)}"
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="堆存单已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改堆存记录；系统会同步更新堆存天数及未结清计费单。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if not entry:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="堆存单已更新", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def replace_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """兼容 PUT 编辑入口，规则与 PATCH 完全一致。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if not entry:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="堆存单已更新", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条堆存单执行确认进场、确认提离、撤销堆存；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
