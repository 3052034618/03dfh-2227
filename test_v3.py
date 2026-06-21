import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api"
future = (datetime.now() + timedelta(days=10)).isoformat()
past = (datetime.now() - timedelta(days=10)).isoformat()

def test(name):
    def deco(fn):
        def wrapper():
            print(f"\n{'='*70}")
            print(f"▶ 测试: {name}")
            print('='*70)
            try:
                fn()
                print(f"✅ [{name}] 测试通过")
            except AssertionError as e:
                print(f"❌ [{name}] 断言失败: {e}")
                raise
            except Exception as e:
                print(f"❌ [{name}] 异常: {e}")
                raise
        return wrapper
    return deco

def pprint(title, data=None, level=0):
    prefix = "  " * level
    print(f"{prefix}📌 {title}")
    if data is not None:
        try:
            text = json.dumps(data, indent=2, ensure_ascii=False)
            for line in text.split('\n'):
                print(f"{prefix}  {line}")
        except:
            print(f"{prefix}  {data}")

@test("1. 超期未回提醒推送记录 - 超期检查也能留下推送明细")
def test_overdue_push_records():
    # 创建一个超期任务（expected_return_date设为过去）
    box = "BOX-OVERDUE-001"
    r1 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "超期测试客户",
        "route": "线路A", "expected_return_date": past,
        "operator": "测试员"
    }).json()
    pprint("创建超期任务", {"task_no": r1["task_no"], "expected_return_date": past})

    # 手动触发超期检查
    check_r = requests.post(f"{BASE_URL}/alerts/check/overdue").json()
    pprint("超期检查结果", check_r)
    assert check_r["new_alerts"] >= 1, "应该至少产生1条超期提醒"

    # 查超期提醒
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=超期未回&is_handled=false").json()
    assert len(alerts) >= 1, "应该有超期未回提醒"
    alert_id = alerts[0]["id"]
    pprint(f"超期提醒 ID", alert_id)
    assert alerts[0]["last_pushed_at"] is not None, "超期提醒应该有最近推送时间"

    # 查详情，确认有推送记录
    detail = requests.get(f"{BASE_URL}/alerts/{alert_id}").json()
    push_records = detail.get("push_records", [])
    pprint(f"超期提醒的推送记录数量", len(push_records))
    assert len(push_records) >= 1, "超期提醒应该有推送记录"

    for rec in push_records:
        pprint(f"推送记录", {
            "接收人": rec["recipient_name"],
            "角色": rec["recipient_role"],
            "渠道": rec["push_channel"],
            "状态": rec["status"],
            "时间": rec["pushed_at"]
        }, level=1)
        assert rec["status"] == "success"

    print("  ✔ 超期未回提醒推送记录正确")

@test("2. 提醒处置台 - 处理+转派留下处置记录，并同步到时间线")
def test_alert_disposal():
    # 创建一个重复出库提醒
    box = "BOX-DISPOSAL-001"
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "客户A", "route": "线路1",
        "expected_return_date": future
    })
    requests.post(f"{BASE_URL}/turnover/outbound", json={  # 重复出库
        "box_no": box, "customer": "客户B", "route": "线路2",
        "expected_return_date": future
    })

    # 找提醒
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=同箱重复出库&is_handled=false").json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]
    pprint(f"找到提醒 ID: {alert_id}")

    # ====== 测试转派 ======
    assign_r = requests.post(f"{BASE_URL}/alerts/{alert_id}/assign", json={
        "operator_name": "张调度",
        "operator_role": "dispatch",
        "assigned_to_role": "warehouse",
        "assigned_to_name": "李仓管",
        "disposal_note": "请仓库核查箱体实际位置"
    }).json()
    pprint("转派结果", {
        "disposal_type": assign_r["disposal_type"],
        "assigned_to_name": assign_r["assigned_to_name"],
        "disposal_result": assign_r["disposal_result"]
    })
    assert assign_r["disposal_type"] == "assign"
    assert assign_r["assigned_to_name"] == "李仓管"

    # ====== 测试处理 ======
    handle_r = requests.post(f"{BASE_URL}/alerts/{alert_id}/handle", json={
        "handled_by": "李仓管",
        "handled_note": "已核查，确实是系统重复出库，已通知客户B",
        "disposal_result": "已联系客户"
    }).json()
    pprint("处理结果", {
        "disposal_type": handle_r["disposal_type"],
        "operator_name": handle_r["operator_name"],
        "disposal_result": handle_r["disposal_result"]
    })
    assert handle_r["disposal_type"] == "handle"
    assert handle_r["disposal_result"] == "已联系客户"

    # ====== 验证详情中包含处置记录 ======
    detail = requests.get(f"{BASE_URL}/alerts/{alert_id}").json()
    disposals = detail.get("disposals", [])
    pprint(f"处置记录数量", len(disposals))
    assert len(disposals) >= 2, "应该有2条处置记录（转派+处理）"

    types = [d["disposal_type"] for d in disposals]
    pprint(f"处置记录类型", types)
    assert "assign" in types and "handle" in types, "应该包含转派和处理两种类型"

    # ====== 验证时间线中包含处置记录 ======
    tl = requests.get(f"{BASE_URL}/turnover/timeline/{box}").json()
    event_types = [e["event_type"] for e in tl["events"]]
    pprint(f"时间线事件类型", event_types)
    assert any("提醒转派" in t for t in event_types), "时间线应该包含提醒转派事件"
    assert any("提醒处置" in t for t in event_types), "时间线应该包含提醒处置事件"

    # 检查处理时间和处理人出现在提醒事件中
    alert_events = [e for e in tl["events"] if "提醒-" in e["event_type"]]
    assert alert_events, "时间线应该有提醒事件"
    for ae in alert_events:
        if ae["data"].get("is_handled"):
            pprint("已处理提醒的处理人/时间", {
                "handled_by": ae["data"].get("handled_by"),
                "handled_at": ae["data"].get("handled_at")
            }, level=1)
            assert ae["data"].get("handled_by") == "李仓管"
            assert "已处理" in ae["title"]

    print("  ✔ 提醒处置台功能正确，处置记录已同步到时间线")

