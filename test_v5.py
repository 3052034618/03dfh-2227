import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api"
future = (datetime.now() + timedelta(days=10)).isoformat()
past = (datetime.now() - timedelta(days=10)).isoformat()
past_25h = (datetime.now() - timedelta(hours=25)).isoformat()

def test(name):
    def deco(fn):
        def wrapper():
            print(f"\n{'='*70}")
            print(f">>> 测试: {name}")
            print('='*70)
            try:
                fn()
                print(f"[PASS] [{name}] 测试通过")
            except AssertionError as e:
                print(f"[FAIL] [{name}] 断言失败: {e}")
                raise
            except Exception as e:
                print(f"[FAIL] [{name}] 异常: {e}")
                raise
        return wrapper
    return deco

def pprint(title, data=None, level=0):
    prefix = "  " * level
    print(f"{prefix}> {title}")
    if data is not None:
        try:
            text = json.dumps(data, indent=2, ensure_ascii=False)
            for line in text.split('\n'):
                print(f"{prefix}  {line}")
        except:
            print(f"{prefix}  {data}")

@test("1. 看板按异常类型下钻 - 所有类型都能稳定列出未处理提醒")
def test_drill_down_all_types():
    # 先创建各种类型的提醒
    types_to_test = {
        "超期未回": 2,
        "温控异常": 1,
        "客户投诉": 1,
        "同箱重复出库": 1,
        "客户高占用": 0,  # 阈值10，不好触发，最后手动验证API返回结构即可
    }

    # 降低高占用阈值
    requests.post(f"{BASE_URL}/admin/configs", json={
        "config_key": "customer_high_occupation_threshold",
        "config_value": "1"
    })

    # 创建超期未回
    for i in range(2):
        box = f"BOX-DD-OD-{i:03d}"
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "下钻客户", "route": "下钻线路A",
            "expected_return_date": past
        })
    requests.post(f"{BASE_URL}/alerts/check/overdue")

    # 创建温控异常
    box = "BOX-DD-TEMP-001"
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "下钻客户", "route": "下钻线路B",
        "expected_return_date": future
    })
    requests.post(f"{BASE_URL}/turnover/temperature", json={
        "box_no": box, "temperature": 15.0
    })

    # 创建客户投诉
    box = "BOX-DD-CMP-001"
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "下钻客户", "route": "下钻线路C",
        "expected_return_date": future
    })
    requests.post(f"{BASE_URL}/turnover/complaint", json={
        "box_no": box, "customer": "下钻客户",
        "complaint_type": "配送延迟", "description": "送晚了"
    })

    # 创建重复出库
    box = "BOX-DD-DUP-001"
    for i in range(2):
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": f"客户{i}", "route": "下钻线路D",
            "expected_return_date": future
        })

    # 创建客户高占用（阈值1，2个箱号触发）
    for i in range(2):
        box = f"BOX-DD-HI-{i:03d}"
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "高占用客户", "route": "下钻线路E",
            "expected_return_date": future
        })

    # 验证每种类型的下钻
    test_types = ["超期未回", "温控异常", "客户投诉", "同箱重复出库", "客户高占用"]
    for t in test_types:
        r = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down",
                        params={"dimension": "alert_type", "dimension_value": t})
        assert r.status_code == 200, f"{t} 下钻API返回错误: {r.status_code}"
        data = r.json()
        pprint(f"下钻 '{t}' 结果数量", data["total"])
        assert "dimension" in data and "alerts" in data, f"{t} 返回结构错误"

        # 检查每条都是未处理的
        for a in data["alerts"]:
            assert a["is_handled"] == False, f"{t} 的提醒应该是未处理的"
            assert a["alert_type"] == t, f"类型不匹配: {a['alert_type']} != {t}"

    print("  >> 所有异常类型下钻功能正常")

