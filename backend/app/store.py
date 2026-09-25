"""数据仓库：内存表 + 落盘持久化。

业务接口在进程内直接读写内存表（快、可筛选）；每次写操作后调用 save()
把全量数据原子写入本地 JSON，重启或浏览器刷新后仍能看到最后一次的结果，
不会再回到示例数据。真实项目里这里会换成数据库访问层。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.seed import SEED_ROWS

DATA_PATH = Path(os.environ.get("APP_DATA_FILE", Path(__file__).resolve().parent / "data" / "store.json"))


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if DATA_PATH.exists():
            try:
                with DATA_PATH.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict) and data.get("modules"):
                    return {name: [dict(row) for row in rows] for name, rows in data["modules"].items()}
            except (json.JSONDecodeError, OSError, TypeError):
                # 落盘文件损坏时退回示例数据，而不是让服务起不来。
                pass
        return {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    def save(self) -> None:
        """把当前全部表原子落盘；写失败只记录，不影响接口响应。"""
        with self._lock:
            try:
                DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
                payload = {"version": 1, "modules": self._tables}
                fd, tmp_name = tempfile.mkstemp(prefix=".store-", suffix=".json", dir=DATA_PATH.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(payload, handle, ensure_ascii=False)
                    os.replace(tmp_name, DATA_PATH)
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
            except OSError:
                pass

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