@test("3. 批量处理 - 超期和温控异常提醒批量标记已跟进")
def test_batch_handle():
    # 创建3个超期任务
    boxes = []
    for i in range(3):
        box = f"BOX-BATCH-{i:03d}"
        boxes.append(box)
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "批量处理客户",
            "route": f"线路{i}", "expected_return_date": past
        })

    # 触发超期检查
    requests.post(f"{BASE_URL}/alerts/check/overdue")

    # 找超期未回提醒
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=超期未回&is_handled=false").json()
    batch_alerts = [a for a in alerts if a["box_no"] and a["box_no"].startswith("BOX-BATCH-")]
    alert_ids = [a["id"] for a in batch_alerts]
    pprint(f"找到批量超期提醒数量", len(alert_ids))
    pprint(f"提醒ID列表", alert_ids)
    assert len(alert_ids) >= 3

    # 先回仓第一个箱体（模拟已回仓，批量处理时应跳过）
    requests.post(f"{BASE_URL}/turnover/return", json={
        "box_no": boxes[0], "location": "总仓", "operator": "仓管"
    })
    pprint(f"已回仓箱体: {boxes[0]}，批量处理时应该跳过它")

    # 批量处理
    batch_r = requests.post(f"{BASE_URL}/alerts/batch-handle", json={
        "alert_ids": alert_ids,
        "handled_by": "王调度",
        "handled_note": "已统一联系客户催还",
        "disposal_result": "已跟进催还"
    }).json()
    pprint("批量处理结果", batch_r)
    assert batch_r["processed"] == 2, "应该处理2条（跳过1条已回仓的）"
    assert batch_r["skipped"] == 1, "应该跳过1条已回仓的"
    assert len(batch_r["skipped_ids"]) == 1

    # 验证已处理的提醒状态（排除最后一个ID，因为最早创建的提醒对应最早创建的box）
    processed_ids = [aid for aid in alert_ids if aid not in batch_r["skipped_ids"]]
    pprint(f"实际处理的提醒ID", processed_ids)
    for aid in processed_ids:
        detail = requests.get(f"{BASE_URL}/alerts/{aid}").json()
        pprint(f"  验证提醒 {aid}", {
            "is_handled": detail["alert"]["is_handled"],
            "handled_by": detail["alert"]["handled_by"],
            "handled_note": detail["alert"]["handled_note"]
        }, level=1)
        assert detail["alert"]["is_handled"] == True
        assert detail["alert"]["handled_by"] == "王调度"
        assert detail["alert"]["handled_note"] == "已统一联系客户催还"

    # 验证跳过的提醒仍然未处理
    skipped_id = batch_r["skipped_ids"][0]
    detail2 = requests.get(f"{BASE_URL}/alerts/{skipped_id}").json()
    assert detail2["alert"]["is_handled"] == False, "已回仓箱体的提醒应该未被处理"

    print("  ✔ 批量处理功能正确，已回仓箱体的提醒被正确跳过")

