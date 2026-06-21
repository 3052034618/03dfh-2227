from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.models import Alert, AlertRecipient


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def push_alert(self, alert: Alert) -> dict:
        recipients = self._get_recipients(alert)
        results = []

        for recipient in recipients:
            result = self._send_notification(recipient, alert)
            results.append(result)

        return {
            "alert_id": alert.id,
            "alert_no": alert.alert_no,
            "pushed_to": len(results),
            "results": results
        }

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
            "status": "sent",
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
