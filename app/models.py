from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Box(Base):
    __tablename__ = "boxes"

    id = Column(Integer, primary_key=True, index=True)
    box_no = Column(String(50), unique=True, index=True, nullable=False)
    status = Column(String(20), default="idle", nullable=False)
    current_customer = Column(String(100), nullable=True)
    current_route = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    turnover_tasks = relationship("TurnoverTask", back_populates="box")
    handover_records = relationship("HandoverRecord", back_populates="box")
    temperature_records = relationship("TemperatureRecord", back_populates="box")
    alerts = relationship("Alert", back_populates="box")


class TurnoverTask(Base):
    __tablename__ = "turnover_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String(50), unique=True, index=True, nullable=False)
    box_id = Column(Integer, ForeignKey("boxes.id"), nullable=False)
    box_no = Column(String(50), index=True, nullable=False)
    customer = Column(String(100), nullable=False)
    route = Column(String(100), nullable=False)
    expected_return_date = Column(DateTime, nullable=False)
    actual_return_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="outbound", nullable=False)
    is_overdue = Column(Boolean, default=False)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_task_id = Column(Integer, ForeignKey("turnover_tasks.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    box = relationship("Box", back_populates="turnover_tasks")
    handover_records = relationship("HandoverRecord", back_populates="turnover_task")
    duplicate_of_task = relationship("TurnoverTask", remote_side=[id])


class HandoverRecord(Base):
    __tablename__ = "handover_records"

    id = Column(Integer, primary_key=True, index=True)
    box_id = Column(Integer, ForeignKey("boxes.id"), nullable=False)
    box_no = Column(String(50), index=True, nullable=False)
    task_id = Column(Integer, ForeignKey("turnover_tasks.id"), nullable=True)
    record_type = Column(String(20), nullable=False)
    location = Column(String(200), nullable=True)
    operator = Column(String(50), nullable=True)
    remark = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)

    box = relationship("Box", back_populates="handover_records")
    turnover_task = relationship("TurnoverTask", back_populates="handover_records")


class TemperatureRecord(Base):
    __tablename__ = "temperature_records"

    id = Column(Integer, primary_key=True, index=True)
    box_id = Column(Integer, ForeignKey("boxes.id"), nullable=False)
    box_no = Column(String(50), index=True, nullable=False)
    temperature = Column(Float, nullable=False)
    is_abnormal = Column(Boolean, default=False)
    recorded_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)

    box = relationship("Box", back_populates="temperature_records")


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    complaint_no = Column(String(50), unique=True, index=True, nullable=False)
    box_no = Column(String(50), index=True, nullable=False)
    customer = Column(String(100), nullable=False)
    complaint_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_no = Column(String(50), unique=True, index=True, nullable=False)
    box_id = Column(Integer, ForeignKey("boxes.id"), nullable=True)
    box_no = Column(String(50), index=True, nullable=True)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="warning", nullable=False)
    responsible_node = Column(String(50), nullable=False)
    suggested_action = Column(String(200), nullable=False)
    latest_handover = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    target_roles = Column(String(200), nullable=False)
    is_read = Column(Boolean, default=False)
    is_handled = Column(Boolean, default=False)
    handled_by = Column(String(50), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    handled_note = Column(Text, nullable=True)
    assigned_to = Column(String(50), nullable=True)
    current_owner_role = Column(String(50), nullable=True)
    current_owner_name = Column(String(50), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    is_escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime, nullable=True)
    escalated_to = Column(String(50), nullable=True)
    escalation_note = Column(Text, nullable=True)
    last_pushed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    box = relationship("Box", back_populates="alerts")
    push_records = relationship("AlertPushRecord", back_populates="alert")
    disposals = relationship("AlertDisposal", back_populates="alert")
    comments = relationship("AlertComment", back_populates="alert")


class AlertPushRecord(Base):
    __tablename__ = "alert_push_records"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    alert_no = Column(String(50), index=True, nullable=False)
    recipient_id = Column(Integer, ForeignKey("alert_recipients.id"), nullable=True)
    recipient_name = Column(String(50), nullable=False)
    recipient_role = Column(String(50), nullable=False)
    push_channel = Column(String(20), default="system", nullable=False)
    push_target = Column(String(100), nullable=True)
    status = Column(String(20), default="success", nullable=False)
    error_message = Column(Text, nullable=True)
    pushed_at = Column(DateTime, default=datetime.now)

    alert = relationship("Alert", back_populates="push_records")


class AlertDisposal(Base):
    __tablename__ = "alert_disposals"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    alert_no = Column(String(50), index=True, nullable=False)
    disposal_type = Column(String(20), nullable=False)  # handle / assign
    operator_name = Column(String(50), nullable=False)
    operator_role = Column(String(50), nullable=False)
    disposal_note = Column(Text, nullable=True)
    assigned_to_role = Column(String(50), nullable=True)
    assigned_to_name = Column(String(50), nullable=True)
    operator_from_role = Column(String(50), nullable=True)
    operator_from_name = Column(String(50), nullable=True)
    disposal_result = Column(String(100), nullable=True)
    disposed_at = Column(DateTime, default=datetime.now)

    alert = relationship("Alert", back_populates="disposals")


class AlertComment(Base):
    __tablename__ = "alert_comments"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    alert_no = Column(String(50), index=True, nullable=False)
    comment_type = Column(String(20), default="comment", nullable=False)  # comment / attachment
    operator_name = Column(String(50), nullable=False)
    operator_role = Column(String(50), nullable=False)
    content = Column(Text, nullable=True)
    attachment_name = Column(String(200), nullable=True)
    attachment_url = Column(String(500), nullable=True)
    attachment_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    alert = relationship("Alert", back_populates="comments")


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, index=True, nullable=False)
    config_value = Column(Text, nullable=False)
    description = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CustomerTurnoverConfig(Base):
    __tablename__ = "customer_turnover_configs"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), unique=True, index=True, nullable=False)
    turnover_days = Column(Integer, default=7, nullable=False)
    description = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AlertRecipient(Base):
    __tablename__ = "alert_recipients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    role = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    alert_types = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