@test("4. 责任节点看板 - 按客户/线路/箱号/异常类型汇总")
def test_dashboard():
    # 再触发一些数据
    for i in range(2):
        box = f"BOX-DASH-{i:03d}"
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "看板客户A",
            "route": "北京-上海", "expected_return_date": past
        })
    requests.post(f"{BASE_URL}/alerts/check/overdue")

    # 触发一些温控异常
    for i in range(2):
        box = f"BOX-TEMP-{i:03d}"
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "看板客户B",
            "route": "北京-广州", "expected_return_date": future
        })
        requests.post(f"{BASE_URL}/turnover/temperature", json={
            "box_no": box, "temperature": 15.0
        })

    # 触发一些重复出库
    box = "BOX-DUP-001"
    for i in range(2):
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": f"客户{i+1}",
            "route": "线路X", "expected_return_date": future
        })

    # ====== 看板总览 ======
    summary = requests.get(f"{BASE_URL}/alerts/dashboard/summary").json()
    pprint("看板总览", {
        "待处理总数": summary["total_pending"],
        "已处理总数": summary["total_handled"],
        "平均处理时长(分钟)": round(summary["avg_processing_minutes"], 1),
        "温控异常": summary["total_temp_abnormal"],
        "超期未回": summary["total_overdue"],
        "客户投诉": summary["total_complaint"],
        "重复出库": summary["total_duplicate"]
    })
    assert summary["total_pending"] > 0
    assert summary["total_overdue"] >= 5  # 超期测试3 + 看板2
    assert summary["total_temp_abnormal"] >= 2
    assert summary["total_duplicate"] >= 2  # 处置测试1 + 批量3 + 看板1

    # ====== 按客户汇总 ======
    by_customer = requests.get(f"{BASE_URL}/alerts/dashboard/by-customer").json()
    pprint("按客户汇总数量", len(by_customer))
    for item in by_customer[:3]:
        pprint(f"  {item['dimension_value']}", {
            "待处理": item["pending_count"],
            "平均时长(分钟)": round(item["avg_processing_minutes"], 1),
            "最近箱号": item["latest_box_no"]
        }, level=1)
    assert len(by_customer) >= 3

    # ====== 按线路汇总 ======
    by_route = requests.get(f"{BASE_URL}/alerts/dashboard/by-route").json()
    pprint("按线路汇总数量", len(by_route))
    for item in by_route[:3]:
        pprint(f"  {item['dimension_value']}", {
            "待处理": item["pending_count"],
            "平均时长(分钟)": round(item["avg_processing_minutes"], 1),
            "最近箱号": item["latest_box_no"]
        }, level=1)
    assert len(by_route) >= 3

    # ====== 按箱号汇总 ======
    by_box = requests.get(f"{BASE_URL}/alerts/dashboard/by-box").json()
    pprint("按箱号汇总数量", len(by_box))
    for item in by_box[:3]:
        pprint(f"  {item['dimension_value']}", {
            "待处理": item["pending_count"],
            "最近箱号": item["latest_box_no"]
        }, level=1)
    assert len(by_box) >= 5

    # ====== 按异常类型汇总 ======
    by_type = requests.get(f"{BASE_URL}/alerts/dashboard/by-type").json()
    pprint("按异常类型汇总数量", len(by_type))
    for item in by_type:
        pprint(f"  {item['dimension_value']}", {
            "待处理": item["pending_count"],
            "平均时长(分钟)": round(item["avg_processing_minutes"], 1)
        }, level=1)
    types = [i["dimension_value"] for i in by_type]
    assert "超期未回" in types
    assert "温控异常" in types
    assert "同箱重复出库" in types

    print("  ✔ 责任节点看板功能正确，所有维度汇总正常")

print("\n" + "="*70)
print("🚀 低温箱周转异常服务 - 处置闭环与看板功能验证")
print("="*70)

all_pass = True
try:
    test_overdue_push_records()
    test_alert_disposal()
    test_batch_handle()
    test_dashboard()

    print("\n" + "="*70)
    print("🎉 所有 4 项测试全部通过！")
    print("="*70)

    print("\n📊 新增功能总结:")
    print("  1️⃣  ✅ 超期未回提醒推送记录 - 超期检查也有推送明细")
    print("  2️⃣  ✅ 提醒处置台 - 支持处理/转派，记录同步到时间线")
    print("  3️⃣  ✅ 批量处理 - 批量标记跟进，自动跳过已回仓箱体")
    print("  4️⃣  ✅ 责任节点看板 - 按客户/线路/箱号/异常类型汇总")

    print("\n🌐 访问地址:")
    print("   管理后台: http://localhost:8000/static/index.html")
    print("   API 文档: http://localhost:8000/docs")

    print("\n📝 主要新增API:")
    print("   POST /api/alerts/{id}/handle - 处理提醒")
    print("   POST /api/alerts/{id}/assign - 转派提醒")
    print("   POST /api/alerts/batch-handle - 批量处理")
    print("   GET  /api/alerts/dashboard/summary - 看板总览")
    print("   GET  /api/alerts/dashboard/by-customer - 按客户汇总")
    print("   GET  /api/alerts/dashboard/by-route - 按线路汇总")
    print("   GET  /api/alerts/dashboard/by-box - 按箱号汇总")
    print("   GET  /api/alerts/dashboard/by-type - 按类型汇总")

except Exception as e:
    all_pass = False
    print(f"\n❌ 测试过程中出现异常: {e}")
    import traceback
    traceback.print_exc()

exit(0 if all_pass else 1)
