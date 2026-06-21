from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.database import engine, Base, SessionLocal
from app.routers import turnover_router, alerts_router, admin_router
from app.models import SystemConfig, CustomerTurnoverConfig, AlertRecipient

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="低温箱周转异常监控服务",
    description="面向企业订单系统、车载温度系统和客服系统调用的统一箱体状态判断和提醒服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(turnover_router)
app.include_router(alerts_router)
app.include_router(admin_router)

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    return {
        "service": "低温箱周转异常监控服务",
        "version": "1.0.0",
        "docs": "/docs",
        "admin": "/static/index.html"
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


def init_default_configs():
    db = SessionLocal()
    try:
        default_configs = [
            ("default_overdue_days", "7", "默认逾期天数"),
            ("min_temperature", "2", "最低温度阈值(°C)"),
            ("max_temperature", "8", "最高温度阈值(°C)"),
            ("customer_high_occupation_threshold", "10", "客户高占用阈值(箱)"),
            ("escalation_timeout_hours_dispatch", "24", "调度角色超时升级阈值(小时)"),
            ("escalation_timeout_hours_warehouse", "24", "仓库角色超时升级阈值(小时)"),
            ("escalation_timeout_hours_customer_service", "12", "客服角色超时升级阈值(小时)"),
            ("escalation_timeout_hours_manager", "48", "管理角色超时升级阈值(小时)"),
        ]
        for key, value, desc in default_configs:
            existing = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
            if not existing:
                db.add(SystemConfig(config_key=key, config_value=value, description=desc))

        default_customers = [
            ("连锁超市A", 7, "标准周转周期"),
            ("餐饮连锁B", 5, "短周期客户"),
        ]
        for name, days, desc in default_customers:
            existing = db.query(CustomerTurnoverConfig).filter(
                CustomerTurnoverConfig.customer_name == name
            ).first()
            if not existing:
                db.add(CustomerTurnoverConfig(
                    customer_name=name, turnover_days=days, description=desc
                ))

        default_recipients = [
            ("张调度", "dispatch", "13800138001", None, "超期未回,同箱重复出库,客户高占用", True),
            ("李仓管", "warehouse", "13800138002", None, "同箱重复出库", True),
            ("王客服", "customer_service", "13800138003", None, "温控异常,客户投诉", True),
        ]
        for name, role, phone, email, alert_types, is_active in default_recipients:
            existing = db.query(AlertRecipient).filter(
                AlertRecipient.name == name, AlertRecipient.role == role
            ).first()
            if not existing:
                db.add(AlertRecipient(
                    name=name, role=role, phone=phone, email=email,
                    alert_types=alert_types, is_active=is_active
                ))

        db.commit()
    finally:
        db.close()


init_default_configs()


@app.on_event("startup")
async def startup_event():
    init_default_configs()
