import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api"
future = (datetime.now() + timedelta(days=3)).isoformat()

print("="*60)
print("验证剩余3个功能（快速版）")
print("="*60)

# ============ 测试3: 同箱重复出库任务标记 ============
print("\n[3] 测试同箱重复出库任务标记...")
box = "TEST-DUP-001"
r1 = requests.post(f"{BASE_URL}/turnover/outbound", json={
    "box_no": box, "customer": "客户A", "route": "线路1",
    "expected_return_date": future
}).json()
r2 = requests.post(f"{BASE_URL}/turnover/outbound", json={
    "box_no": box, "customer": "客户B", "route": "线路2",
    "expected_return_date": future
}).json()
tasks = requests.get(f"{BASE_URL}/admin/tasks").json()
t1 = next(t for t in tasks if t["task_no"] == r1["task_no"])
t2 = next(t for t in tasks if t["task_no"] == r2["task_no"])
print(f"  任务1 is_duplicate={t1.get('is_duplicate')} (应为False)")
print(f"  任务2 is_duplicate={t2.get('is_duplicate')} (应为True)")
print(f"  任务2 duplicate_of_task_id={t2.get('duplicate_of_task_id')} (应关联任务1 id={t1['id']})")
assert t1.get("is_duplicate") == False and t2.get("is_duplicate") == True
assert t2.get("duplicate_of_task_id") == t1["id"]
print("  ✅ 通过!")

# ============ 测试4: 温度越界状态稳定 ============
print("\n[4] 测试温度越界状态稳定转换...")
box = "TEST-TEMP-001"
requests.post(f"{BASE_URL}/turnover/outbound", json={
    "box_no": box, "customer": "温控客户", "route": "线路A",
    "expected_return_date": future
})
# 温度越界
requests.post(f"{BASE_URL}/turnover/temperature", json={
    "box_no": box, "temperature": 15.0
})
s1 = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()["status"]
print(f"  温度越界后: status={s1} (应为temp_abnormal)")
assert s1 == "temp_abnormal"

# 签收不应覆盖
requests.post(f"{BASE_URL}/turnover/sign", json={
    "box_no": box, "location": "某地"
})
s2 = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()["status"]
print(f"  签收后: status={s2} (仍应为temp_abnormal)")
assert s2 == "temp_abnormal"

# 温控异常筛选能找到
filtered = requests.get(f"{BASE_URL}/admin/boxes?status=temp_abnormal").json()
found = any(b["box_no"] == box for b in filtered)
print(f"  温控异常筛选能查到: {found} (应为True)")
assert found

# 回仓恢复空闲
requests.post(f"{BASE_URL}/turnover/return", json={
    "box_no": box, "location": "总仓"
})
s3 = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()["status"]
print(f"  回仓后: status={s3} (应为idle)")
assert s3 == "idle"
print("  ✅ 通过!")

# ============ 测试5: 全链路时间线 ============
print("\n[5] 测试箱体全链路时间线...")
box = "TEST-TL-001"
requests.post(f"{BASE_URL}/turnover/outbound", json={
    "box_no": box, "customer": "时间线客户", "route": "北京-上海",
    "expected_return_date": future
})
requests.post(f"{BASE_URL}/turnover/outbound", json={  # 重复出库
    "box_no": box, "customer": "另一客户", "route": "北京-广州",
    "expected_return_date": future
})
requests.post(f"{BASE_URL}/turnover/sign", json={
    "box_no": box, "location": "上海配送站"
})
requests.post(f"{BASE_URL}/turnover/temperature", json={
    "box_no": box, "temperature": 5.0
})
requests.post(f"{BASE_URL}/turnover/temperature", json={  # 越界
    "box_no": box, "temperature": 12.5
})
requests.post(f"{BASE_URL}/turnover/complaint", json={
    "box_no": box, "customer": "时间线客户",
    "complaint_type": "温度异常", "description": "货物温度偏高"
})
requests.post(f"{BASE_URL}/turnover/return", json={
    "box_no": box, "location": "总仓"
})

tl = requests.get(f"{BASE_URL}/turnover/timeline/{box}").json()
events = tl["events"]
types = [e["event_type"] for e in events]
print(f"  事件数: {tl['total_events']}")
print(f"  事件类型: {types}")
required = ["出库", "签收", "温度异常", "客户投诉", "回仓",
            "同箱重复出库", "温控异常", "系统标记"]
missing = [r for r in required if not any(r in t for t in types)]
print(f"  缺失的事件类型: {missing} (应为空)")
assert len(missing) == 0

# 验证时间升序
times = [datetime.fromisoformat(e["event_time"].replace("Z", "")) for e in events]
sorted_ok = all(times[i] >= times[i-1] for i in range(1, len(times)))
print(f"  事件按时间升序: {sorted_ok} (应为True)")
assert sorted_ok
print(f"  建议下一步动作: {tl.get('next_suggested_action')}")
print("  ✅ 通过!")

print("\n" + "="*60)
print("🎉 所有3项剩余测试全部通过!")
print("="*60)