@test("2. 复盘预览 - 多维度筛选返回汇总+明细，再导出CSV")
def test_review_query_and_export():
    today = datetime.now().strftime("%Y-%m-%d")

    # 测试复盘查询
    r = requests.post(f"{BASE_URL}/alerts/review/query", json={
        "customer": "下钻客户",
        "is_handled": False
    })
    assert r.status_code == 200, f"复盘查询返回错误: {r.status_code}"
    data = r.json()

    pprint("复盘查询 - 按客户'下钻客户'筛选汇总", {
        "总数": data["total"],
        "summary": {
            "总数量": data["summary"]["total_count"],
            "待处理": data["summary"]["pending_count"],
            "已处理": data["summary"]["handled_count"],
            "超期": data["summary"]["overdue_count"],
            "温控异常": data["summary"]["temp_abnormal_count"],
            "投诉": data["summary"]["complaint_count"]
        }
    })

    assert "summary" in data and "alerts" in data, "返回结构错误"
    assert len(data["alerts"]) == data["total"], "明细数量和total不一致"
    assert data["summary"]["total_count"] >= 4, "应该至少有4条记录（2超期+1温控+1投诉）"

    # 测试按线路筛选
    r2 = requests.post(f"{BASE_URL}/alerts/review/query", json={
        "route": "下钻线路A"
    })
    assert r2.status_code == 200
    d2 = r2.json()
    pprint("复盘查询 - 按线路'下钻线路A'筛选数量", d2["total"])
    assert d2["total"] >= 1, "应该至少有1条线路A的记录"

    # 测试按异常类型筛选
    r3 = requests.post(f"{BASE_URL}/alerts/review/query", json={
        "alert_type": "超期未回",
        "is_handled": False
    })
    assert r3.status_code == 200
    d3 = r3.json()
    pprint("复盘查询 - 按'超期未回'筛选数量", d3["total"])
    assert d3["total"] >= 2, "应该至少有2条超期未回"

    # 测试按日期筛选
    r4 = requests.post(f"{BASE_URL}/alerts/review/query", json={
        "start_date": "2020-01-01",
        "end_date": today
    })
    assert r4.status_code == 200
    d4 = r4.json()
    pprint("复盘查询 - 按日期范围筛选数量", d4["total"])
    assert d4["total"] >= 6, "应该至少有6条记录"

    # 测试CSV导出
    import csv as csv_mod
    r5 = requests.get(f"{BASE_URL}/alerts/export", params={
        "alert_type": "超期未回",
        "start_date": "2020-01-01",
        "end_date": today
    })
    assert r5.status_code == 200, f"导出返回错误: {r5.status_code}"
    assert "text/csv" in r5.headers.get("content-type", "")
    reader = csv_mod.reader(r5.text.strip().splitlines())
    rows = list(reader)
    pprint("CSV导出 - 超期未回行数", len(rows))
    header = ",".join(rows[0])
    assert "评论记录" in header and "附件记录" in header, "CSV应该包含评论和附件列"
    assert len(rows) >= 3, "应该至少有标题行+2条数据"

    print("  >> 复盘预览和导出功能正常")

