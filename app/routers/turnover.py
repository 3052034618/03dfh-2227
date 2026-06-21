from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas import (
    OutboundRequest, OutboundResponse,
    SignRequest, ReturnRequest,
    TemperatureRequest, ComplaintRequest,
    HandoverRecordResponse
)
from app.services import TurnoverService

router = APIRouter(prefix="/api/turnover", tags=["周转管理"])


@router.post("/outbound", response_model=OutboundResponse, summary="订单出库")
def outbound(request: OutboundRequest, db: Session = Depends(get_db)):
    """
    订单出库时调用，接收箱号、客户、线路和预计归还日期，生成周转任务
    """
    service = TurnoverService(db)
    result = service.process_outbound(
        box_no=request.box_no,
        customer=request.customer,
        route=request.route,
        expected_return_date=request.expected_return_date,
        operator=request.operator
    )
    return result["task"]


@router.post("/sign", summary="签收回传")
def sign(request: SignRequest, db: Session = Depends(get_db)):
    """
    外部系统回传签收信息
    """
    service = TurnoverService(db)
    result = service.process_sign(
        box_no=request.box_no,
        location=request.location,
        operator=request.operator,
        remark=request.remark
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/return", summary="回仓回传")
def return_box(request: ReturnRequest, db: Session = Depends(get_db)):
    """
    外部系统回传回仓信息
    """
    service = TurnoverService(db)
    result = service.process_return(
        box_no=request.box_no,
        location=request.location,
        operator=request.operator,
        remark=request.remark
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/temperature", summary="温度数据回传")
def temperature(request: TemperatureRequest, db: Session = Depends(get_db)):
    """
    车载温度系统回传温度数据，自动判断是否越界
    """
    service = TurnoverService(db)
    result = service.process_temperature(
        box_no=request.box_no,
        temperature=request.temperature,
        recorded_at=request.recorded_at
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/complaint", summary="客服投诉回传")
def complaint(request: ComplaintRequest, db: Session = Depends(get_db)):
    """
    客服系统回传投诉信息
    """
    service = TurnoverService(db)
    result = service.process_complaint(
        box_no=request.box_no,
        customer=request.customer,
        complaint_type=request.complaint_type,
        description=request.description
    )
    return result


@router.get("/handover/{box_no}", response_model=List[HandoverRecordResponse], summary="查询箱体交接记录")
def get_handover_records(box_no: str, db: Session = Depends(get_db)):
    """
    查询指定箱体的交接记录
    """
    from app.models import HandoverRecord
    records = db.query(HandoverRecord).filter(
        HandoverRecord.box_no == box_no
    ).order_by(HandoverRecord.recorded_at.desc()).all()
    return records


@router.get("/timeline/{box_no}", summary="箱体全链路时间线")
def get_box_timeline(box_no: str, db: Session = Depends(get_db)):
    """
    获取箱体全链路时间线：出库、签收、温度、投诉、回仓、提醒、处置等事件串联
    """
    from app.models import (
        Box, HandoverRecord, TemperatureRecord,
        Complaint, Alert, TurnoverTask, AlertDisposal
    )

    box = db.query(Box).filter(Box.box_no == box_no).first()
    if not box:
        raise HTTPException(status_code=404, detail=f"箱体 {box_no} 不存在")

    events = []

    handovers = db.query(HandoverRecord).filter(
        HandoverRecord.box_no == box_no
    ).order_by(HandoverRecord.recorded_at.asc()).all()
    for h in handovers:
        icon_map = {"出库": "📦", "签收": "✅", "回仓": "🏠"}
        events.append({
            "event_type": f"交接-{h.record_type}",
            "event_time": h.recorded_at,
            "icon": icon_map.get(h.record_type, "📝"),
            "title": f"{h.record_type}",
            "description": f"地点: {h.location or '-'}，操作人: {h.operator or '-'}，备注: {h.remark or '-'}",
            "data": {"id": h.id, "location": h.location, "operator": h.operator, "remark": h.remark}
        })

    temps = db.query(TemperatureRecord).filter(
        TemperatureRecord.box_no == box_no
    ).order_by(TemperatureRecord.recorded_at.asc()).all()
    for t in temps:
        if t.is_abnormal:
            events.append({
                "event_type": "温度异常",
                "event_time": t.recorded_at,
                "icon": "🌡️",
                "title": f"温度越界: {t.temperature}°C",
                "description": f"温度 {t.temperature}°C 超出阈值范围，请排查温控设备",
                "severity": "danger",
                "data": {"id": t.id, "temperature": t.temperature}
            })

    complaints = db.query(Complaint).filter(
        Complaint.box_no == box_no
    ).order_by(Complaint.created_at.asc()).all()
    for c in complaints:
        events.append({
            "event_type": "客户投诉",
            "event_time": c.created_at,
            "icon": "📢",
            "title": f"{c.complaint_type}（客户: {c.customer}）",
            "description": c.description or "无详细描述",
            "severity": "warning",
            "data": {"id": c.id, "complaint_no": c.complaint_no, "complaint_type": c.complaint_type, "status": c.status}
        })

    alerts = db.query(Alert).filter(
        Alert.box_no == box_no
    ).order_by(Alert.created_at.asc()).all()
    for a in alerts:
        sev_map = {"high": "danger", "warning": "warning", "low": "info"}
        status_text = "已处理" if a.is_handled else ("已读" if a.is_read else "待处理")
        handled_info = ""
        if a.is_handled:
            handled_info = f"，处理人: {a.handled_by or '-'}，处理时间: {a.handled_at.strftime('%Y-%m-%d %H:%M') if a.handled_at else '-'}"
        events.append({
            "event_type": f"提醒-{a.alert_type}",
            "event_time": a.created_at,
            "icon": "🔔",
            "title": f"{a.alert_type} [{status_text}]",
            "description": f"责任节点: {a.responsible_node}，建议动作: {a.suggested_action}，推送给: {a.target_roles}{handled_info}",
            "severity": sev_map.get(a.severity, "info"),
            "data": {"id": a.id, "alert_no": a.alert_no, "alert_type": a.alert_type, "is_handled": a.is_handled, "is_read": a.is_read, "last_pushed_at": a.last_pushed_at.isoformat() if a.last_pushed_at else None, "handled_by": a.handled_by, "handled_at": a.handled_at.isoformat() if a.handled_at else None}
        })

    alert_ids = [a.id for a in alerts]
    if alert_ids:
        disposals = db.query(AlertDisposal).filter(
            AlertDisposal.alert_id.in_(alert_ids)
        ).order_by(AlertDisposal.disposed_at.asc()).all()
        for d in disposals:
            type_text = "处置" if d.disposal_type == "handle" else "转派"
            icon = "✏️" if d.disposal_type == "handle" else "➡️"
            desc_parts = [f"操作人: {d.operator_name}({d.operator_role})"]
            if d.operator_from_name:
                desc_parts.append(f"来源: {d.operator_from_name}({d.operator_from_role})")
            if d.disposal_result:
                desc_parts.append(f"结果: {d.disposal_result}")
            if d.disposal_note:
                desc_parts.append(f"备注: {d.disposal_note}")
            if d.assigned_to_name:
                desc_parts.append(f"转派给: {d.assigned_to_name}({d.assigned_to_role})")
            events.append({
                "event_type": f"提醒{type_text}",
                "event_time": d.disposed_at,
                "icon": icon,
                "title": f"提醒{type_text}: {d.disposal_result or type_text}",
                "description": "，".join(desc_parts),
                "severity": "info",
                "data": {"id": d.id, "alert_id": d.alert_id, "disposal_type": d.disposal_type, "operator_name": d.operator_name, "operator_role": d.operator_role, "operator_from_name": d.operator_from_name, "operator_from_role": d.operator_from_role, "disposal_note": d.disposal_note, "disposal_result": d.disposal_result, "assigned_to_name": d.assigned_to_name, "assigned_to_role": d.assigned_to_role}
            })

    tasks = db.query(TurnoverTask).filter(
        TurnoverTask.box_no == box_no
    ).order_by(TurnoverTask.created_at.asc()).all()
    for t in tasks:
        if t.is_duplicate:
            events.append({
                "event_type": "系统标记",
                "event_time": t.created_at,
                "icon": "⚠️",
                "title": f"重复出库任务: {t.task_no}",
                "description": f"该任务为重复出库，客户: {t.customer}，线路: {t.route}，请仓库核查",
                "severity": "warning",
                "data": {"task_no": t.task_no, "is_duplicate": True, "customer": t.customer}
            })

    events.sort(key=lambda e: e["event_time"])

    next_action = None
    if box.status == "temp_abnormal":
        next_action = "立即排查温控设备，联系客户确认货物情况，必要时安排换货"
    elif box.status == "overdue":
        next_action = "联系客户催还箱体，必要时安排上门回收"
    elif box.status == "signed" or box.status == "outbound" or box.status == "in_transit":
        next_action = "跟踪箱体状态，到期前提醒客户归还"
    elif box.status == "idle":
        next_action = "箱体已回仓入库，可正常调度使用"

    return {
        "box": {
            "box_no": box.box_no,
            "status": box.status,
            "current_customer": box.current_customer,
            "current_route": box.current_route
        },
        "total_events": len(events),
        "next_suggested_action": next_action,
        "events": events
    }
