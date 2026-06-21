from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas import (
    SystemConfigRequest, CustomerTurnoverConfigRequest, AlertRecipientRequest,
    BoxResponse, TurnoverTaskResponse
)
from app.models import (
    SystemConfig, CustomerTurnoverConfig, AlertRecipient, Box, TurnoverTask, Alert
)

router = APIRouter(prefix="/api/admin", tags=["管理配置"])


@router.get("/configs", summary="获取所有系统配置")
def get_all_configs(db: Session = Depends(get_db)):
    configs = db.query(SystemConfig).all()
    return {c.config_key: c.config_value for c in configs}


@router.post("/configs", summary="新增或更新系统配置")
def upsert_config(request: SystemConfigRequest, db: Session = Depends(get_db)):
    config = db.query(SystemConfig).filter(
        SystemConfig.config_key == request.config_key
    ).first()
    if config:
        config.config_value = request.config_value
        config.description = request.description
    else:
        config = SystemConfig(
            config_key=request.config_key,
            config_value=request.config_value,
            description=request.description
        )
        db.add(config)
    db.commit()
    return {"success": True, "config_key": request.config_key}


@router.delete("/configs/{config_key}", summary="删除系统配置")
def delete_config(config_key: str, db: Session = Depends(get_db)):
    config = db.query(SystemConfig).filter(
        SystemConfig.config_key == config_key
    ).first()
    if config:
        db.delete(config)
        db.commit()
    return {"success": True}


@router.get("/customer-configs", summary="获取客户周转配置列表")
def get_customer_configs(db: Session = Depends(get_db)):
    configs = db.query(CustomerTurnoverConfig).all()
    return configs


@router.post("/customer-configs", summary="新增或更新客户周转配置")
def upsert_customer_config(request: CustomerTurnoverConfigRequest, db: Session = Depends(get_db)):
    config = db.query(CustomerTurnoverConfig).filter(
        CustomerTurnoverConfig.customer_name == request.customer_name
    ).first()
    if config:
        config.turnover_days = request.turnover_days
        config.description = request.description
    else:
        config = CustomerTurnoverConfig(
            customer_name=request.customer_name,
            turnover_days=request.turnover_days,
            description=request.description
        )
        db.add(config)
    db.commit()
    return {"success": True, "customer_name": request.customer_name}


@router.delete("/customer-configs/{customer_name}", summary="删除客户周转配置")
def delete_customer_config(customer_name: str, db: Session = Depends(get_db)):
    config = db.query(CustomerTurnoverConfig).filter(
        CustomerTurnoverConfig.customer_name == customer_name
    ).first()
    if config:
        db.delete(config)
        db.commit()
    return {"success": True}


@router.get("/recipients", summary="获取提醒接收人列表")
def get_recipients(db: Session = Depends(get_db)):
    recipients = db.query(AlertRecipient).all()
    return recipients


@router.post("/recipients", summary="新增提醒接收人")
def create_recipient(request: AlertRecipientRequest, db: Session = Depends(get_db)):
    recipient = AlertRecipient(
        name=request.name,
        role=request.role,
        phone=request.phone,
        email=request.email,
        alert_types=request.alert_types,
        is_active=request.is_active
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return {"success": True, "id": recipient.id}


@router.put("/recipients/{recipient_id}", summary="更新提醒接收人")
def update_recipient(recipient_id: int, request: AlertRecipientRequest, db: Session = Depends(get_db)):
    recipient = db.query(AlertRecipient).filter(AlertRecipient.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="接收人不存在")
    recipient.name = request.name
    recipient.role = request.role
    recipient.phone = request.phone
    recipient.email = request.email
    recipient.alert_types = request.alert_types
    recipient.is_active = request.is_active
    db.commit()
    return {"success": True}


@router.delete("/recipients/{recipient_id}", summary="删除提醒接收人")
def delete_recipient(recipient_id: int, db: Session = Depends(get_db)):
    recipient = db.query(AlertRecipient).filter(AlertRecipient.id == recipient_id).first()
    if recipient:
        db.delete(recipient)
        db.commit()
    return {"success": True}


@router.get("/boxes", response_model=List[BoxResponse], summary="获取箱体列表")
def get_boxes(status: str = None, db: Session = Depends(get_db)):
    query = db.query(Box)
    if status:
        query = query.filter(Box.status == status)
    return query.order_by(Box.updated_at.desc()).all()


@router.get("/boxes/{box_no}", response_model=BoxResponse, summary="获取箱体详情")
def get_box(box_no: str, db: Session = Depends(get_db)):
    box = db.query(Box).filter(Box.box_no == box_no).first()
    if not box:
        raise HTTPException(status_code=404, detail="箱体不存在")
    return box


@router.get("/tasks", response_model=List[TurnoverTaskResponse], summary="获取周转任务列表")
def get_tasks(status: str = None, customer: str = None, db: Session = Depends(get_db)):
    query = db.query(TurnoverTask)
    if status:
        query = query.filter(TurnoverTask.status == status)
    if customer:
        query = query.filter(TurnoverTask.customer == customer)
    return query.order_by(TurnoverTask.created_at.desc()).all()


@router.get("/tasks/{task_no}", response_model=TurnoverTaskResponse, summary="获取周转任务详情")
def get_task(task_no: str, db: Session = Depends(get_db)):
    task = db.query(TurnoverTask).filter(TurnoverTask.task_no == task_no).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/dashboard", summary="仪表盘统计")
def get_dashboard(db: Session = Depends(get_db)):
    total_boxes = db.query(Box).count()
    in_use_boxes = db.query(Box).filter(Box.status != "idle").count()
    overdue_boxes = db.query(Box).filter(Box.status == "overdue").count()
    active_tasks = db.query(TurnoverTask).filter(
        TurnoverTask.status.in_(["outbound", "in_transit", "signed"])
    ).count()
    unhandled_alerts = db.query(Alert).filter(Alert.is_handled == False).count()

    return {
        "total_boxes": total_boxes,
        "in_use_boxes": in_use_boxes,
        "idle_boxes": total_boxes - in_use_boxes,
        "overdue_boxes": overdue_boxes,
        "active_tasks": active_tasks,
        "unhandled_alerts": unhandled_alerts
    }
