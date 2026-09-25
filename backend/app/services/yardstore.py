"""堆存记录业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

from app.services.storage import storage_service
from app.store import store

MODULE = "yardstore"
REQUIRED_FIELDS = ["堆存单号", "关联箱号", "箱区编号"]
EDITABLE_FIELDS = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束"]
STATUS_ORDER = ["待进场", "堆存中", "待提离", "已提离"]
ACTION_RULES = {"确认进场": "堆存中", "确认提离": "已提离", "撤销堆存": "待进场"}
NEGATIVE_ACTIONS = ["撤销堆存"]


class YardstoreService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("堆存单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        self._normalize_dates(entry)
        rows.append(entry)
        storage_service.sync_open_entries()
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"

        merged = {field: entry.get(field, "") for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                merged[field] = values.get(field)
        for field in REQUIRED_FIELDS:
            if not str(merged.get(field) or "").strip():
                return None, f"缺少必填字段：{field}"

        entry.update({field: str(merged.get(field) or "").strip() for field in EDITABLE_FIELDS})
        start, end, message = self._date_range(entry.get("堆存开始"), entry.get("堆存结束"))
        if message:
            return None, message
        entry["堆存开始"] = start.isoformat()
        entry["堆存结束"] = end.isoformat()
        entry["堆存天数"] = (end - start).days + 1
        entry["堆存状态"] = entry.get("status") or STATUS_ORDER[0]
        storage_service.sync_open_entries()
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"堆存单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["堆存状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        self._normalize_dates(entry)
        storage_service.sync_open_entries()
        return entry, f"堆存单已{action}"

    def _normalize_dates(self, entry: dict[str, Any]) -> None:
        start, end, message = self._date_range(entry.get("堆存开始"), entry.get("堆存结束"))
        if message:
            return
        entry["堆存开始"] = start.isoformat()
        entry["堆存结束"] = end.isoformat()
        entry["堆存天数"] = (end - start).days + 1

    @staticmethod
    def _date_range(start_value: Any, end_value: Any) -> tuple[date | None, date | None, str]:
        starts = YardstoreService._parse_dates(str(start_value or ""))
        if not starts:
            return None, None, "堆存开始日期无效"
        start = starts[0]
        ends = YardstoreService._parse_dates(str(end_value or ""))
        end = ends[0] if ends else start
        if start > end:
            return None, None, "堆存开始日期不能晚于结束日期"
        return start, end, ""

    @staticmethod
    def _parse_dates(value: str) -> list[date]:
        dates: list[date] = []
        pattern = re.compile(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
        for match in pattern.finditer(value):
            year, month, day = (int(part) for part in match.groups())
            try:
                parsed = date(year, month, day)
            except ValueError:
                continue
            if parsed not in dates:
                dates.append(parsed)
        return dates
