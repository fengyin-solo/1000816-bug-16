"""堆存计费接口：维护计费单，覆盖生成账单、确认对账、开具发票等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.storage import MODULE, storage_service

router = APIRouter(prefix="/api/storage", tags=["堆存计费"])

service = storage_service

LIST_FIELDS = ["计费单号", "关联箱号", "计费周期", "堆存天数", "计费标准", "应收金额", "客户名称", "计费状态"]
STATUSES = ["待核算", "已核算", "已对账", "已开票"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计费单号检索"),
    status: str | None = Query(default=None, description="待核算、已核算、已对账、已开票"),
    计费单号: str | None = Query(default=None),
    关联箱号: str | None = Query(default=None),
    计费周期: str | None = Query(default=None),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按计费单号、箱号、周期与状态过滤堆存计费列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        bill_no=计费单号,
        container_no=关联箱号,
        period=计费周期,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    status: str | None = None,
    计费单号: str | None = None,
    关联箱号: str | None = None,
    计费周期: str | None = None,
) -> dict[str, Any]:
    """导出与列表相同口径、相同过滤条件下的全量计费数据。"""
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        bill_no=计费单号,
        container_no=关联箱号,
        period=计费周期,
        page=1,
        size=10000,
    )
    return {"module": MODULE, "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条计费单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"计费单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条计费单，缺字段或同箱号同周期重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if not entry:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="计费单已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改未结清计费单；金额与堆存天数随后按箱号和计费周期统一重算。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if not entry:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="计费单已更新", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def replace_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """兼容 PUT 编辑入口，规则与 PATCH 完全一致。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if not entry:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="计费单已更新", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条计费单执行生成账单、确认对账、开具发票；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
