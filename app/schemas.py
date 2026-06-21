from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class OutboundRequest(BaseModel):
    box_no: str = Field(..., description="箱号")
    customer: str = Field(..., description="客户名称")
    route: str = Field(..., description="线路")
    expected_return_date: datetime = Field(..., description="预计归还日期")
    operator: Optional[str] = Field(None, description="操作人")


class OutboundResponse(BaseModel):
    task_no: str
    box_no: str
    customer: str
    route: str
    expected_return_date: datetime
    status: str

    class Config:
        from_attributes = True


class SignRequest(BaseModel):
    box_no: str = Field(..., description="箱号")
    location: Optional[str] = Field(None, description="签收地点")
    operator: Optional[str] = Field(None, description="签收人")
    remark: Optional[str] = Field(None, description="备注")


class ReturnRequest(BaseModel):
    box_no: str = Field(..., description="箱号")
    location: Optional[str] = Field(None, description="回仓地点")
    operator: Optional[str] = Field(None, description="回仓操作人")
    remark: Optional[str] = Field(None, description="备注")


class TemperatureRequest(BaseModel):
    box_no: str = Field(..., description="箱号")
    temperature: float = Field(..., description="温度值")
    recorded_at: Optional[datetime] = Field(None, description="记录时间")


class ComplaintRequest(BaseModel):
    box_no: str = Field(..., description="箱号")
    customer: str = Field(..., description="客户名称")
    complaint_type: str = Field(..., description="投诉类型")
    description: Optional[str] = Field(None, description="投诉描述")


class HandoverRecordResponse(BaseModel):
    id: int
    box_no: str
    record_type: str
    location: Optional[str]
    operator: Optional[str]
    remark: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: int
    alert_no: str
    box_no: Optional[str]
    alert_type: str
    severity: str
    responsible_node: str
    suggested_action: str
    latest_handover: Optional[str]
    content: str
    target_roles: str
    is_read: bool
    is_handled: bool
    handled_by: Optional[str]
    handled_at: Optional[datetime]
    handled_note: Optional[str]
    assigned_to: Optional[str]
    current_owner_role: Optional[str]
    current_owner_name: Optional[str]
    last_pushed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertPushRecordResponse(BaseModel):
    id: int
    alert_id: int
    alert_no: str
    recipient_id: Optional[int]
    recipient_name: str
    recipient_role: str
    push_channel: str
    push_target: Optional[str]
    status: str
    error_message: Optional[str]
    pushed_at: datetime

    class Config:
        from_attributes = True


class AlertDisposalResponse(BaseModel):
    id: int
    alert_id: int
    alert_no: str
    disposal_type: str
    operator_name: str
    operator_role: str
    disposal_note: Optional[str]
    assigned_to_role: Optional[str]
    assigned_to_name: Optional[str]
    operator_from_role: Optional[str]
    operator_from_name: Optional[str]
    disposal_result: Optional[str]
    disposed_at: datetime

    class Config:
        from_attributes = True


class HandleAlertRequest(BaseModel):
    handled_by: str = Field(..., description="处理人姓名")
    handled_note: Optional[str] = Field(None, description="处理备注")
    disposal_result: Optional[str] = Field(None, description="处理结果")


class AssignAlertRequest(BaseModel):
    operator_name: str = Field(..., description="操作人姓名")
    operator_role: str = Field(..., description="操作人角色")
    assigned_to_role: str = Field(..., description="转派目标角色")
    assigned_to_name: str = Field(..., description="转派目标姓名")
    disposal_note: Optional[str] = Field(None, description="转派备注")


class BatchHandleRequest(BaseModel):
    alert_ids: List[int] = Field(..., description="要处理的提醒ID列表")
    handled_by: str = Field(..., description="处理人姓名")
    handled_note: str = Field(..., description="批量处理说明")
    disposal_result: Optional[str] = Field(None, description="处理结果")


class DashboardSummary(BaseModel):
    total_pending: int
    total_handled: int
    avg_processing_minutes: float
    total_temp_abnormal: int
    total_overdue: int
    total_complaint: int
    total_duplicate: int


class DashboardItem(BaseModel):
    dimension: str
    dimension_value: str
    pending_count: int
    avg_processing_minutes: float
    latest_alert_id: Optional[int]
    latest_box_no: Optional[str]


class SystemConfigRequest(BaseModel):
    config_key: str
    config_value: str
    description: Optional[str] = None


class CustomerTurnoverConfigRequest(BaseModel):
    customer_name: str
    turnover_days: int
    description: Optional[str] = None


class AlertRecipientRequest(BaseModel):
    name: str
    role: str
    phone: Optional[str] = None
    email: Optional[str] = None
    alert_types: str
    is_active: bool = True


class TurnoverTaskResponse(BaseModel):
    id: int
    task_no: str
    box_no: str
    customer: str
    route: str
    expected_return_date: datetime
    actual_return_date: Optional[datetime]
    status: str
    is_overdue: bool
    is_duplicate: bool
    duplicate_of_task_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class BoxResponse(BaseModel):
    id: int
    box_no: str
    status: str
    current_customer: Optional[str]
    current_route: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DrillDownRequest(BaseModel):
    dimension: str = Field(..., description="维度: customer/route/box_no/alert_type")
    dimension_value: str = Field(..., description="维度值")


class ExportRequest(BaseModel):
    start_date: Optional[str] = Field(None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="结束日期 YYYY-MM-DD")
    alert_type: Optional[str] = Field(None, description="异常类型筛选")
