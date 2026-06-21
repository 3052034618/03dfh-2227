from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.models import Alert, AlertRecipient, AlertPushRecord


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def push_alert(self, alert: Alert) -> dict:
        recipients = self._get_recipients(alert)
        results = []
        now = datetime.now()

        for recipient in recipients:
            result = self._send_notification(recipient, alert)
            self._create_push_record(alert, recipient, result, now)
            results.append(result)

        alert.last_pushed_at = now
        self.db.flush()

        return {
            "alert_id": alert.id,
            "alert_no": alert.alert_no,
            "pushed_to": len(results),
            "last_pushed_at": now.isoformat(),
            "results": results
        }

    def _create_push_record(self, alert: Alert, recipient: AlertRecipient,
                            result: dict, pushed_at: datetime):
        push_targets = []
        if recipient.phone:
            push_targets.append(f"sms:{recipient.phone}")
        if recipient.email:
            push_targets.append(f"email:{recipient.email}")
        if not push_targets:
            push_targets.append("system:in-app")

        for target in push_targets:
            channel = target.split(":")[0]
            record = AlertPushRecord(
                alert_id=alert.id,
                alert_no=alert.alert_no,
                recipient_id=recipient.id,
                recipient_name=recipient.name,
                recipient_role=recipient.role,
                push_channel=channel,
                push_target=target,
                status=result.get("status", "success"),
                error_message=result.get("error"),
                pushed_at=pushed_at
            )
            self.db.add(record)

    def _get_recipients(self, alert: Alert) -> List[AlertRecipient]:
        target_roles = alert.target_roles.split(",")
        recipients = self.db.query(AlertRecipient).filter(
            AlertRecipient.is_active == True,
            AlertRecipient.role.in_(target_roles)
        ).all()

        filtered = []
        for r in recipients:
            alert_types = r.alert_types.split(",")
            if alert.alert_type in alert_types or "all" in alert_types:
                filtered.append(r)

        return filtered

    def _send_notification(self, recipient: AlertRecipient, alert: Alert) -> dict:
        print(f"[推送提醒] 给 {recipient.name} ({recipient.role}): {alert.alert_type} - {alert.box_no}")

        if recipient.phone:
            print(f"  -> 短信发送至 {recipient.phone}: {alert.content[:50]}...")

        if recipient.email:
            print(f"  -> 邮件发送至 {recipient.email}")

        return {
            "recipient": recipient.name,
            "role": recipient.role,
            "status": "success",
            "sent_at": datetime.now().isoformat()
        }

    def get_unhandled_alerts(self, role: str = None) -> List[Alert]:
        query = self.db.query(Alert).filter(Alert.is_handled == False)
        if role:
            query = query.filter(Alert.target_roles.contains(role))
        return query.order_by(Alert.created_at.desc()).all()

    def mark_as_read(self, alert_id: int) -> Alert:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.is_read = True
            self.db.commit()
        return alert

    def mark_as_handled(self, alert_id: int) -> Alert:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.is_handled = True
            self.db.commit()
        return alert

    def get_push_records(self, alert_id: int) -> List[AlertPushRecord]:
        return self.db.query(AlertPushRecord).filter(
            AlertPushRecord.alert_id == alert_id
        ).order_by(AlertPushRecord.pushed_at.desc()).all()

    def push_alert_again(self, alert_id: int) -> dict:
        alert = self.db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return {"success": False, "message": "提醒不存在"}
        return self.push_alert(alert)
