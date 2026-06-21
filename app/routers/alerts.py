import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.schemas import (
    AlertResponse, AlertPushRecordResponse, AlertDisposalResponse,
    HandleAlertRequest, AssignAlertRequest, BatchHandleRequest,
    DashboardSummary, DashboardItem, DrillDownRequest, ExportRequest,
    AlertCommentResponse, AlertCommentRequest, ReviewQueryRequest,
    ReviewResponse, ReviewSummary, EscalationResult
)
from app.services import NotificationService, run_all_checks, run_overdue_check
from app.services.rules_engine import run_escalation_check
from app.models import Alert, AlertPushRecord, AlertDisposal, TurnoverTask, Box, AlertComment

router = APIRouter(prefix="/api/alerts", tags=["提醒管理"])

ALLOWED_BATCH_TYPES = {"超期未回", "温控异常"}


@router.get("", response_model=List[AlertResponse], summary="查询提醒列表")
def get_alerts(
    role: Optional[str] = Query(None, description="按角色筛选"),
    is_handled: Optional[bool] = Query(None, description="是否已处理"),
    alert_type: Optional[str] = Query(None, description="按异常类型筛选"),
    assigned_to: Optional[str] = Query(None, description="按当前归属角色筛选"),
    is_escalated: Optional[bool] = Query(None, description="是否已升级"),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if role:
        query = query.filter(Alert.target_roles.contains(role))
    if is_handled is not None:
        query = query.filter(Alert.is_handled == is_handled)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if assigned_to:
        query = query.filter(Alert.current_owner_role == assigned_to)
    if is_escalated is not None:
        query = query.filter(Alert.is_escalated == is_escalated)
    return query.order_by(Alert.created_at.desc()).all()


@router.get("/export", summary="处置复盘导出（CSV）")
def export_alerts(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    alert_type: Optional[str] = Query(None, description="异常类型筛选"),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)

    if start_date:
        from datetime import datetime as dt
        try:
            sd = dt.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Alert.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        from datetime import datetime as dt
        try:
            ed = dt.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Alert.created_at <= ed)
        except ValueError:
            pass
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)

    alerts = query.order_by(Alert.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "提醒编号", "箱号", "异常类型", "严重程度", "责任节点",
        "建议动作", "内容", "目标角色", "当前归属角色", "当前归属人",
        "是否已处理", "处理人", "处理时间", "处理备注",
        "创建时间", "最近推送时间",
        "推送记录(角色/渠道/状态/时间)",
        "转派记录(从谁/到谁/时间)",
        "评论记录(人/时间/内容)",
        "附件记录(文件名/上传人/时间)",
        "处理时长(分钟)"
    ])

    for a in alerts:
        push_records = db.query(AlertPushRecord).filter(
            AlertPushRecord.alert_id == a.id
        ).order_by(AlertPushRecord.pushed_at.asc()).all()
        push_str = "; ".join([
            f"{pr.recipient_name}({pr.recipient_role})/{pr.push_channel}/{pr.status}/{pr.pushed_at.strftime('%Y-%m-%d %H:%M')}"
            for pr in push_records
        ]) if push_records else ""

        assign_disposals = db.query(AlertDisposal).filter(
            AlertDisposal.alert_id == a.id,
            AlertDisposal.disposal_type == "assign"
        ).order_by(AlertDisposal.disposed_at.asc()).all()
        assign_str = "; ".join([
            f"{d.operator_from_name or d.operator_name}({d.operator_from_role or d.operator_role}) -> {d.assigned_to_name}({d.assigned_to_role})/{d.disposed_at.strftime('%Y-%m-%d %H:%M')}"
            for d in assign_disposals
        ]) if assign_disposals else ""

        from app.models import AlertComment
        comments = db.query(AlertComment).filter(
            AlertComment.alert_id == a.id,
            AlertComment.comment_type == "comment"
        ).order_by(AlertComment.created_at.asc()).all()
        comment_str = "; ".join([
            f"{c.operator_name}({c.operator_role})/{c.created_at.strftime('%Y-%m-%d %H:%M')}: {c.content}"
            for c in comments if c.content
        ]) if comments else ""

        attachments = db.query(AlertComment).filter(
            AlertComment.alert_id == a.id,
            AlertComment.comment_type == "attachment"
        ).order_by(AlertComment.created_at.asc()).all()
        attach_str = "; ".join([
            f"{c.attachment_name}/{c.operator_name}({c.operator_role})/{c.created_at.strftime('%Y-%m-%d %H:%M')}"
            for c in attachments if c.attachment_name
        ]) if attachments else ""

        duration = ""
        if a.is_handled and a.handled_at and a.created_at:
            duration = str(round((a.handled_at - a.created_at).total_seconds() / 60, 1))
        elif not a.is_handled and a.created_at:
            duration = str(round((datetime.now() - a.created_at).total_seconds() / 60, 1))

        writer.writerow([
            a.alert_no,
            a.box_no or "",
            a.alert_type,
            a.severity,
            a.responsible_node,
            a.suggested_action,
            a.content,
            a.target_roles,
            a.current_owner_role or "",
            a.current_owner_name or "",
            "是" if a.is_handled else "否",
            a.handled_by or "",
            a.handled_at.strftime("%Y-%m-%d %H:%M") if a.handled_at else "",
            a.handled_note or "",
            a.created_at.strftime("%Y-%m-%d %H:%M"),
            a.last_pushed_at.strftime("%Y-%m-%d %H:%M") if a.last_pushed_at else "",
            push_str,
            assign_str,
            comment_str,
            attach_str,
            duration
        ])

    output.seek(0)
    filename = f"alert_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


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


