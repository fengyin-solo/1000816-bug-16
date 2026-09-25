"""堆存计费口径：金额与堆存天数的唯一计算来源。

列表、详情、导出都调用这里的 derive/settled 投影，保证三处看到的
（堆存天数、应收金额、计费状态）永远一致，不再"各算各的"。

口径约定：
- 计费周期支持完整区间（如 2026-09-01~2026-09-10、2026-09-01 至 2026-09-10）
  与整月（2026-09，按当月首末日）；天数按"起讫均计"（结束-开始+1）。
- 堆存天数优先取堆存记录（yardstore）中该箱号与周期重叠的区间，
  重叠区间会先合并再计数，避免同一时间被两张单重复计费；
  没有堆存记录时退化为按计费周期本身计天。
- 计费标准中提取第一个数字作为日费率（元/天），无法识别时按 0 处理。
- 金额 = 堆存天数 × 日费率，四舍五入保留两位。
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any, Iterable

# 计费单终态：达到该状态即视为结清，锁定不可再改。
SETTLED_STATUS = "已开票"

FULL_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
MONTH_RE = re.compile(r"(\d{4})[-/.](\d{1,2})(?!\d)")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

DEFAULT_RATE = 0.0


def normalize_container(value: Any) -> str:
    """箱号归一化：去空白，避免空格/大小写造成同箱号被当作两票。"""
    return re.sub(r"\s+", "", str(value or "")).upper()


def _to_date(year: int, month: int, day: int | None) -> date | None:
    try:
        return date(year, month, day or 1)
    except ValueError:
        return None


def parse_period(period: Any) -> tuple[date, date] | None:
    """把计费周期文本解析为 [起, 止] 闭区间；无法解析时返回 None。"""
    text = str(period or "").strip()
    if not text:
        return None

    # 完整日期（年月日齐全）成对出现时按区间处理，避免把 "2026-09" 误拆成两个日期。
    full_dates = list(FULL_DATE_RE.finditer(text))
    if len(full_dates) >= 2:
        first, last = full_dates[0], full_dates[-1]
        start = _to_date(int(first[1]), int(first[2]), int(first[3]))
        end = _to_date(int(last[1]), int(last[2]), int(last[3]))
    elif full_dates:
        first = full_dates[0]
        start = end = _to_date(int(first[1]), int(first[2]), int(first[3]))
    else:
        # 整月周期：2026-09 表示 9 月 1 日到月末。
        month_match = MONTH_RE.search(text)
        if month_match is None:
            return None
        year, month = int(month_match[1]), int(month_match[2])
        if not 1 <= month <= 12:
            return None
        start = _to_date(year, month, 1)
        end = _to_date(year, month, calendar.monthrange(year, month)[1])

    if start is None or end is None or end < start:
        return None
    return start, end


def normalize_period_key(period: Any) -> str:
    """周期归一化键：同一区间的不同写法（~、至、/）映射到同一个键。

    无法解析时退化为去除分隔符与空白的文本，保证唯一性检查始终有键可比。
    """
    parsed = parse_period(period)
    if parsed is not None:
        return f"{parsed[0].isoformat()}~{parsed[1].isoformat()}"
    return re.sub(r"[\s~～至\-/]", "", str(period or "")).upper()


def parse_rate(standard: Any) -> float:
    """从计费标准文本中提取日费率；无法识别时按 0 处理。"""
    match = NUMBER_RE.search(str(standard or ""))
    return float(match.group()) if match else DEFAULT_RATE


def _yardstore_intervals(
    yardstore_rows: Iterable[dict[str, Any]], container: str
) -> list[tuple[date, date | None]]:
    intervals: list[tuple[date, date | None]] = []
    for row in yardstore_rows:
        if normalize_container(row.get("关联箱号")) != container:
            continue
        start = parse_loose_date(row.get("堆存开始"))
        if start is None:
            continue
        # 仍在堆存（未提离）的记录结束日为 None，表示开放区间。
        intervals.append((start, parse_loose_date(row.get("堆存结束"))))
    return intervals


def parse_loose_date(value: Any) -> date | None:
    """从任意文本中提取第一个完整日期（年月日齐全）。"""
    if not value:
        return None
    match = FULL_DATE_RE.search(str(value))
    if match is None:
        return None
    return _to_date(int(match[1]), int(match[2]), int(match[3]))


def _clamp(
    interval: tuple[date, date | None], start: date, end: date
) -> tuple[date, date] | None:
    lo = max(interval[0], start)
    # 开放区间（仍在堆存）收口到计费周期末日；已提离的不超过提离日。
    hi = end if interval[1] is None else min(interval[1], end)
    return (lo, hi) if hi >= lo else None


def overlap_days(
    yardstore_rows: Iterable[dict[str, Any]],
    container: str,
    start: date,
    end: date,
) -> int:
    """计算该箱号堆存记录与计费周期重叠的天数（先合并重叠区间，杜绝重复计天）。"""
    clamped = [
        seg
        for interval in _yardstore_intervals(yardstore_rows, container)
        if (seg := _clamp(interval, start, end)) is not None
    ]
    if not clamped:
        return 0

    clamped.sort()
    merged: list[tuple[date, date]] = []
    for lo, hi in clamped:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return sum((hi - lo).days + 1 for lo, hi in merged)


def period_days(start: date, end: date) -> int:
    """周期天数：起讫均计。"""
    return (end - start).days + 1


def derive(bill: dict[str, Any], yardstore_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """计费单的统一投影：以箱号+周期为唯一键重算天数与金额。

    已结清（已开票）的单子返回锁定快照，保证历史对账结果不被后续改动影响；
    其余单子每次都按堆存记录与最新费率实时推导。
    """
    view = dict(bill)
    container = normalize_container(bill.get("关联箱号"))
    view["关联箱号"] = bill.get("关联箱号")

    locked = bill.get("status") == SETTLED_STATUS
    if locked and bill.get("locked"):
        # 结清时已固化天数与金额，列表/导出/详情看到的都是同一份结算结果。
        view["堆存天数"] = bill.get("堆存天数", 0)
        view["应收金额"] = bill.get("应收金额", 0)
        view["计费状态"] = bill.get("计费状态") or SETTLED_STATUS
        view["已结清"] = True
        return view

    parsed = parse_period(bill.get("计费周期"))
    if parsed is None:
        days = int(bill.get("堆存天数") or 0)
    else:
        start, end = parsed
        days = overlap_days(yardstore_rows, container, start, end)
        if days <= 0:
            # 还没有堆存记录可对齐时，至少按计费周期本身计天，金额随周期联动。
            days = period_days(start, end)

    rate = parse_rate(bill.get("计费标准"))
    amount = round(days * rate, 2)
    view["堆存天数"] = days
    view["应收金额"] = amount
    view["计费状态"] = bill.get("status", "")
    view["已结清"] = False
    return view


def snapshot_for_settle(bill: dict[str, Any], yardstore_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """结清（开具发票）时固化最终天数与金额，作为之后不可变的对账依据。"""
    view = derive(bill, yardstore_rows)
    bill["status"] = SETTLED_STATUS
    bill["堆存天数"] = view["堆存天数"]
    bill["应收金额"] = view["应收金额"]
    bill["计费状态"] = SETTLED_STATUS
    bill["locked"] = True
    return bill
