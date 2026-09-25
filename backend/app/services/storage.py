"""堆存计费业务规则。

与通用 CRUD 模块的区别：
- 同箱号 + 同计费周期全表唯一，重复登记直接拒绝（不再重复扣费、金额翻倍）；
- 堆存天数与应收金额不在建单时写死，而是通过 billing_rules 按箱号、周期、
  堆存记录与费率实时推导，改短周期金额立即联动，列表/详情/导出共用同一份投影；
- 到达终态"已开票"即结清，固化天数与金额快照，之后任何修改与动作一律拒绝；
- 每次写操作后落盘，刷新或重启仍保持最后结果。
"""
from __future__ import annotations

from typing import Any

from app.services import billing_rules as rules
from app.store import store

MODULE = "storage"
YARDSTORE_MODULE = "yardstore"
REQUIRED_FIELDS = ["计费单号", "关联箱号", "计费周期"]
EDITABLE_FIELDS = ["关联箱号", "计费周期", "计费标准", "客户名称"]
STATUS_ORDER = ["待核算", "已核算", "已对账", "已开票"]
# 每个动作只能推进到下一个状态，禁止跨状态跳转或对已结清单再操作。
NEXT_ACTION = {"生成账单": "已核算", "确认对账": "已对账", "开具发票": "已开票"}
SETTLED_STATUS = rules.SETTLED_STATUS


class StorageService:
    def _yardstore_rows(self) -> list[dict[str, Any]]:
        return store.rows(YARDSTORE_MODULE)

    def _present(self, bill: dict[str, Any]) -> dict[str, Any]:
        return rules.derive(bill, self._yardstore_rows())

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        container: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """计费单列表：所有过滤都在统一投影上做，保证与导出取同一份数据。"""
        views = [self._present(row) for row in store.rows(MODULE)]
        if keyword:
            views = [row for row in views if keyword in str(row.get("计费单号", ""))]
        if status:
            views = [row for row in views if row.get("status") == status]
        if container:
            key = rules.normalize_container(container)
            views = [row for row in views if rules.normalize_container(row.get("关联箱号")) == key]
        total = len(views)
        start = max(page - 1, 0) * size
        return views[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        bill = store.find(MODULE, entry_id)
        return self._present(bill) if bill is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""

        container = str(values.get("关联箱号")).strip()
        period = str(values.get("计费周期")).strip()
        if rules.parse_period(period) is None:
            return None, [], "计费周期无法识别，请使用 2026-09-01~2026-09-10 或 2026-09 这样的格式"

        conflict = self._find_conflict(container, period)
        if conflict is not None:
            return None, [], (
                f"箱号 {container} 在计费周期 {period} 已存在计费单 "
                f"{conflict.get('计费单号')}，同一箱号同一周期只能计费一次"
            )

        rows = store.rows(MODULE)
        bill = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        bill["计费单号"] = str(values.get("计费单号")).strip()
        bill["关联箱号"] = container
        bill["计费周期"] = period
        bill["计费标准"] = str(values.get("计费标准") or "").strip()
        bill["客户名称"] = str(values.get("客户名称") or "").strip()
        bill["status"] = STATUS_ORDER[0]
        bill["pending"] = True
        bill["abnormal"] = False
        bill["locked"] = False
        rows.append(bill)
        store.save()
        return self._present(bill), [], ""

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """修改计费单：结清后拒绝任何改动；改箱号/周期要重新做唯一与周期校验。"""
        bill = store.find(MODULE, entry_id)
        if bill is None:
            return None, f"计费单 {entry_id} 不存在或已归档"
        if bill.get("status") == SETTLED_STATUS:
            return None, f"计费单 {bill.get('计费单号')} 已结清（已开票），结清后不可再修改"

        updates = {field: values[field] for field in EDITABLE_FIELDS if field in values}
        container = str(updates.get("关联箱号", bill.get("关联箱号"))).strip()
        period = str(updates.get("计费周期", bill.get("计费周期"))).strip()
        if rules.parse_period(period) is None:
            return None, "计费周期无法识别，请使用 2026-09-01~2026-09-10 或 2026-09 这样的格式"

        conflict = self._find_conflict(container, period, exclude_id=entry_id)
        if conflict is not None:
            return None, (
                f"箱号 {container} 在计费周期 {period} 已存在计费单 "
                f"{conflict.get('计费单号')}，同一箱号同一周期只能计费一次"
            )

        for field, value in updates.items():
            bill[field] = str(value).strip()
        store.save()
        return self._present(bill), ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        bill = store.find(MODULE, entry_id)
        if bill is None:
            return None, f"计费单 {entry_id} 不存在或已归档"
        if action not in NEXT_ACTION:
            return None, f"动作「{action}」不属于堆存计费可执行范围"
        if bill.get("status") == SETTLED_STATUS:
            return None, f"计费单 {bill.get('计费单号')} 已结清，结清后不可再修改"

        target = NEXT_ACTION[action]
        current_index = STATUS_ORDER.index(bill["status"])
        target_index = STATUS_ORDER.index(target)
        if target_index != current_index + 1:
            current = bill["status"]
            return None, f"计费单当前为「{current}」，不能直接执行「{action}」，请按顺序流转"

        if target == SETTLED_STATUS:
            # 结清瞬间固化天数与金额，之后只认这份快照。
            rules.snapshot_for_settle(bill, self._yardstore_rows())
        else:
            bill["status"] = target
        bill["pending"] = target != SETTLED_STATUS
        store.save()
        return self._present(bill), f"计费单已{action}"

    def _find_conflict(
        self,
        container: str,
        period: str,
        *,
        exclude_id: int | None = None,
    ) -> dict[str, Any] | None:
        target_container = rules.normalize_container(container)
        target_period = rules.normalize_period_key(period)
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if rules.normalize_container(row.get("关联箱号")) != target_container:
                continue
            if rules.normalize_period_key(row.get("计费周期")) == target_period:
                return row
        return None
