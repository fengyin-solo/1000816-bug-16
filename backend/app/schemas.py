"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None
    action: str | None = None



class BerthEntry(BaseModel):
    """泊位计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 泊位编号
    field_2: str | None = None  # 靠泊船舶
    field_3: str | None = None  # 计划靠泊时间
    field_4: str | None = None  # 计划离泊时间
    field_5: str | None = None  # 船长
    field_6: str | None = None  # 吃水深度
    field_7: str | None = None  # 计划状态

class VesselEntry(BaseModel):
    """船舶明细结构。"""

    field_0: str | None = None  # 船舶编号
    field_1: str | None = None  # 船舶名称
    field_2: str | None = None  # 船舶类型
    field_3: str | None = None  # 载重吨位
    field_4: str | None = None  # 船长
    field_5: str | None = None  # 船宽
    field_6: str | None = None  # 所属船公司
    field_7: str | None = None  # 船舶状态

class VoyageEntry(BaseModel):
    """航次明细结构。"""

    field_0: str | None = None  # 航次编号
    field_1: str | None = None  # 关联船舶
    field_2: str | None = None  # 进口航次号
    field_3: str | None = None  # 出口航次号
    field_4: str | None = None  # 预计到港
    field_5: str | None = None  # 实际到港
    field_6: str | None = None  # 航线名称
    field_7: str | None = None  # 航次状态

class CraneEntry(BaseModel):
    """岸桥明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 岸桥型号
    field_2: str | None = None  # 额定起重量
    field_3: str | None = None  # 作业泊位
    field_4: str | None = None  # 司机姓名
    field_5: str | None = None  # 班次
    field_6: str | None = None  # 作业量
    field_7: str | None = None  # 设备状态

class LoadingEntry(BaseModel):
    """装卸任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 关联航次
    field_2: str | None = None  # 作业类型
    field_3: str | None = None  # 计划箱量
    field_4: str | None = None  # 完成箱量
    field_5: str | None = None  # 作业班组
    field_6: str | None = None  # 开始时间
    field_7: str | None = None  # 任务状态

class YardEntry(BaseModel):
    """箱区明细结构。"""

    field_0: str | None = None  # 箱区编号
    field_1: str | None = None  # 箱区名称
    field_2: str | None = None  # 堆放层数
    field_3: str | None = None  # 可用箱位
    field_4: str | None = None  # 已用箱位
    field_5: str | None = None  # 所属堆场
    field_6: str | None = None  # 责任人
    field_7: str | None = None  # 箱区状态

class ContainerEntry(BaseModel):
    """集装箱明细结构。"""

    field_0: str | None = None  # 箱号
    field_1: str | None = None  # 箱型
    field_2: str | None = None  # 箱况等级
    field_3: str | None = None  # 所属船公司
    field_4: str | None = None  # 尺寸规格
    field_5: str | None = None  # 自重
    field_6: str | None = None  # 检验到期日
    field_7: str | None = None  # 箱体状态

class YardstoreEntry(BaseModel):
    """堆存单明细结构。"""

    field_0: str | None = None  # 堆存单号
    field_1: str | None = None  # 关联箱号
    field_2: str | None = None  # 箱区编号
    field_3: str | None = None  # 贝位号
    field_4: str | None = None  # 堆存开始
    field_5: str | None = None  # 堆存结束
    field_6: str | None = None  # 堆存天数
    field_7: str | None = None  # 堆存状态

class GateEntry(BaseModel):
    """通行记录明细结构。"""

    field_0: str | None = None  # 通行编号
    field_1: str | None = None  # 车牌号码
    field_2: str | None = None  # 关联箱号
    field_3: str | None = None  # 进出方向
    field_4: str | None = None  # 通行时间
    field_5: str | None = None  # 道口编号
    field_6: str | None = None  # 值守人员
    field_7: str | None = None  # 通行状态

class TruckEntry(BaseModel):
    """集卡明细结构。"""

    field_0: str | None = None  # 调度单号
    field_1: str | None = None  # 集卡牌号
    field_2: str | None = None  # 司机姓名
    field_3: str | None = None  # 作业任务
    field_4: str | None = None  # 派车时间
    field_5: str | None = None  # 返回时间
    field_6: str | None = None  # 所属车队
    field_7: str | None = None  # 调度状态

class TallyEntry(BaseModel):
    """理货单明细结构。"""

    field_0: str | None = None  # 理货单号
    field_1: str | None = None  # 关联航次
    field_2: str | None = None  # 理货方式
    field_3: str | None = None  # 理货箱量
    field_4: str | None = None  # 残损箱数
    field_5: str | None = None  # 理货人员
    field_6: str | None = None  # 完成时间
    field_7: str | None = None  # 理货状态

class DamageEntry(BaseModel):
    """残损记录明细结构。"""

    field_0: str | None = None  # 残损编号
    field_1: str | None = None  # 关联箱号
    field_2: str | None = None  # 残损类型
    field_3: str | None = None  # 残损部位
    field_4: str | None = None  # 责任方
    field_5: str | None = None  # 发现时间
    field_6: str | None = None  # 登记人员
    field_7: str | None = None  # 残损状态

class ManifestEntry(BaseModel):
    """单证明细结构。"""

    field_0: str | None = None  # 单证编号
    field_1: str | None = None  # 单证类型
    field_2: str | None = None  # 关联航次
    field_3: str | None = None  # 申报箱量
    field_4: str | None = None  # 申报人
    field_5: str | None = None  # 提交时间
    field_6: str | None = None  # 审核人员
    field_7: str | None = None  # 单证状态

class StorageEntry(BaseModel):
    """计费单明细结构。"""

    field_0: str | None = None  # 计费单号
    field_1: str | None = None  # 关联箱号
    field_2: str | None = None  # 计费周期
    field_3: str | None = None  # 堆存天数
    field_4: str | None = None  # 计费标准
    field_5: str | None = None  # 应收金额
    field_6: str | None = None  # 客户名称
    field_7: str | None = None  # 计费状态

class PilotEntry(BaseModel):
    """引航作业明细结构。"""

    field_0: str | None = None  # 作业编号
    field_1: str | None = None  # 作业类型
    field_2: str | None = None  # 关联船舶
    field_3: str | None = None  # 拖轮名称
    field_4: str | None = None  # 引航员
    field_5: str | None = None  # 计划时间
    field_6: str | None = None  # 实际时间
    field_7: str | None = None  # 作业状态

class SafetyEntry(BaseModel):
    """安全检查明细结构。"""

    field_0: str | None = None  # 检查编号
    field_1: str | None = None  # 检查区域
    field_2: str | None = None  # 检查类型
    field_3: str | None = None  # 隐患项数
    field_4: str | None = None  # 整改项数
    field_5: str | None = None  # 检查人员
    field_6: str | None = None  # 检查日期
    field_7: str | None = None  # 检查状态

class CustomerEntry(BaseModel):
    """货主明细结构。"""

    field_0: str | None = None  # 客户编码
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 客户类型
    field_3: str | None = None  # 联系人
    field_4: str | None = None  # 联系电话
    field_5: str | None = None  # 结算方式
    field_6: str | None = None  # 信用等级
    field_7: str | None = None  # 客户状态

class SettleEntry(BaseModel):
    """结算单明细结构。"""

    field_0: str | None = None  # 结算单号
    field_1: str | None = None  # 结算对象
    field_2: str | None = None  # 结算周期
    field_3: str | None = None  # 作业量
    field_4: str | None = None  # 应收金额
    field_5: str | None = None  # 已收金额
    field_6: str | None = None  # 开票状态
    field_7: str | None = None  # 结算状态
