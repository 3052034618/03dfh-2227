import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models import (
    Box, TurnoverTask, HandoverRecord, TemperatureRecord,
    Complaint, Alert, SystemConfig, CustomerTurnoverConfig, AlertRecipient
)


def generate_no(prefix: str) -> str:
    return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"


def get_config_value(db: Session, key: str, default: str) -> str:
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    return config.config_value if config else default


def get_customer_turnover_days(db: Session, customer: str) -> int:
    config = db.query(CustomerTurnoverConfig).filter(
        CustomerTurnoverConfig.customer_name == customer
    ).first()
    if config:
        return config.turnover_days
    default_days = get_config_value(db, "default_overdue_days", "7")
    return int(default_days)


def get_latest_handover_text(db: Session, box_id: int) -> str:
    record = db.query(HandoverRecord).filter(
        HandoverRecord.box_id == box_id
    ).order_by(HandoverRecord.recorded_at.desc()).first()
    if not record:
        return "暂无交接记录"
    return f"{record.record_type} | {record.location or '未知地点'} | {record.operator or '未知操作人'} | {record.recorded_at.strftime('%Y-%m-%d %H:%M')}"


def create_alert(
    db: Session,
    alert_type: str,
    severity: str,
    responsible_node: str,
    suggested_action: str,
    box_id: Optional[int] = None,
    box_no: Optional[str] = None,
    extra_info: str = "",
    target_roles: str = "dispatch,warehouse,customer_service"
) -> Alert:
    latest_handover = get_latest_handover_text(db, box_id) if box_id else "暂无"

    content_parts = [
        f"【{alert_type}】",
        f"箱号: {box_no or 'N/A'}",
        f"责任节点: {responsible_node}",
        f"建议动作: {suggested_action}",
        f"最近交接: {latest_handover}"
    ]
    if extra_info:
        content_parts.append(f"补充信息: {extra_info}")

    content = "\n".join(content_parts)

    alert = Alert(
        alert_no=generate_no("ALT"),
        box_id=box_id,
        box_no=box_no,
        alert_type=alert_type,
        severity=severity,
        responsible_node=responsible_node,
        suggested_action=suggested_action,
        latest_handover=latest_handover,
        content=content,
        target_roles=target_roles
    )
    db.add(alert)
    db.flush()
    return alert


def check_duplicate_outbound(db: Session, box_no: str) -> Optional[TurnoverTask]:
    box = db.query(Box).filter(Box.box_no == box_no).first()
    if not box:
        return None
    active_task = db.query(TurnoverTask).filter(
        TurnoverTask.box_no == box_no,
        TurnoverTask.status.in_(["outbound", "in_transit", "signed", "temp_abnormal", "overdue"])
    ).first()
    return active_task


def check_overdue(db: Session, task: TurnoverTask) -> bool:
    if task.status == "returned" or task.actual_return_date:
        return False
    overdue_days = get_customer_turnover_days(db, task.customer)
    deadline = task.expected_return_date + timedelta(days=overdue_days)
    return datetime.now() > deadline


def check_temperature_abnormal(db: Session, box_id: int, temperature: float) -> bool:
    min_temp = float(get_config_value(db, "min_temperature", "2"))
    max_temp = float(get_config_value(db, "max_temperature", "8"))
    return temperature < min_temp or temperature > max_temp


def check_customer_high_occupation(db: Session, customer: str) -> tuple:
    threshold = int(get_config_value(db, "customer_high_occupation_threshold", "10"))
    active_tasks = db.query(TurnoverTask).filter(
        TurnoverTask.customer == customer,
        TurnoverTask.status.in_(["outbound", "in_transit", "signed", "temp_abnormal", "overdue"])
    ).all()
    unique_boxes = set()
    for task in active_tasks:
        if not task.is_duplicate:
            unique_boxes.add(task.box_no)
    active_count = len(unique_boxes)
    return active_count >= threshold, active_count


def get_active_tasks_by_box(db: Session, box_no: str) -> List[TurnoverTask]:
    return db.query(TurnoverTask).filter(
        TurnoverTask.box_no == box_no,
        TurnoverTask.status.in_(["outbound", "in_transit", "signed", "temp_abnormal", "overdue"])
    ).all()


def run_overdue_check(db: Session) -> List[Alert]:
    alerts = []
    active_tasks = db.query(TurnoverTask).filter(
        TurnoverTask.status.in_(["outbound", "in_transit", "signed"])
    ).all()

    for task in active_tasks:
        if check_overdue(db, task):
            if not task.is_overdue:
                task.is_overdue = True
                box = db.query(Box).filter(Box.id == task.box_id).first()
                if box and box.status != "temp_abnormal":
                    box.status = "overdue"

                alert = create_alert(
                    db=db,
                    alert_type="超期未回",
                    severity="high",
                    responsible_node="调度",
                    suggested_action="立即联系客户催还箱体，必要时安排上门回收",
                    box_id=task.box_id,
                    box_no=task.box_no,
                    extra_info=f"客户: {task.customer}, 线路: {task.route}, 预计归还: {task.expected_return_date.strftime('%Y-%m-%d')}",
                    target_roles="dispatch,customer_service"
                )
                alerts.append(alert)

    db.commit()
    return alerts


def run_all_checks(db: Session) -> List[Alert]:
    all_alerts = []
    all_alerts.extend(run_overdue_check(db))
    return all_alerts
