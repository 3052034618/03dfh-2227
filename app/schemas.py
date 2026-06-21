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
    created_at: datetime

    class Config:
        from_attributes = True


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