@router.get("/dashboard/drill-down", summary="责任节点看板-下钻明细")
def get_dashboard_drill_down(
    dimension: str = Query(..., description="维度: customer/route/box_no/alert_type"),
    dimension_value: str = Query(..., description="维度值"),
    db: Session = Depends(get_db)
):
    query = db.query(Alert).filter(Alert.is_handled == False)

    if dimension == "alert_type":
        query = query.filter(Alert.alert_type == dimension_value)
    elif dimension == "box_no":
        query = query.filter(Alert.box_no == dimension_value)
    elif dimension in ("customer", "route"):
        alert_ids = []
        all_pending = query.all()
        for alert in all_pending:
            if not alert.box_no:
                continue
            task = db.query(TurnoverTask).filter(
                TurnoverTask.box_no == alert.box_no,
                TurnoverTask.status.notin_(["returned"]),
                TurnoverTask.is_duplicate == False
            ).order_by(TurnoverTask.id.desc()).first()
            if task:
                val = getattr(task, dimension, None)
                if val == dimension_value:
                    alert_ids.append(alert.id)
        query = db.query(Alert).filter(Alert.id.in_(alert_ids))
    else:
        return {"alerts": [], "total": 0}

    alerts = query.order_by(Alert.created_at.desc()).all()
    result = []
    for a in alerts:
        a_dict = AlertResponse.model_validate(a).model_dump()
        result.append(a_dict)

    return {
        "dimension": dimension,
        "dimension_value": dimension_value,
        "total": len(result),
        "alerts": result
    }


@router.post("/batch-handle", summary="批量处理提醒（仅超期未回+温控异常）")
def batch_handle_alerts(req: BatchHandleRequest, db: Session = Depends(get_db)):
    now = datetime.now()
    processed = 0
    skipped = 0
    skipped_ids = []
    not_allowed = 0
    not_allowed_ids = []

    for alert_id in req.alert_ids:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            skipped += 1
            skipped_ids.append({"id": alert_id, "reason": "提醒不存在"})
            continue
        if alert.is_handled:
            skipped += 1
            skipped_ids.append({"id": alert_id, "reason": "已处理"})
            continue
        if alert.alert_type not in ALLOWED_BATCH_TYPES:
            not_allowed += 1
            not_allowed_ids.append({"id": alert_id, "reason": f"类型'{alert.alert_type}'不允许批量处理"})
            continue
        if alert.box_no:
            box = db.query(Box).filter(Box.box_no == alert.box_no).first()
            if box and box.status == "idle":
                skipped += 1
                skipped_ids.append({"id": alert_id, "reason": "箱体已回仓"})
                continue

        prev_owner_role = alert.current_owner_role
        prev_owner_name = alert.current_owner_name
        alert.is_handled = True
        alert.handled_by = req.handled_by
        alert.handled_at = now
        alert.handled_note = req.handled_note
        alert.is_read = True
        alert.current_owner_role = req.handled_by
        alert.current_owner_name = req.handled_by
        alert.assigned_at = now
        db.flush()

        disposal = AlertDisposal(
            alert_id=alert.id,
            alert_no=alert.alert_no,
            disposal_type="handle",
            operator_name=req.handled_by,
            operator_role=prev_owner_role or "operator",
            disposal_note=req.handled_note,
            operator_from_role=prev_owner_role,
            operator_from_name=prev_owner_name,
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
        "skipped_ids": skipped_ids,
        "not_allowed": not_allowed,
        "not_allowed_ids": not_allowed_ids
    }


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


