from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.schemas import (
    AlertResponse, AlertPushRecordResponse, AlertDisposalResponse,
    HandleAlertRequest, AssignAlertRequest, BatchHandleRequest,
    DashboardSummary, DashboardItem
)
from app.services import NotificationService, run_all_checks, run_overdue_check
from app.models import Alert, AlertPushRecord, AlertDisposal, TurnoverTask

router = APIRouter(prefix="/api/alerts", tags=["提醒管理"])


@router.get("", response_model=List[AlertResponse], summary="查询提醒列表")
def get_alerts(
    role: Optional[str] = Query(None, description="按角色筛选"),
    is_handled: Optional[bool] = Query(None, description="是否已处理"),
    alert_type: Optional[str] = Query(None, description="按异常类型筛选"),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if role:
        query = query.filter(Alert.target_roles.contains(role))
    if is_handled is not None:
        query = query.filter(Alert.is_handled == is_handled)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    return query.order_by(Alert.created_at.desc()).all()


@router.get("/{alert_id}", summary="查询提醒详情（含推送记录+处置记录）")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    push_records = db.query(AlertPushRecord).filter(
        AlertPushRecord.alert_id == alert_id
    ).order_by(AlertPushRecord.pushed_at.desc()).all()
    disposals = db.query(AlertDisposal).filter(
        AlertDisposal.alert_id == alert_id
    ).order_by(AlertDisposal.disposed_at.desc()).all()
    return {
        "alert": AlertResponse.model_validate(alert).model_dump(),
        "push_records": [AlertPushRecordResponse.model_validate(r).model_dump() for r in push_records],
        "disposals": [AlertDisposalResponse.model_validate(d).model_dump() for d in disposals]
    }


@router.get("/{alert_id}/push-records", response_model=List[AlertPushRecordResponse], summary="查询提醒推送记录")
def get_alert_push_records(alert_id: int, db: Session = Depends(get_db)):
    return db.query(AlertPushRecord).filter(
        AlertPushRecord.alert_id == alert_id
    ).order_by(AlertPushRecord.pushed_at.desc()).all()


@router.get("/{alert_id}/disposals", response_model=List[AlertDisposalResponse], summary="查询提醒处置记录")
def get_alert_disposals(alert_id: int, db: Session = Depends(get_db)):
    return db.query(AlertDisposal).filter(
        AlertDisposal.alert_id == alert_id
    ).order_by(AlertDisposal.disposed_at.desc()).all()


@router.post("/{alert_id}/push", summary="重新推送提醒")
def push_alert_again(alert_id: int, db: Session = Depends(get_db)):
    service = NotificationService(db)
    result = service.push_alert_again(alert_id)
    db.commit()
    return result


@router.put("/{alert_id}/read", summary="标记已读")
def mark_as_read(alert_id: int, db: Session = Depends(get_db)):
    service = NotificationService(db)
    alert = service.mark_as_read(alert_id)
    return {"success": True, "alert_id": alert_id}


@router.post("/{alert_id}/handle", response_model=AlertDisposalResponse, summary="处理提醒（填写处理结果）")
def handle_alert(alert_id: int, req: HandleAlertRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    if alert.is_handled:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        disp = db.query(AlertDisposal).filter(AlertDisposal.alert_id == alert_id).order_by(AlertDisposal.id.desc()).first()
        return disp
    alert.is_handled = True
    alert.handled_by = req.handled_by
    alert.handled_at = datetime.now()
    alert.handled_note = req.handled_note
    alert.is_read = True
    db.flush()
    disposal = AlertDisposal(
        alert_id=alert.id,
        alert_no=alert.alert_no,
        disposal_type="handle",
        operator_name=req.handled_by,
        operator_role="operator",
        disposal_note=req.handled_note,
        disposal_result=req.disposal_result or "已跟进处理",
        disposed_at=datetime.now()
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    return disposal


@router.post("/{alert_id}/assign", response_model=AlertDisposalResponse, summary="转派提醒给其他角色")
def assign_alert(alert_id: int, req: AssignAlertRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    alert.assigned_to = req.assigned_to_role
    alert.is_read = True
    db.flush()
    disposal = AlertDisposal(
        alert_id=alert.id,
        alert_no=alert.alert_no,
        disposal_type="assign",
        operator_name=req.operator_name,
        operator_role=req.operator_role,
        disposal_note=req.disposal_note,
        assigned_to_role=req.assigned_to_role,
        assigned_to_name=req.assigned_to_name,
        disposal_result=f"转派给 {req.assigned_to_name}({req.assigned_to_role})",
        disposed_at=datetime.now()
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    return disposal


@router.post("/batch-handle", summary="批量处理提醒")
def batch_handle_alerts(req: BatchHandleRequest, db: Session = Depends(get_db)):
    now = datetime.now()
    processed = 0
    skipped = 0
    skipped_ids = []

    for alert_id in req.alert_ids:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            skipped += 1
            skipped_ids.append(alert_id)
            continue
        if alert.is_handled:
            skipped += 1
            skipped_ids.append(alert_id)
            continue
        if alert.box_no:
            from app.models import Box
            box = db.query(Box).filter(Box.box_no == alert.box_no).first()
            if box and box.status == "idle":
                skipped += 1
                skipped_ids.append(alert_id)
                continue

        alert.is_handled = True
        alert.handled_by = req.handled_by
        alert.handled_at = now
        alert.handled_note = req.handled_note
        alert.is_read = True
        db.flush()

        disposal = AlertDisposal(
            alert_id=alert.id,
            alert_no=alert.alert_no,
            disposal_type="handle",
            operator_name=req.handled_by,
            operator_role="operator",
            disposal_note=req.handled_note,
            disposal_result=req.disposal_result or "批量跟进处理",
            disposed_at=now
        )
        db.add(disposal)
        processed += 1

    db.commit()
    return {
        "success": True,
        "processed": processed,
        "skipped": skipped,
        "skipped_ids": skipped_ids
    }


def _calc_dashboard_for_dimension(db: Session, dimension: str, alert_column,
                                   task_column=None) -> List[DashboardItem]:
    from sqlalchemy import func, and_
    items_map = {}

    pending_alerts = db.query(Alert).filter(Alert.is_handled == False).all()

    for alert in pending_alerts:
        if task_column is not None and alert.box_no:
            task = db.query(TurnoverTask).filter(
                TurnoverTask.box_no == alert.box_no,
                TurnoverTask.status.notin_(["returned"]),
                TurnoverTask.is_duplicate == False
            ).order_by(TurnoverTask.id.desc()).first()
            if task:
                if task_column == "customer":
                    value = task.customer
                elif task_column == "route":
                    value = task.route
                else:
                    value = None
            else:
                value = None
        else:
            value = getattr(alert, alert_column.key) if hasattr(alert, alert_column.key) else None

        if not value:
            continue

        key = str(value)
        if key not in items_map:
            items_map[key] = {
                "pending_count": 0,
                "total_minutes": 0,
                "alert_count": 0,
                "latest_id": alert.id,
                "latest_box": alert.box_no
            }
        items_map[key]["pending_count"] += 1
        minutes = (datetime.now() - alert.created_at).total_seconds() / 60
        items_map[key]["total_minutes"] += minutes
        items_map[key]["alert_count"] += 1
        if alert.id > items_map[key]["latest_id"]:
            items_map[key]["latest_id"] = alert.id
            items_map[key]["latest_box"] = alert.box_no

    items = []
    for key, data in items_map.items():
        avg_minutes = data["total_minutes"] / data["alert_count"] if data["alert_count"] > 0 else 0
        items.append(DashboardItem(
            dimension=dimension,
            dimension_value=key,
            pending_count=data["pending_count"],
            avg_processing_minutes=round(avg_minutes, 1),
            latest_alert_id=data["latest_id"],
            latest_box_no=data["latest_box"]
        ))
    return sorted(items, key=lambda x: -x.pending_count)


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="责任节点看板-总览")
def get_dashboard_summary(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total_pending = db.query(func.count(Alert.id)).filter(Alert.is_handled == False).scalar() or 0
    total_handled = db.query(func.count(Alert.id)).filter(Alert.is_handled == True).scalar() or 0
    total_temp_abnormal = db.query(func.count(Alert.id)).filter(
        Alert.is_handled == False, Alert.alert_type == "温控异常"
    ).scalar() or 0
    total_overdue = db.query(func.count(Alert.id)).filter(
        Alert.is_handled == False, Alert.alert_type == "超期未回"
    ).scalar() or 0
    total_complaint = db.query(func.count(Alert.id)).filter(
        Alert.is_handled == False, Alert.alert_type == "客户投诉"
    ).scalar() or 0
    total_duplicate = db.query(func.count(Alert.id)).filter(
        Alert.is_handled == False, Alert.alert_type == "同箱重复出库"
    ).scalar() or 0

    pending_alerts = db.query(Alert).filter(Alert.is_handled == False).all()
    total_minutes = 0
    for a in pending_alerts:
        total_minutes += (datetime.now() - a.created_at).total_seconds() / 60
    avg_result = total_minutes / len(pending_alerts) if pending_alerts else 0

    return DashboardSummary(
        total_pending=int(total_pending),
        total_handled=int(total_handled),
        avg_processing_minutes=round(float(avg_result), 1),
        total_temp_abnormal=int(total_temp_abnormal),
        total_overdue=int(total_overdue),
        total_complaint=int(total_complaint),
        total_duplicate=int(total_duplicate)
    )


@router.get("/dashboard/by-customer", response_model=List[DashboardItem], summary="责任节点看板-按客户汇总")
def get_dashboard_by_customer(db: Session = Depends(get_db)):
    return _calc_dashboard_for_dimension(db, "customer", None, task_column="customer")


@router.get("/dashboard/by-route", response_model=List[DashboardItem], summary="责任节点看板-按线路汇总")
def get_dashboard_by_route(db: Session = Depends(get_db)):
    return _calc_dashboard_for_dimension(db, "route", None, task_column="route")


@router.get("/dashboard/by-box", response_model=List[DashboardItem], summary="责任节点看板-按箱号汇总")
def get_dashboard_by_box(db: Session = Depends(get_db)):
    return _calc_dashboard_for_dimension(db, "box_no", Alert.box_no)


@router.get("/dashboard/by-type", response_model=List[DashboardItem], summary="责任节点看板-按异常类型汇总")
def get_dashboard_by_type(db: Session = Depends(get_db)):
    return _calc_dashboard_for_dimension(db, "alert_type", Alert.alert_type)


@router.post("/check/run", summary="手动执行规则检查")
def run_checks(db: Session = Depends(get_db)):
    alerts = run_all_checks(db)
    return {
        "success": True,
        "new_alerts": len(alerts),
        "alerts": [a.alert_no for a in alerts]
    }


@router.post("/check/overdue", summary="手动执行超期检查")
def run_overdue(db: Session = Depends(get_db)):
    alerts = run_overdue_check(db)
    return {
        "success": True,
        "new_alerts": len(alerts),
        "alerts": [a.alert_no for a in alerts]
    }
