import requests
BASE = "http://localhost:8000/api"

print("=== 验证服务 ===")
r = requests.get(f"{BASE}/alerts?alert_type=超期未回&is_handled=false")
print(f"alerts API: status={r.status_code}, len={len(r.json())}")
if r.status_code != 200:
    print(f"Error: {r.text[:200]}")

print("\n=== 测试下钻 ===")
for t in ["超期未回", "温控异常"]:
    r2 = requests.get(f"{BASE}/alerts/dashboard/drill-down",
                    params={"dimension": "alert_type", "dimension_value": t})
    print(f"drill-down {t}: status={r2.status_code}, total={r2.json().get('total')}")
    if r2.status_code != 200:
        print(f"Error: {r2.text[:200]}")

print("\n=== 测试复盘查询 ===")
r3 = requests.post(f"{BASE}/alerts/review/query", json={"is_handled": False})
print(f"review/query: status={r3.status_code}, total={r3.json().get('total')}")
if r3.status_code == 200:
    print(f"  summary keys: {list(r3.json().get('summary', {}).keys())}")
else:
    print(f"Error: {r3.text[:500]}")

print("\n=== 测试升级检查 ===")
r4 = requests.post(f"{BASE}/alerts/check/escalation")
print(f"escalation check: status={r4.status_code}")
if r4.status_code == 200:
    print(f"  escalated count={len(r4.json().get('escalated', []))}")
else:
    print(f"Error: {r4.text[:500]}")

print("\n=== 测试已升级筛选 ===")
r5 = requests.get(f"{BASE}/alerts", params={"is_escalated": "true"})
print(f"alerts is_escalated: status={r5.status_code}, len={len(r5.json())}")

print("\n=== 测试CSV导出 ===")
r6 = requests.get(f"{BASE}/alerts/export")
print(f"export: status={r6.status_code}, content-type={r6.headers.get('content-type')}")
if r6.status_code == 200:
    lines = r6.text.strip().split("\n")
    print(f"  rows={len(lines)}, has 评论: {'评论记录' in lines[0]}, has 附件: {'附件记录' in lines[0]}")

print("\nALL API TESTS DONE!")
