"""堆存计费接口：维护计费单，覆盖生成账单、确认对账、开具发票等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.storage import StorageService

router = APIRouter(prefix="/api/storage", tags=["堆存计费"])

service = StorageService()

LIST_FIELDS = ["计费单号", "关联箱号", "计费周期", "堆存天数", "计费标准", "应收金额", "客户名称", "计费状态"]
STATUSES = ["待核算", "已核算", "已对账", "已开票"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计费单号检索"),
    status: str | None = Query(default=None, description="待核算、已核算、已对账、已开票"),
    container: str | None = Query(default=None, description="按关联箱号精确检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按计费单号、状态、箱号过滤堆存计费列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, container=container, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按计费单号检索"),
    status: str | None = Query(default=None, description="待核算、已核算、已对账、已开票"),
    container: str | None = Query(default=None, description="按关联箱号精确检索"),
) -> dict[str, Any]:
    """导出对账单：与列表页使用同一套过滤口径与同一份数据投影。"""
    items, total = service.list_entries(
        keyword=keyword, status=status, container=container, page=1, size=10000
    )
    return {"module": "storage", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条计费单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"计费单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条计费单；箱号+周期重复或周期格式不对时说明原因，而不是静默收下。"""
    entry, missing, error = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="计费单已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改计费单（周期、费率等）；结清后的计费单一律拒绝修改。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="计费单已更新，金额与堆存天数已重新核算", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条计费单执行生成账单、确认对账、开具发票；不允许或已结清的动作会被拦下。"""
    action = str(payload.values.get("action") or payload.action or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
