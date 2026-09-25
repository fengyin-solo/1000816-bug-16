"""堆存记录业务规则：状态流转、日期与堆存天数维护、筛选口径。

堆存记录是堆存计费的事实源：天数由"堆存开始/堆存结束"两个日期推导
（起讫均计），确认进场写入开始日、确认提离写入结束日；计费单只读取这里的
区间，不再各自维护一份天数。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.billing_rules import parse_loose_date
from app.store import store

MODULE = "yardstore"
REQUIRED_FIELDS = ["堆存单号", "关联箱号", "箱区编号"]
OPTIONAL_FIELDS = ["贝位号", "堆存开始", "堆存结束", "客户名称"]
STATUS_ORDER = ["待进场", "堆存中", "待提离", "已提离"]
ACTION_RULES = {"确认进场": "堆存中", "确认提离": "已提离", "撤销堆存": "待进场"}
NEGATIVE_ACTIONS = ["撤销堆存"]


def _calc_days(start: Any, end: Any) -> int:
    start_date = parse_loose_date(start)
    if start_date is None:
        return 0
    end_date = parse_loose_date(end) or start_date
    if end_date < start_date:
        return 0
    return (end_date - start_date).days + 1


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """统一投影：堆存天数始终由起止日期推导，避免存死值与日期不一致。"""
    view = dict(entry)
    view["堆存天数"] = _calc_days(entry.get("堆存开始"), entry.get("堆存结束"))
    return view


class YardstoreService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_present(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("堆存单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if values.get(field) is not None:
                entry[field] = str(values.get(field)).strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        store.save()
        return _present(entry), []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        values = values or {}
        if action == "确认进场":
            start = str(values.get("堆存开始") or entry.get("堆存开始") or date.today().isoformat())
            if parse_loose_date(start) is None:
                return None, "堆存开始日期格式不正确，请使用 2026-09-01 这样的格式"
            entry["堆存开始"] = start
            entry["堆存结束"] = ""
        elif action == "确认提离":
            if not entry.get("堆存开始"):
                return None, "尚未确认进场，无法确认提离"
            end = str(values.get("堆存结束") or date.today().isoformat())
            end_date = parse_loose_date(end)
            if end_date is None:
                return None, "堆存结束日期格式不正确，请使用 2026-09-01 这样的格式"
            if end_date < parse_loose_date(entry["堆存开始"]):
                return None, "提离日期不能早于进场日期"
            entry["堆存结束"] = end
        elif action == "撤销堆存":
            entry["堆存开始"] = ""
            entry["堆存结束"] = ""

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        store.save()
        return _present(entry), f"堆存单已{action}"
