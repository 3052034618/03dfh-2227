import requests
BASE = "http://localhost:8000/api"

print("=== 1. 验证所有API返回状态 ===")

# 1. 提醒列表（含is_escalated筛选）
r = requests.get(f"{BASE}/alerts", params={"is_handled": "false", "is_escalated": "false"})
print(f"alerts list: status={r.status_code}, count={len(r.json())}")
assert r.status_code == 200
assert len(r.json()) >= 1
# 检查新字段
first = r.json()[0]
for field in ["is_escalated", "current_owner_role", "current_owner_name", "assigned_at"]:
    assert field in first, f"缺少字段 {field}"
print(f"  新字段存在: is_escalated={first['is_escalated']}, current_owner={first['current_owner_role']}")

# 2. 下钻 - 所有类型
all_types = ["超期未回", "温控异常", "客户投诉", "同箱重复出库", "客户高占用"]
for t in all_types:
    r = requests.get(f"{BASE}/alerts/dashboard/drill-down",
                    params={"dimension": "alert_type", "dimension_value": t})
    assert r.status_code == 200, f"{t} 下钻返回 {r.status_code}"
    d = r.json()
    assert "alerts" in d and "total" in d, f"{t} 返回结构错误"
    print(f"  drill-down {t}: status=200, total={d['total']}")

# 3. 复盘查询
r = requests.post(f"{BASE}/alerts/review/query", json={
    "is_handled": False,
    "alert_type": "超期未回"
})
assert r.status_code == 200
d = r.json()
print(f"review/query: status=200, total={d['total']}")
assert "summary" in d
assert d["summary"]["total_count"] >= 1
print(f"  summary keys: {list(d['summary'].keys())}")

# 4. 评论API
alerts = requests.get(f"{BASE}/alerts?alert_type=超期未回&is_handled=false").json()
if alerts:
    aid = alerts[0]["id"]
    # 发表评论
    r = requests.post(f"{BASE}/alerts/comments", json={
        "alert_id": aid,
        "comment_type": "comment",
        "operator_name": "测试员",
        "operator_role": "dispatch",
        "content": "测试评论"
    })
    assert r.status_code == 200
    print(f"post comment: status=200, id={r.json()['id']}")

    # 查评论列表
    r = requests.get(f"{BASE}/alerts/{aid}/comments")
    assert r.status_code == 200
    print(f"get comments: status=200, count={len(r.json())}")

    # 查提醒详情含评论
    r = requests.get(f"{BASE}/alerts/{aid}")
    assert r.status_code == 200
    d = r.json()
    assert "comments" in d
    print(f"alert detail has comments: count={len(d['comments'])}")

# 5. 超时升级
r = requests.post(f"{BASE}/alerts/check/escalation")
assert r.status_code == 200
result = r.json()
print(f"escalation check: status=200, escalated_count={len(result) if isinstance(result, list) else len(result.get('escalated', []))}")
if isinstance(result, list) and result:
    print(f"  first escalated: alert_id={result[0]['alert_id']}, escalated_to={result[0]['escalated_to']}")

# 6. 已升级筛选
r = requests.get(f"{BASE}/alerts", params={"is_escalated": "true"})
assert r.status_code == 200
print(f"filter by is_escalated=true: status=200, count={len(r.json())}")

# 7. CSV导出含评论/附件列
r = requests.get(f"{BASE}/alerts/export")
assert r.status_code == 200
assert "text/csv" in r.headers["content-type"]
lines = r.text.strip().split("\n")
header = lines[0]
print(f"export: rows={len(lines)}")
print(f"  has评论列: {'评论记录' in header}")
print(f"  has附件列: {'附件记录' in header}")
assert "评论记录" in header and "附件记录" in header

# 8. 时间线含评论事件
if alerts:
    box = alerts[0]["box_no"]
    r = requests.get(f"{BASE}/turnover/timeline/{box}")
    assert r.status_code == 200
    d = r.json()
    event_types = [e["event_type"] for e in d["events"]]
    print(f"timeline for {box}: total_events={d['total_events']}")
    print(f"  has评论事件: {any('提醒评论' in t for t in event_types)}")
    print(f"  has附件事件: {any('提醒附件' in t for t in event_types)}")

print("\n" + "="*60)
print("✅ ALL API TESTS PASSED!")
print("="*60)