@router.post("/check/escalation", response_model=List[EscalationResult], summary="手动执行超时升级检查")
def run_escalation(db: Session = Depends(get_db)):
    escalated_alerts = run_escalation_check(db)
    result = []
    for alert in escalated_alerts:
        hours_overdue = (datetime.now() - alert.assigned_at).total_seconds() / 3600 if alert.assigned_at else 0
        result.append(EscalationResult(
            alert_id=alert.id,
            alert_no=alert.alert_no,
            box_no=alert.box_no,
            previous_owner_role=alert.current_owner_role,
            escalated_to=alert.escalated_to or "manager",
            hours_overdue=round(hours_overdue, 1)
        ))
    return result


@router.post("/review/query", response_model=ReviewResponse, summary="处置复盘多维度查询")
def review_query(req: ReviewQueryRequest, db: Session = Depends(get_db)):
    query = db.query(Alert)

    if req.start_date:
        try:
            sd = datetime.strptime(req.start_date, "%Y-%m-%d")
            query = query.filter(Alert.created_at >= sd)
        except ValueError:
            pass
    if req.end_date:
        try:
            ed = datetime.strptime(req.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Alert.created_at <= ed)
        except ValueError:
            pass
    if req.alert_type:
        query = query.filter(Alert.alert_type == req.alert_type)
    if req.is_handled is not None:
        query = query.filter(Alert.is_handled == req.is_handled)

    alerts = query.all()

    if req.customer or req.route:
        box_no_to_task = {}
        alert_ids = []
        for alert in alerts:
            if not alert.box_no:
                continue
            if alert.box_no not in box_no_to_task:
                task = db.query(TurnoverTask).filter(
                    TurnoverTask.box_no == alert.box_no,
                    TurnoverTask.status.notin_(["returned"]),
                    TurnoverTask.is_duplicate == False
                ).order_by(TurnoverTask.id.desc()).first()
                box_no_to_task[alert.box_no] = task
            task = box_no_to_task[alert.box_no]
            if not task:
                continue
            if req.customer and task.customer != req.customer:
                continue
            if req.route and task.route != req.route:
                continue
            alert_ids.append(alert.id)
        alerts = [a for a in alerts if a.id in alert_ids]

    total_count = len(alerts)
    pending_count = sum(1 for a in alerts if not a.is_handled)
    handled_count = sum(1 for a in alerts if a.is_handled)
    escalated_count = sum(1 for a in alerts if a.is_escalated)
    overdue_count = sum(1 for a in alerts if a.alert_type == "超期未回")
    temp_abnormal_count = sum(1 for a in alerts if a.alert_type == "温控异常")
    complaint_count = sum(1 for a in alerts if a.alert_type == "客户投诉")
    duplicate_count = sum(1 for a in alerts if a.alert_type == "同箱重复出库")

    total_minutes = 0
    for a in alerts:
        if a.is_handled and a.handled_at and a.created_at:
            total_minutes += (a.handled_at - a.created_at).total_seconds() / 60
        elif not a.is_handled and a.created_at:
            total_minutes += (datetime.now() - a.created_at).total_seconds() / 60
    avg_processing_minutes = round(total_minutes / total_count, 1) if total_count > 0 else 0

    high_occupation_count = 0
    if req.customer:
        from app.services.rules_engine import check_customer_high_occupation
        is_high, count = check_customer_high_occupation(db, req.customer)
        if is_high:
            high_occupation_count = 1

    summary = ReviewSummary(
        total_count=total_count,
        pending_count=pending_count,
        handled_count=handled_count,
        avg_processing_minutes=avg_processing_minutes,
        escalated_count=escalated_count,
        overdue_count=overdue_count,
        temp_abnormal_count=temp_abnormal_count,
        complaint_count=complaint_count,
        duplicate_count=duplicate_count,
        high_occupation_count=high_occupation_count
    )

    alert_responses = [AlertResponse.model_validate(a) for a in sorted(alerts, key=lambda x: x.created_at, reverse=True)]

    return ReviewResponse(
        summary=summary,
        alerts=alert_responses,
        total=total_count
    )