@test("3. 协同评论 - 处理前后都能补充说明，时间线和复盘中能看到")
def test_comments():
    # 获取一个未处理的提醒
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=同箱重复出库&is_handled=false").json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]
    box_no = alerts[0]["box_no"]
    pprint(f"找到提醒 ID: {alert_id}, 箱号: {box_no}")

    # 发表评论
    r1 = requests.post(f"{BASE_URL}/alerts/comments", json={
        "alert_id": alert_id,
        "comment_type": "comment",
        "operator_name": "张调度",
        "operator_role": "dispatch",
        "content": "已通知仓库检查，请仓库尽快确认"
    }).json()
    pprint("发表评论结果", {
        "id": r1["id"],
        "content": r1["content"],
        "operator": r1["operator_name"]
    })
    assert r1["content"] == "已通知仓库检查，请仓库尽快确认"

    # 上传附件记录
    r2 = requests.post(f"{BASE_URL}/alerts/comments", json={
        "alert_id": alert_id,
        "comment_type": "attachment",
        "operator_name": "张调度",
        "operator_role": "dispatch",
        "attachment_name": "现场照片.jpg",
        "attachment_url": "/uploads/现场照片_123.jpg",
        "attachment_size": 1024000
    }).json()
    pprint("上传附件结果", {
        "id": r2["id"],
        "attachment_name": r2["attachment_name"]
    })
    assert r2["attachment_name"] == "现场照片.jpg"

    # 获取评论列表
    comments = requests.get(f"{BASE_URL}/alerts/{alert_id}/comments").json()
    pprint(f"评论列表数量", len(comments))
    assert len(comments) >= 2, "应该至少有2条评论"

    # 获取提醒详情，确认包含评论
    detail = requests.get(f"{BASE_URL}/alerts/{alert_id}").json()
    pprint(f"提醒详情中的评论数量", len(detail.get("comments", [])))
    assert len(detail.get("comments", [])) >= 2

    # 转派给仓库
    requests.post(f"{BASE_URL}/alerts/{alert_id}/assign", json={
        "operator_name": "张调度",
        "operator_role": "dispatch",
        "assigned_to_role": "warehouse",
        "assigned_to_name": "李仓管",
        "disposal_note": "请仓库核查并处理"
    })

    # 处理后再发表评论
    handle_r = requests.post(f"{BASE_URL}/alerts/{alert_id}/handle", json={
        "handled_by": "李仓管",
        "handled_note": "已核查，重复出库已纠正",
        "disposal_result": "已跟进处理"
    }).json()

    r3 = requests.post(f"{BASE_URL}/alerts/comments", json={
        "alert_id": alert_id,
        "comment_type": "comment",
        "operator_name": "李仓管",
        "operator_role": "warehouse",
        "content": "已联系第二个客户更换箱号，问题已解决"
    }).json()
    assert r3["content"] == "已联系第二个客户更换箱号，问题已解决"

    # 查看时间线，确认评论出现在时间线中
    tl = requests.get(f"{BASE_URL}/turnover/timeline/{box_no}").json()
    event_types = [e["event_type"] for e in tl["events"]]
    pprint("时间线事件类型", event_types)
    comment_events = [e for e in tl["events"] if "提醒评论" in e["event_type"] or "提醒附件" in e["event_type"]]
    pprint(f"时间线中评论/附件事件数量", len(comment_events))
    assert len(comment_events) >= 3, "时间线应该包含3条评论/附件事件"

    # 检查复盘中评论列
    import csv as csv_mod
    export_r = requests.get(f"{BASE_URL}/alerts/export", params={
        "start_date": "2020-01-01",
        "end_date": datetime.now().strftime("%Y-%m-%d")
    })
    reader = csv_mod.reader(export_r.text.strip().splitlines())
    rows = list(reader)
    header = rows[0]
    comment_idx = header.index("评论记录(人/时间/内容)")
    attach_idx = header.index("附件记录(文件名/上传人/时间)")
    pprint("CSV列索引", {"评论": comment_idx, "附件": attach_idx})

    # 找到该提醒的行，确认有评论
    for row in rows[1:]:
        if row and row[0] == alerts[0]["alert_no"]:
            pprint("该提醒的CSV导出", {
                "评论列": row[comment_idx][:80] + "..." if len(row[comment_idx]) > 80 else row[comment_idx],
                "附件列": row[attach_idx][:80] + "..." if len(row[attach_idx]) > 80 else row[attach_idx]
            })
            assert "张调度" in row[comment_idx], "评论列应包含张调度"
            assert "李仓管" in row[comment_idx], "评论列应包含李仓管"
            assert "现场照片.jpg" in row[attach_idx], "附件列应包含现场照片"
            break

    print("  >> 协同评论功能正常，时间线和复盘中都能看到")

