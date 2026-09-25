"""堆存计费业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

from app.store import store

MODULE = "storage"
YARDSTORE_MODULE = "yardstore"
REQUIRED_FIELDS = ["计费单号", "关联箱号", "计费周期"]
EDITABLE_FIELDS = ["计费单号", "关联箱号", "计费周期", "计费标准", "客户名称"]
STATUS_ORDER = ["待核算", "已核算", "已对账", "已开票"]
LOCKED_STATUSES = {"已对账", "已开票", "已结清"}
ACTION_RULES = {"生成账单": "已核算", "确认对账": "已对账", "开具发票": "已开票"}
NEGATIVE_ACTIONS: list[str] = []
DEFAULT_RATE = 10.0


class StorageService:
    def __init__(self) -> None:
        self._consistent = False

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        bill_no: str | None = None,
        container_no: str | None = None,
        period: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.ensure_consistent()
        rows = store.rows(MODULE)
        keyword = (keyword or "").strip()
        bill_no = (bill_no or "").strip()
        container_no = (container_no or "").strip()
        period = (period or "").strip()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("计费单号", ""))]
        if bill_no:
            rows = [row for row in rows if bill_no in str(row.get("计费单号", ""))]
        if container_no:
            rows = [row for row in rows if container_no in str(row.get("关联箱号", ""))]
        if period:
            rows = [row for row in rows if period in str(row.get("计费周期", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status or row.get("计费状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.ensure_consistent()
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        self.ensure_consistent()
        normalized, message = self._payload_values(values)
        if message:
            return None, message

        rows = store.rows(MODULE)
        if self._find_duplicate(normalized["关联箱号"], normalized["计费周期"]):
            return None, "同一箱号在同一计费周期只能存在一张计费单，且计费周期不能重叠"

        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update(normalized)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["计费状态"] = entry["status"]
        self._calculate_entry(entry, exclude_id=entry["id"])
        rows.append(entry)
        return entry, ""

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        self.ensure_consistent()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"计费单 {entry_id} 不存在或已归档"
        if self._is_locked(entry):
            return None, "计费单已结清/对账，不允许再修改"

        merged = {field: entry.get(field) for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                merged[field] = values.get(field)

        normalized, message = self._payload_values(merged)
        if message:
            return None, message
        duplicate = self._find_duplicate(normalized["关联箱号"], normalized["计费周期"], exclude_id=entry_id)
        if duplicate:
            return None, "同一箱号在同一计费周期只能存在一张计费单，且计费周期不能重叠"

        entry.update(normalized)
        self._calculate_entry(entry, exclude_id=entry_id)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        self.ensure_consistent()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"计费单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于堆存计费可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        current_index = STATUS_ORDER.index(str(entry.get("status") or STATUS_ORDER[0]))
        target_index = STATUS_ORDER.index(target)
        if target_index <= current_index:
            return None, "计费单状态只能向前流转，已结清的计费单不能再改"

        if target in LOCKED_STATUSES:
            self._calculate_entry(entry, exclude_id=entry_id)
        entry["status"] = target
        entry["计费状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"计费单已{action}"

    def ensure_consistent(self) -> None:
        """合并同箱号同周期的重复单，并重算未结清账单，列表和导出共用此口径。"""
        if self._consistent:
            return
        rows = store.rows(MODULE)
        unique_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            container = str(row.get("关联箱号") or "").strip()
            period = str(row.get("计费周期") or "").strip()
            start, end, period_error = self._period_range(period)
            key = (container, self._period_key(start, end) if start and end and not period_error else period)
            if key not in unique_rows:
                unique_rows[key] = row

        deduped = list(unique_rows.values())
        rows[:] = deduped
        for row in rows:
            status = str(row.get("status") or row.get("计费状态") or STATUS_ORDER[0]).strip()
            if status not in STATUS_ORDER:
                status = STATUS_ORDER[0]
            row["status"] = status
            row["计费状态"] = status
            row.setdefault("计费标准", self._format_rate(DEFAULT_RATE))
            row.setdefault("客户名称", "")
            if not self._is_locked(row):
                self._calculate_entry(row, exclude_id=int(row.get("id", 0)))
        self._consistent = True

    def sync_open_entries(self) -> None:
        """堆存记录变化后，只重算仍未结清的计费单；已结清金额保持快照不变。"""
        for row in store.rows(MODULE):
            if not self._is_locked(row):
                self._calculate_entry(row, exclude_id=int(row.get("id", 0)))

    def _payload_values(self, values: dict[str, Any]) -> tuple[dict[str, str], str]:
        result: dict[str, str] = {}
        for field in REQUIRED_FIELDS:
            value = str(values.get(field) or "").strip()
            if not value:
                return {}, f"缺少必填字段：{field}"
            result[field] = value

        start, end, period_error = self._period_range(result["计费周期"])
        if period_error or start is None or end is None:
            return {}, "计费周期需包含两个有效日期，例如：2026-09-01 至 2026-09-10"
        result["计费周期"] = f"{start.isoformat()} 至 {end.isoformat()}"
        result["计费标准"] = str(values.get("计费标准") or self._format_rate(DEFAULT_RATE)).strip()
        result["客户名称"] = str(values.get("客户名称") or "").strip()
        return result, ""

    def _calculate_entry(self, entry: dict[str, Any], exclude_id: int | None = None) -> None:
        container = str(entry.get("关联箱号") or "").strip()
        start, end, period_error = self._period_range(str(entry.get("计费周期") or ""))
        if period_error or start is None or end is None:
            entry["堆存天数"] = 0
            entry["应收金额"] = 0
            return

        rate = self._parse_rate(entry.get("计费标准"))
        entry["计费标准"] = self._format_rate(rate)

        billed_days = self._billable_days(container, start, end, exclude_id)
        if billed_days == 0:
            # 允许先建当期账单；尚未关联到堆存记录或自然天数已被较早账单占用时按剩余可计费天数占账。
            allocated = self._allocated_days(container, start, end, exclude_id)
            billed_days = (end - start).days + 1 - len(allocated)

        entry["堆存天数"] = max(billed_days, 0)
        entry["应收金额"] = round(max(billed_days, 0) * rate, 2)
        entry["计费状态"] = entry.get("status") or STATUS_ORDER[0]

    def _billable_days(
        self,
        container_no: str,
        period_start: date,
        period_end: date,
        exclude_id: int | None,
    ) -> int:
        stored = self._stored_days(container_no, period_start, period_end)
        allocated = self._allocated_days(container_no, period_start, period_end, exclude_id)
        return len(stored - allocated)

    def _allocated_days(
        self,
        container_no: str,
        period_start: date,
        period_end: date,
        exclude_id: int | None,
    ) -> set[int]:
        allocated: set[int] = set()
        for bill in store.rows(MODULE):
            if exclude_id is not None and int(bill.get("id", 0)) == exclude_id:
                continue
            if str(bill.get("关联箱号") or "").strip() != container_no:
                continue
            start, end, error = self._period_range(str(bill.get("计费周期") or ""))
            if error or start is None or end is None:
                continue
            start = max(start, period_start)
            end = min(end, period_end)
            if start <= end:
                allocated.update(range(start.toordinal(), end.toordinal() + 1))
        return allocated

    def _stored_days(self, container_no: str, period_start: date, period_end: date) -> set[int]:
        covered: set[int] = set()
        for yard_row in store.rows(YARDSTORE_MODULE):
            if str(yard_row.get("关联箱号") or "").strip() != container_no:
                continue
            start, end, error = self._date_range(
                yard_row.get("堆存开始"),
                yard_row.get("堆存结束"),
            )
            if error or start is None:
                continue
            if end is None:
                end = start
            start = max(start, period_start)
            end = min(end, period_end)
            if start <= end:
                covered.update(range(start.toordinal(), end.toordinal() + 1))
        return covered

    def _find_duplicate(
        self,
        container_no: str,
        period: str,
        *,
        exclude_id: int | None = None,
    ) -> dict[str, Any] | None:
        start, end, error = self._period_range(period)
        if error or start is None or end is None:
            return None
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("关联箱号") or "").strip() != container_no.strip():
                continue
            row_start, row_end, row_error = self._period_range(str(row.get("计费周期") or ""))
            if row_error or row_start is None or row_end is None:
                continue
            if start <= row_end and row_start <= end:
                return row
        return None

    @staticmethod
    def _is_locked(entry: dict[str, Any]) -> bool:
        return str(entry.get("status") or entry.get("计费状态") or "") in LOCKED_STATUSES

    @staticmethod
    def _period_key(start: date, end: date) -> str:
        return f"{start.isoformat()}/{end.isoformat()}"

    @staticmethod
    def _format_rate(rate: float) -> str:
        return f"{rate:g} 元/天"

    @staticmethod
    def _parse_rate(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(float(value), 0.0)
        match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
        return max(float(match.group()), 0.0) if match else DEFAULT_RATE

    @staticmethod
    def _period_range(value: str) -> tuple[date | None, date | None, str]:
        dates = StorageService._parse_dates(value)
        if len(dates) < 2:
            return None, None, "计费周期需包含开始和结束日期"
        start, end = dates[0], dates[-1]
        if start > end:
            return None, None, "计费开始日期不能晚于结束日期"
        return start, end, ""

    @staticmethod
    def _date_range(start_value: Any, end_value: Any) -> tuple[date | None, date | None, str]:
        starts = StorageService._parse_dates(str(start_value or ""))
        if not starts:
            return None, None, "堆存开始日期无效"
        start = starts[0]
        ends = StorageService._parse_dates(str(end_value or ""))
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


storage_service = StorageService()
