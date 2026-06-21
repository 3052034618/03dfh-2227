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

@test("1. 转派归属 - 目标角色能看到分给自己的提醒，转派记录有从谁到谁")
def test_assign_ownership():
    box = "BOX-ASSIGN-001"
    # 创建重复出库提醒
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "客户A", "route": "线路1",
        "expected_return_date": future
    })
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "客户B", "route": "线路2",
        "expected_return_date": future
    })

    # 找提醒
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=同箱重复出库&is_handled=false").json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]
    pprint(f"提醒 ID: {alert_id}, 初始归属角色", alerts[0].get("current_owner_role"))

    # 初始归属应该是责任节点
    assert alerts[0]["current_owner_role"] is not None, "初始提醒应该有current_owner_role"

    # 转派
    assign_r = requests.post(f"{BASE_URL}/alerts/{alert_id}/assign", json={
        "operator_name": "张调度",
        "operator_role": "dispatch",
        "assigned_to_role": "warehouse",
        "assigned_to_name": "李仓管",
        "disposal_note": "请仓库核查"
    }).json()
    pprint("转派结果", {
        "disposal_result": assign_r["disposal_result"],
        "operator_from_name": assign_r.get("operator_from_name"),
        "operator_from_role": assign_r.get("operator_from_role"),
        "assigned_to_name": assign_r["assigned_to_name"],
        "assigned_to_role": assign_r["assigned_to_role"]
    })
    assert assign_r["assigned_to_name"] == "李仓管"
    assert assign_r["assigned_to_role"] == "warehouse"
    assert assign_r["operator_from_name"] is not None or assign_r["operator_from_role"] is not None

    # 按归属角色筛选 - warehouse角色应该能看到这条提醒
    warehouse_alerts = requests.get(f"{BASE_URL}/alerts?assigned_to=warehouse&is_handled=false").json()
    found = any(a["id"] == alert_id for a in warehouse_alerts)
    pprint(f"仓库角色筛选能找到该提醒", found)
    assert found, "仓库角色按assigned_to筛选应该能看到这条提醒"

    # 查提醒详情确认current_owner已更新
    detail = requests.get(f"{BASE_URL}/alerts/{alert_id}").json()
    pprint("转派后提醒归属", {
        "current_owner_role": detail["alert"]["current_owner_role"],
        "current_owner_name": detail["alert"]["current_owner_name"]
    })
    assert detail["alert"]["current_owner_role"] == "warehouse"
    assert detail["alert"]["current_owner_name"] == "李仓管"

    # 转派记录中能看到从谁转给谁
    assign_disposal = [d for d in detail["disposals"] if d["disposal_type"] == "assign"]
    assert len(assign_disposal) >= 1
    pprint("转派记录", {
        "从谁": f"{assign_disposal[0]['operator_from_name']}({assign_disposal[0]['operator_from_role']})",
        "到谁": f"{assign_disposal[0]['assigned_to_name']}({assign_disposal[0]['assigned_to_role']})",
        "结果": assign_disposal[0]["disposal_result"]
    })
    assert "转派给" in assign_disposal[0]["disposal_result"]

    print("  >> 转派归属功能正确")

@test("2. 批量处理限制 - 只有超期未回+温控异常能批量处理，其他类型被拒绝")
def test_batch_type_limit():
    # 创建超期任务（允许批量）
    for i in range(2):
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": f"BOX-BATCH2-{i:03d}", "customer": "批量客户",
            "route": "线路A", "expected_return_date": past
        })
    requests.post(f"{BASE_URL}/alerts/check/overdue")

    # 创建重复出库提醒（不允许批量）
    for i in range(2):
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": f"BOX-BATCHDUP-{i:03d}", "customer": "批量客户",
            "route": "线路B", "expected_return_date": future
        })
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": f"BOX-BATCHDUP-{i:03d}", "customer": "批量客户2",
            "route": "线路C", "expected_return_date": future
        })

    # 获取所有未处理提醒
    all_alerts = requests.get(f"{BASE_URL}/alerts?is_handled=false").json()
    overdue = [a for a in all_alerts if a["alert_type"] == "超期未回"]
    dup = [a for a in all_alerts if a["alert_type"] == "同箱重复出库"]

    pprint(f"超期提醒数量", len(overdue))
    pprint(f"重复出库提醒数量", len(dup))
    assert len(overdue) >= 2
    assert len(dup) >= 2

    # 混合批量处理（超期+重复出库）
    all_ids = [a["id"] for a in overdue] + [a["id"] for a in dup]
    batch_r = requests.post(f"{BASE_URL}/alerts/batch-handle", json={
        "alert_ids": all_ids,
        "handled_by": "王调度",
        "handled_note": "批量测试",
        "disposal_result": "已跟进催还"
    }).json()
    pprint("批量处理结果", {
        "处理成功": batch_r["processed"],
        "跳过": batch_r["skipped"],
        "不允许": batch_r["not_allowed"]
    })

    assert batch_r["processed"] >= 2, "超期未回应该被成功处理"
    assert batch_r["not_allowed"] >= 2, "重复出库应该被标记为不允许"

    # 检查不允许的原因
    pprint("不允许明细", batch_r["not_allowed_ids"])
    for item in batch_r["not_allowed_ids"]:
        assert "不允许" in item["reason"], f"原因应包含'不允许': {item['reason']}"

    # 验证超期提醒已处理
    for a in overdue:
        detail = requests.get(f"{BASE_URL}/alerts/{a['id']}").json()
        assert detail["alert"]["is_handled"] == True, f"超期提醒{a['id']}应该已处理"

    # 验证重复出库提醒未处理
    for a in dup:
        detail = requests.get(f"{BASE_URL}/alerts/{a['id']}").json()
        assert detail["alert"]["is_handled"] == False, f"重复出库提醒{a['id']}不应被处理"

    print("  >> 批量处理类型限制正确")

