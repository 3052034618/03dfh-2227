from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.models import Box, TurnoverTask, HandoverRecord, TemperatureRecord, Complaint
from app.services.rules_engine import (
    generate_no, check_duplicate_outbound, check_temperature_abnormal,
    check_customer_high_occupation, create_alert, get_active_tasks_by_box
)
from app.services.notification import NotificationService


class TurnoverService:
    def __init__(self, db: Session):
        self.db = db
        self.notification = NotificationService(db)

    def process_outbound(self, box_no: str, customer: str, route: str,
                         expected_return_date: datetime, operator: str = None) -> dict:
        existing_task = check_duplicate_outbound(self.db, box_no)
        is_duplicate = existing_task is not None

        box = self.db.query(Box).filter(Box.box_no == box_no).first()
        if not box:
            box = Box(box_no=box_no, status="outbound", current_customer=customer, current_route=route)
            self.db.add(box)
            self.db.flush()
        else:
            if box.status != "temp_abnormal":
                box.status = "outbound"
            box.current_customer = customer
            box.current_route = route
            self.db.flush()

        task = TurnoverTask(
            task_no=generate_no("TASK"),
            box_id=box.id,
            box_no=box_no,
            customer=customer,
            route=route,
            expected_return_date=expected_return_date,
            status="outbound",
            is_duplicate=is_duplicate,
            duplicate_of_task_id=existing_task.id if existing_task else None
        )
        self.db.add(task)
        self.db.flush()

        handover = HandoverRecord(
            box_id=box.id,
            box_no=box_no,
            task_id=task.id,
            record_type="出库",
            location=route,
            operator=operator,
            remark="订单出库" + ("（重复出库警告）" if is_duplicate else "")
        )
        self.db.add(handover)

        alerts = []

        if is_duplicate:
            extra = f"该箱体已有在途任务（{existing_task.task_no}，客户: {existing_task.customer}），新任务客户: {customer}"
            alert = create_alert(
                db=self.db,
                alert_type="同箱重复出库",
                severity="high",
                responsible_node="仓库",
                suggested_action="立即核查箱体状态，确认是否存在错发或系统数据异常",
                box_id=box.id,
                box_no=box_no,
                extra_info=extra,
                target_roles="warehouse,dispatch"
            )
            alerts.append(alert)
            self.notification.push_alert(alert)

        if not is_duplicate:
            is_high_occ, count = check_customer_high_occupation(self.db, customer)
            if is_high_occ:
                alert = create_alert(
                    db=self.db,
                    alert_type="客户高占用",
                    severity="warning",
                    responsible_node="调度",
                    suggested_action=f"评估客户 {customer} 的箱体占用情况，必要时催还或补充库存",
                    box_id=box.id,
                    box_no=box_no,
                    extra_info=f"客户当前占用箱体数: {count}（已去重）",
                    target_roles="dispatch,manager"
                )
                alerts.append(alert)
                self.notification.push_alert(alert)

        self.db.commit()
        self.db.refresh(task)

        return {
            "task": task,
            "duplicate_warning": is_duplicate,
            "duplicate_of_task_no": existing_task.task_no if existing_task else None,
            "alerts": alerts
        }

    def process_sign(self, box_no: str, location: str = None, operator: str = None,
                     remark: str = None) -> dict:
        box = self.db.query(Box).filter(Box.box_no == box_no).first()
        if not box:
            return {"success": False, "message": f"箱体 {box_no} 不存在"}

        active_tasks = get_active_tasks_by_box(self.db, box_no)
        if not active_tasks:
            return {"success": False, "message": f"箱体 {box_no} 无在途任务"}

        primary_tasks = [t for t in active_tasks if not t.is_duplicate]
        task = primary_tasks[0] if primary_tasks else active_tasks[0]
        task.status = "signed"

        if box.status != "temp_abnormal":
            box.status = "signed"

        handover = HandoverRecord(
            box_id=box.id,
            box_no=box_no,
            task_id=task.id,
            record_type="签收",
            location=location,
            operator=operator,
            remark=remark or "客户签收"
        )
        self.db.add(handover)

        self.db.commit()
        self.db.refresh(task)

        return {"success": True, "task": task}

    def process_return(self, box_no: str, location: str = None, operator: str = None,
                       remark: str = None) -> dict:
        box = self.db.query(Box).filter(Box.box_no == box_no).first()
        if not box:
            return {"success": False, "message": f"箱体 {box_no} 不存在"}

        active_tasks = get_active_tasks_by_box(self.db, box_no)
        if not active_tasks:
            return {"success": False, "message": f"箱体 {box_no} 无在途任务"}

        now = datetime.now()
        primary_tasks = [t for t in active_tasks if not t.is_duplicate]
        task = primary_tasks[0] if primary_tasks else active_tasks[0]

        for t in active_tasks:
            t.status = "returned"
            t.actual_return_date = now

        box.status = "idle"
        box.current_customer = None
        box.current_route = None

        handover = HandoverRecord(
            box_id=box.id,
            box_no=box_no,
            task_id=task.id,
            record_type="回仓",
            location=location or "仓库",
            operator=operator,
            remark=remark or "箱体回仓"
        )
        self.db.add(handover)

        self.db.commit()
        self.db.refresh(task)

        return {"success": True, "task": task, "closed_tasks": len(active_tasks)}

    def process_temperature(self, box_no: str, temperature: float,
                            recorded_at: datetime = None) -> dict:
        box = self.db.query(Box).filter(Box.box_no == box_no).first()
        if not box:
            return {"success": False, "message": f"箱体 {box_no} 不存在"}

        is_abnormal = check_temperature_abnormal(self.db, box.id, temperature)
        now = recorded_at or datetime.now()

        temp_record = TemperatureRecord(
            box_id=box.id,
            box_no=box_no,
            temperature=temperature,
            is_abnormal=is_abnormal,
            recorded_at=now
        )
        self.db.add(temp_record)

        alerts = []
        if is_abnormal:
            alert = create_alert(
                db=self.db,
                alert_type="温控异常",
                severity="high",
                responsible_node="客服",
                suggested_action="立即联系客户核实货物状态，排查温控设备故障，必要时安排换货",
                box_id=box.id,
                box_no=box_no,
                extra_info=f"当前温度: {temperature}°C，请核查温控设备",
                target_roles="customer_service,dispatch"
            )
            alerts.append(alert)
            self.notification.push_alert(alert)

            if box.status != "returned" and box.status != "idle":
                box.status = "temp_abnormal"

            active_tasks = get_active_tasks_by_box(self.db, box_no)
            for t in active_tasks:
                if t.status != "returned":
                    t.status = "temp_abnormal"

        self.db.commit()

        return {
            "success": True,
            "is_abnormal": is_abnormal,
            "alerts": alerts
        }

    def process_complaint(self, box_no: str, customer: str, complaint_type: str,
                          description: str = None) -> dict:
        box = self.db.query(Box).filter(Box.box_no == box_no).first()

        complaint = Complaint(
            complaint_no=generate_no("CMP"),
            box_no=box_no,
            customer=customer,
            complaint_type=complaint_type,
            description=description,
            status="pending"
        )
        self.db.add(complaint)
        self.db.flush()

        alerts = []
        if box:
            alert = create_alert(
                db=self.db,
                alert_type="客户投诉",
                severity="high",
                responsible_node="客服",
                suggested_action=f"跟进 {complaint_type} 投诉，联系客户核实情况并协调解决方案",
                box_id=box.id,
                box_no=box_no,
                extra_info=f"投诉类型: {complaint_type}, 客户: {customer}",
                target_roles="customer_service,manager"
            )
            alerts.append(alert)
            self.notification.push_alert(alert)

        self.db.commit()

        return {
            "success": True,
            "complaint": complaint,
            "alerts": alerts
        }
