from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas import AlertResponse, AlertPushRecordResponse
from app.services import NotificationService, run_all_checks, run_overdue_check
from app.models import Alert, AlertPushRecord

router = APIRouter(prefix="/api/alerts", tags=["提醒管理"])


@router.get("", response_model=List[AlertResponse], summary="查询提醒列表")
def get_alerts(
    role: Optional[str] = Query(None, description="按角色筛选"),
    is_handled: Optional[bool] = Query(None, description="是否已处理"),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if role:
        query = query.filter(Alert.target_roles.contains(role))
    if is_handled is not None:
        query = query.filter(Alert.is_handled == is_handled)
    return query.order_by(Alert.created_at.desc()).all()


@router.get("/{alert_id}", summary="查询提醒详情（含推送记录）")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return None
    push_records = db.query(AlertPushRecord).filter(
        AlertPushRecord.alert_id == alert_id
    ).order_by(AlertPushRecord.pushed_at.desc()).all()
    return {
        "alert": AlertResponse.model_validate(alert).model_dump(),
        "push_records": [AlertPushRecordResponse.model_validate(r).model_dump() for r in push_records]
    }


@router.get("/{alert_id}/push-records", response_model=List[AlertPushRecordResponse], summary="查询提醒推送记录")
def get_alert_push_records(alert_id: int, db: Session = Depends(get_db)):
    return db.query(AlertPushRecord).filter(
        AlertPushRecord.alert_id == alert_id
    ).order_by(AlertPushRecord.pushed_at.desc()).all()


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


@router.put("/{alert_id}/handle", summary="标记已处理")
def mark_as_handled(alert_id: int, db: Session = Depends(get_db)):
    service = NotificationService(db)
    alert = service.mark_as_handled(alert_id)
    return {"success": True, "alert_id": alert_id}


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
