import requests
BASE = "http://localhost:8000/api"

print("=== 1. 检查超时升级配置是否存在 ===")
from datetime import datetime, timedelta
future = (datetime.now() + timedelta(days=10)).isoformat()
past = (datetime.now() - timedelta(days=10)).isoformat()

for role in ["dispatch", "warehouse", "customer_service", "manager"]:
    key = f"escalation_timeout_hours_{role}"
    r = requests.get(f"{BASE}/admin/configs")
    configs = r.json()
    found = any(c["config_key"] == key for c in configs)
    val = next((c["config_value"] for c in configs if c["config_key"] == key), None)
    print(f"  {key}: found={found}, value={val}")

print("\n=== 2. 快速创建超期+温控异常，验证下钻 ===")
for i in range(2):
    box = f"BOX-QA{i:03d}"
    r = requests.post(f"{BASE}/turnover/outbound", json={
        "box_no": box, "customer": "QA客户", "route": "QA线路",
        "expected_return_date": past
    })
requests.post(f"{BASE}/alerts/check/overdue")

box = "BOX-QA-TEMP"
requests.post(f"{BASE}/turnover/outbound", json={
    "box_no": box, "customer": "QA客户", "route": "QA线路2",
    "expected_return_date": future
})
requests.post(f"{BASE}/turnover/temperature", json={
    "box_no": box, "temperature": 15.0
})

for t in ["超期未回", "温控异常"]:
    r = requests.get(f"{BASE}/alerts/dashboard/drill-down",
                    params={"dimension": "alert_type", "dimension_value": t})
    print(f"  下钻 {t}: status={r.status_code}, count={r.json()['total']}")

print("\n=== 3. 测试复盘查询 ===")
r = requests.post(f"{BASE}/alerts/review/query", json={
    "customer": "QA客户",
    "is_handled": False
})
d = r.json()
print(f"  status={r.status_code}")
print(f"  summary.total={d['summary']['total_count']}, pending={d['summary']['pending_count']}, avg_min={d['summary']['avg_processing_minutes']}")
print(f"  alerts count={d['total']}, first={d['alerts'][0]['alert_type'] if d['alerts'] else None}")

print("\n=== 4. 测试评论API ===")
alerts = requests.get(f"{BASE}/alerts?alert_type=温控异常&is_handled=false").json()
if alerts:
    aid = alerts[0]["id"]
    r = requests.post(f"{BASE}/alerts/comments", json={
        "alert_id": aid,
        "comment_type": "comment",
        "operator_name": "QA测试员",
        "operator_role": "dispatch",
        "content": "这是一条测试评论"
    })
    print(f"  发表评论: status={r.status_code}, content={r.json().get('content')}")

    r = requests.get(f"{BASE}/alerts/{aid}/comments")
    print(f"  获取评论: status={r.status_code}, count={len(r.json())}")

print("\n=== 5. 测试超时升级 ===")
# 把调度超时阈值改成1小时
requests.post(f"{BASE}/admin/configs", json={
    "config_key": "escalation_timeout_hours_dispatch",
    "config_value": "1"
})
r = requests.post(f"{BASE}/alerts/check/escalation")
print(f"  升级检查: status={r.status_code}, escalated_count={len(r.json().get('escalated', []))}")

# 筛选已升级的
r2 = requests.get(f"{BASE}/alerts", params={"is_escalated": "true", "is_handled": "false"})
print(f"  已升级筛选: status={r2.status_code}, count={len(r2.json())}")
if r2.json():
    print(f"    first: {r2.json()[0]['alert_no']}, owner={r2.json()[0]['current_owner_role']}, escalated={r2.json()[0]['is_escalated']}")

print("\n=== 6. 测试CSV导出 ===")
r = requests.get(f"{BASE}/alerts/export", params={"alert_type": "超期未回"})
print(f"  导出超期: status={r.status_code}, content-type={r.headers.get('content-type')}")
lines = r.text.strip().split("\n")
print(f"    rows={len(lines)}, header has 评论/附件: {'评论记录' in lines[0] and '附件记录' in lines[0]}")

print("\nALL API TESTS DONE!")
