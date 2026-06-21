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