@test("3. 看板下钻 - 点击维度值能看到未处理提醒明细")
def test_drill_down():
    # 创建一些数据
    for i in range(2):
        box = f"BOX-DRILL-{i:03d}"
        requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": box, "customer": "看板下钻客户",
            "route": "看板下钻线路", "expected_return_date": past
        })
    requests.post(f"{BASE_URL}/alerts/check/overdue")

    # 创建温控异常
    box = "BOX-DRILL-TEMP"
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "看板下钻客户",
        "route": "看板下钻线路", "expected_return_date": future
    })
    requests.post(f"{BASE_URL}/turnover/temperature", json={
        "box_no": box, "temperature": 15.0
    })

    # 按异常类型下钻 - 超期未回
    drill_r = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down?dimension=alert_type&dimension_value=超期未回").json()
    pprint(f"按异常类型下钻 '超期未回' 结果数量", drill_r["total"])
    assert drill_r["total"] >= 2
    assert drill_r["dimension"] == "alert_type"
    assert drill_r["dimension_value"] == "超期未回"
    for a in drill_r["alerts"]:
        assert a["alert_type"] == "超期未回"
        assert a["is_handled"] == False
        assert a["current_owner_role"] is not None

    # 按异常类型下钻 - 温控异常
    drill_r2 = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down?dimension=alert_type&dimension_value=温控异常").json()
    pprint(f"按异常类型下钻 '温控异常' 结果数量", drill_r2["total"])
    assert drill_r2["total"] >= 1

    # 按箱号下钻
    drill_r3 = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down?dimension=box_no&dimension_value=BOX-DRILL-TEMP").json()
    pprint(f"按箱号下钻结果数量", drill_r3["total"])
    assert drill_r3["total"] >= 1
    assert all(a["box_no"] == "BOX-DRILL-TEMP" for a in drill_r3["alerts"])

    # 按客户下钻
    drill_r4 = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down?dimension=customer&dimension_value=看板下钻客户").json()
    pprint(f"按客户下钻 '看板下钻客户' 结果数量", drill_r4["total"])
    assert drill_r4["total"] >= 2

    # 按线路下钻
    drill_r5 = requests.get(f"{BASE_URL}/alerts/dashboard/drill-down?dimension=route&dimension_value=看板下钻线路").json()
    pprint(f"按线路下钻 '看板下钻线路' 结果数量", drill_r5["total"])
    assert drill_r5["total"] >= 2

    print("  >> 看板下钻功能正确")

@test("4. 复盘导出 - CSV导出包含所有字段")
def test_export():
    import csv as csv_mod
    r = requests.get(f"{BASE_URL}/alerts/export")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    reader = csv_mod.reader(r.text.strip().splitlines())
    rows = list(reader)
    pprint(f"CSV总行数", len(rows))
    assert len(rows) >= 2, "应该有标题行+数据行"

    header = rows[0]
    pprint(f"CSV标题字段数", len(header))
    header_text = ",".join(header)
    assert "提醒编号" in header_text
    assert "当前归属角色" in header_text
    assert "当前归属人" in header_text
    assert "处理时长" in header_text
    assert "推送记录" in header_text
    assert "转派记录" in header_text

    today = datetime.now().strftime("%Y-%m-%d")
    r2 = requests.get(f"{BASE_URL}/alerts/export?start_date=2020-01-01&end_date={today}")
    assert r2.status_code == 200
    rows2 = list(csv_mod.reader(r2.text.strip().splitlines()))
    pprint(f"按日期导出行数", len(rows2))

    r3 = requests.get(f"{BASE_URL}/alerts/export?alert_type=超期未回")
    assert r3.status_code == 200
    rows3 = list(csv_mod.reader(r3.text.strip().splitlines()))
    pprint(f"按超期未回导出行数", len(rows3))
    for row in rows3[1:]:
        if row:
            assert "超期未回" in row

    print("  >> 复盘导出功能正确")

print("\n" + "="*70)
print(">>> 低温箱周转异常服务 - 处置协同与复盘能力验证")
print("="*70)

all_pass = True
try:
    test_assign_ownership()
    test_batch_type_limit()
    test_drill_down()
    test_export()

    print("\n" + "="*70)
    print(">>> 所有 4 项测试全部通过!")
    print("="*70)

    print("\n新增功能总结:")
    print("  1. 转派归属 - 目标角色能看到分给自己的提醒，转派记录有从谁到谁")
    print("  2. 批量处理限制 - 只允许超期未回+温控异常，其他类型被拒绝")
    print("  3. 看板下钻 - 按维度值查看未处理提醒明细")
    print("  4. 复盘导出 - CSV导出含异常/推送/转派/处理结果/处理时长")

    print("\n访问地址:")
    print("   管理后台: http://localhost:8000/static/index.html")
    print("   API 文档: http://localhost:8000/docs")

except Exception as e:
    all_pass = False
    print(f"\n测试异常: {e}")
    import traceback
    traceback.print_exc()

exit(0 if all_pass else 1)