@router.get("/comments", response_model=List[AlertCommentResponse], summary="查询所有评论")
def get_all_comments(db: Session = Depends(get_db)):
    return db.query(AlertComment).order_by(AlertComment.created_at.desc()).all()


@router.post("/comments", response_model=AlertCommentResponse, summary="新增评论")
def create_comment(req: AlertCommentRequest, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == req.alert_id).first()
    if not alert:
        return None

    comment = AlertComment(
        alert_id=req.alert_id,
        alert_no=alert.alert_no,
        comment_type=req.comment_type,
        operator_name=req.operator_name,
        operator_role=req.operator_role,
        content=req.content,
        attachment_name=req.attachment_name,
        attachment_url=req.attachment_url,
        attachment_size=req.attachment_size
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/{alert_id}", summary="查询提醒详情（含推送记录+处置记录+评论）")
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
    comments = db.query(AlertComment).filter(
        AlertComment.alert_id == alert_id
    ).order_by(AlertComment.created_at.desc()).all()
    return {
        "alert": AlertResponse.model_validate(alert).model_dump(),
        "push_records": [AlertPushRecordResponse.model_validate(r).model_dump() for r in push_records],
        "disposals": [AlertDisposalResponse.model_validate(d).model_dump() for d in disposals],
        "comments": [AlertCommentResponse.model_validate(c).model_dump() for c in comments]
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


@router.get("/{alert_id}/comments", response_model=List[AlertCommentResponse], summary="查询提醒评论")
def get_alert_comments(alert_id: int, db: Session = Depends(get_db)):
    return db.query(AlertComment).filter(
        AlertComment.alert_id == alert_id
    ).order_by(AlertComment.created_at.desc()).all()


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
        disp = db.query(AlertDisposal).filter(AlertDisposal.alert_id == alert_id).order_by(AlertDisposal.id.desc()).first()
        return disp
    prev_owner_role = alert.current_owner_role
    prev_owner_name = alert.current_owner_name
    now = datetime.now()
    alert.is_handled = True
    alert.handled_by = req.handled_by
    alert.handled_at = now
    alert.handled_note = req.handled_note
    alert.is_read = True
    alert.current_owner_role = req.handled_by
    alert.current_owner_name = req.handled_by
    alert.assigned_at = now
    db.flush()
    disposal = AlertDisposal(
        alert_id=alert.id,
        alert_no=alert.alert_no,
        disposal_type="handle",
        operator_name=req.handled_by,
        operator_role=prev_owner_role or "operator",
        disposal_note=req.handled_note,
        operator_from_role=prev_owner_role,
        operator_from_name=prev_owner_name,
        disposal_result=req.disposal_result or "已跟进处理",
        disposed_at=now
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
    prev_owner_role = alert.current_owner_role
    prev_owner_name = alert.current_owner_name
    now = datetime.now()
    alert.assigned_to = req.assigned_to_role
    alert.current_owner_role = req.assigned_to_role
    alert.current_owner_name = req.assigned_to_name
    alert.is_read = True
    alert.assigned_at = now
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
        operator_from_role=prev_owner_role or req.operator_role,
        operator_from_name=prev_owner_name or req.operator_name,
        disposal_result=f"从 {prev_owner_name or req.operator_name}({prev_owner_role or req.operator_role}) 转派给 {req.assigned_to_name}({req.assigned_to_role})",
        disposed_at=now
    )
    db.add(disposal)
    db.commit()
    db.refresh(disposal)
    return disposal


def _calc_dashboard_for_dimension(db: Session, dimension: str, alert_column,
                                   task_column=None) -> List[DashboardItem]:
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