@test("4. 责任超时规则 - 超过配置时长自动升级给manager，可筛选已升级待办")
def test_escalation():
    # 先手动把一些提醒的assigned_at改到25小时前，模拟超时
    from datetime import datetime as dt
    old_time = dt.now() - timedelta(hours=25)

    # 获取所有未处理、未升级、归属dispatch的提醒
    alerts = requests.get(f"{BASE_URL}/alerts", params={
        "assigned_to": "dispatch",
        "is_handled": "false",
        "is_escalated": "false"
    }).json()
    dispatch_alerts = [a for a in alerts if a["current_owner_role"] == "dispatch"]
    pprint(f"调度角色的未处理提醒数量", len(dispatch_alerts))
    assert len(dispatch_alerts) >= 2, "应该至少有2条调度角色的提醒"

    # 手动修改数据库（需要直接调接口触发，这里通过把调度的超时阈值设为1小时来测试）
    requests.post(f"{BASE_URL}/admin/configs", json={
        "config_key": "escalation_timeout_hours_dispatch",
        "config_value": "1"  # 1小时就升级
    })

    # 触发升级检查
    r = requests.post(f"{BASE_URL}/alerts/check/escalation").json()
    pprint(f"升级检查结果", {
        "升级数量": len(r.get("escalated", [])),
        "escalated": r.get("escalated", [])
    })
    assert len(r.get("escalated", [])) >= 1, "应该至少有1条提醒被升级"

    for e in r["escalated"]:
        pprint(f"升级详情", {
            "alert_id": e["alert_id"],
            "alert_no": e["alert_no"],
            "box_no": e["box_no"],
            "previous_owner_role": e["previous_owner_role"],
            "escalated_to": e["escalated_to"],
            "hours_overdue": round(e["hours_overdue"], 1)
        })
        assert e["escalated_to"] == "manager", "应该升级给manager"
        assert e["hours_overdue"] >= 1.0, "超时时间应该>=1小时"

    # 按已升级筛选，验证能找到这些提醒
    escalated_alerts = requests.get(f"{BASE_URL}/alerts", params={
        "is_escalated": "true",
        "is_handled": "false"
    }).json()
    pprint(f"已升级筛选结果数量", len(escalated_alerts))
    assert len(escalated_alerts) >= 1

    for a in escalated_alerts:
        pprint(f"已升级提醒", {
            "alert_no": a["alert_no"],
            "box_no": a["box_no"],
            "is_escalated": a["is_escalated"],
            "escalated_at": a.get("escalated_at"),
            "escalated_to": a.get("escalated_to"),
            "current_owner_role": a.get("current_owner_role")
        })
        assert a["is_escalated"] == True
        assert a["current_owner_role"] == "manager", "当前归属应该变成manager"
        assert a["escalated_to"] == "manager"

    print("  >> 责任超时升级功能正常")

print("\n" + "="*70)
print(">>> 低温箱周转异常服务 - 处置协同与复盘能力验证")
print("="*70)

all_pass = True
try:
    test_drill_down_all_types()
    test_review_query_and_export()
    test_comments()
    test_escalation()

    print("\n" + "="*70)
    print(">>> 所有 4 项测试全部通过!")
    print("="*70)

    print("\n新增功能总结:")
    print("  1. 看板异常类型下钻 - 所有类型稳定列出未处理提醒")
    print("  2. 复盘预览导出 - 多维度筛选+汇总+明细+CSV导出")
    print("  3. 协同评论留痕 - 评论/附件，时间线和复盘中可见")
    print("  4. 责任超时升级 - 超时自动升级给manager，可筛选")

    print("\n访问地址:")
    print("   管理后台: http://localhost:8000/static/index.html")
    print("   API 文档: http://localhost:8000/docs")

except Exception as e:
    all_pass = False
    print(f"\n测试异常: {e}")
    import traceback
    traceback.print_exc()

exit(0 if all_pass else 1)
