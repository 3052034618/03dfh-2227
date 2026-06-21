import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api"

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

future = (datetime.now() + timedelta(days=3)).isoformat()
past = (datetime.now() - timedelta(days=1)).isoformat()

@test("1. 推送记录追踪 - 验证提醒能查到推送给哪些角色")
def test_push_records():
    # 先出库触发重复出库提醒
    r1 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": "BOX-PUSH-001", "customer": "推送测试客户",
        "route": "A-B", "expected_return_date": future, "operator": "测试员"
    }).json()
    pprint("第一次出库任务号", r1["task_no"])

    # 同箱重复出库，触发提醒
    r2 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": "BOX-PUSH-001", "customer": "推送测试客户2",
        "route": "C-D", "expected_return_date": future, "operator": "测试员2"
    }).json()
    pprint("第二次（重复）出库任务号", r2["task_no"])

    # 查提醒列表
    alerts = requests.get(f"{BASE_URL}/alerts?alert_type=同箱重复出库").json()
    assert len(alerts) >= 1, "应该至少有1条重复出库提醒"
    alert_id = alerts[0]["id"]
    pprint(f"找到提醒 ID: {alert_id}, 最近推送时间", alerts[0].get("last_pushed_at"))
    assert alerts[0].get("last_pushed_at") is not None, "提醒应该有最近推送时间"

    # 查推送记录
    detail = requests.get(f"{BASE_URL}/alerts/{alert_id}").json()
    pprint("提醒详情结构", list(detail.keys()))
    push_records = detail.get("push_records", [])
    pprint(f"推送记录数量", len(push_records))
    assert len(push_records) >= 1, "应该至少有1条推送记录"

    # 检查每条推送记录的内容
    for rec in push_records:
        pprint(f"推送记录", {
            "接收人": rec["recipient_name"],
            "角色": rec["recipient_role"],
            "渠道": rec["push_channel"],
            "目标": rec["push_target"],
            "状态": rec["status"],
            "时间": rec["pushed_at"]
        }, level=1)
        assert rec["recipient_name"], "接收人姓名不能为空"
        assert rec["recipient_role"], "接收人角色不能为空"
        assert rec["status"] == "success", "推送状态应该是成功"

    print("  ✔ 推送记录追踪功能正确")

@test("2. 客户高占用去重 - 同箱重复出库不应虚增占用数")
def test_high_occupation_dedup():
    customer = "占用测试客户_X"
    # 先把阈值调低到2，方便测试
    requests.post(f"{BASE_URL}/admin/configs", json={
        "config_key": "customer_high_occupation_threshold",
        "config_value": "2"
    })

    # 用不同箱号出库2次（达到阈值）
    for i in range(2):
        r = requests.post(f"{BASE_URL}/turnover/outbound", json={
            "box_no": f"BOX-OCC-{i:03d}", "customer": customer,
            "route": f"Route-{i}", "expected_return_date": future
        })
        assert r.status_code == 200

    # 第3次用不同箱号，应该触发高占用
    r3 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": "BOX-OCC-999", "customer": customer,
        "route": "Route-999", "expected_return_date": future
    }).json()
    pprint("第3个不同箱号出库", r3)

    # 找客户高占用提醒
    alerts = requests.get(f"{BASE_URL}/alerts?is_handled=false").json()
    occ_alerts = [a for a in alerts if a["alert_type"] == "客户高占用" and customer in a["content"]]
    pprint(f"客户高占用提醒数量", len(occ_alerts))
    # 应该有高占用提醒
    assert len(occ_alerts) >= 1, f"客户占用了3个不同箱号，应该触发高占用提醒"
    initial_occ_alert_ids = {a["id"] for a in occ_alerts}

    # 现在做同箱重复出库，不应该再新增高占用提醒（因为箱号没增加）
    r4 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": "BOX-OCC-000",  # 重复的箱号
        "customer": customer,
        "route": "Route-DUP", "expected_return_date": future
    }).json()
    pprint("重复出库 BOX-OCC-000", r4)

    # 再次检查高占用提醒数量
    alerts2 = requests.get(f"{BASE_URL}/alerts?is_handled=false").json()
    occ_alerts2 = [a for a in alerts2 if a["alert_type"] == "客户高占用" and customer in a["content"] and a["id"] not in initial_occ_alert_ids]
    pprint(f"重复出库后新增的客户高占用提醒数量", len(occ_alerts2))
    # 重复出库不应该增加新的高占用提醒（去重逻辑生效）
    assert len(occ_alerts2) == 0, "同箱重复出库不应新增客户高占用提醒（应该按箱号去重）"

    # 但重复出库提醒应该有
    dup_alerts = [a for a in alerts2 if a["alert_type"] == "同箱重复出库" and "BOX-OCC-000" in (a["box_no"] or "")]
    pprint(f"同箱重复出库提醒数量", len(dup_alerts))
    assert len(dup_alerts) >= 1, "应该有重复出库提醒"

    print("  ✔ 客户高占用按箱号去重逻辑正确")

@test("3. 同箱重复出库任务标记 - 任务应该有重复标记")
def test_duplicate_task_flag():
    box = "BOX-DUPFLAG-001"
    r1 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "客户A", "route": "线路1",
        "expected_return_date": future
    }).json()
    task1_no = r1["task_no"]

    # 重复出库
    r2 = requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "客户B", "route": "线路2",
        "expected_return_date": future
    }).json()
    task2_no = r2["task_no"]

    # 查询这两个任务
    tasks = requests.get(f"{BASE_URL}/admin/tasks").json()
    task1 = next(t for t in tasks if t["task_no"] == task1_no)
    task2 = next(t for t in tasks if t["task_no"] == task2_no)

    pprint("任务1（原始）", {"is_duplicate": task1.get("is_duplicate"), "duplicate_of_task_id": task1.get("duplicate_of_task_id")})
    pprint("任务2（重复）", {"is_duplicate": task2.get("is_duplicate"), "duplicate_of_task_id": task2.get("duplicate_of_task_id")})

    assert task1.get("is_duplicate") == False, "任务1应该不是重复任务"
    assert task1.get("duplicate_of_task_id") is None, "任务1 duplicate_of_task_id 应为空"
    assert task2.get("is_duplicate") == True, "任务2应该标记为重复任务"
    assert task2.get("duplicate_of_task_id") == task1["id"], "任务2应该关联到任务1"

    # 周转任务列表按重复筛选能查到
    dup_filtered = [t for t in tasks if t.get("is_duplicate")]
    pprint("筛选到的重复任务数", len(dup_filtered))
    assert len(dup_filtered) >= 1, "应该能筛选出重复任务"

    print("  ✔ 同箱重复出库任务标记正确")

@test("4. 温度越界状态稳定转换 - 任何状态都转温控异常，回仓后恢复空闲")
def test_temp_abnormal_state():
    box = "BOX-TEMP-001"

    # ====== 测试1：出库状态下温度越界 ======
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "温控客户", "route": "线路A",
        "expected_return_date": future
    })
    box_info = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()
    pprint("初始（出库后）状态", box_info["status"])
    assert box_info["status"] == "outbound", "初始应该是出库状态"

    # 温度越界
    requests.post(f"{BASE_URL}/turnover/temperature", json={
        "box_no": box, "temperature": 15.0  # 超过8度
    })
    box_info = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()
    pprint("温度越界后的状态", box_info["status"])
    assert box_info["status"] == "temp_abnormal", "出库状态下温度越界应该转温控异常"

    # ====== 测试2：签收不能覆盖温控异常 ======
    sign_r = requests.post(f"{BASE_URL}/turnover/sign", json={
        "box_no": box, "location": "某地", "operator": "某人"
    }).json()
    pprint("签收结果", {"success": sign_r.get("success")})
    box_info = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()
    pprint("签收后的状态（仍应保持温控异常）", box_info["status"])
    assert box_info["status"] == "temp_abnormal", "签收不能覆盖温控异常状态"

    # 管理页按温控异常筛选能查到
    all_boxes = requests.get(f"{BASE_URL}/admin/boxes?status=temp_abnormal").json()
    found = any(b["box_no"] == box for b in all_boxes)
    pprint("按温控异常筛选能找到箱体", found)
    assert found, "管理页按温控异常筛选应该能查到该箱体"

    # ====== 测试3：回仓后恢复空闲 ======
    ret_r = requests.post(f"{BASE_URL}/turnover/return", json={
        "box_no": box, "location": "总仓", "operator": "仓管"
    }).json()
    pprint("回仓结果", {"success": ret_r.get("success"), "关闭任务数": ret_r.get("closed_tasks")})
    box_info = requests.get(f"{BASE_URL}/admin/boxes/{box}").json()
    pprint("回仓后的状态", box_info["status"])
    assert box_info["status"] == "idle", "回仓后状态应该恢复为空闲"
    assert box_info["current_customer"] is None, "回仓后当前客户应为空"
    assert box_info["current_route"] is None, "回仓后当前线路应为空"

    # 空闲箱体检索不到温控异常
    all_boxes2 = requests.get(f"{BASE_URL}/admin/boxes?status=temp_abnormal").json()
    still_found = any(b["box_no"] == box for b in all_boxes2)
    pprint("回仓后还在温控异常列表里吗", still_found)
    assert not still_found, "回仓后不应该在温控异常列表里"

    print("  ✔ 温度越界状态转换逻辑正确")

@test("5. 箱体全链路时间线 - 所有事件串联显示")
def test_box_timeline():
    box = "BOX-TIMELINE-001"

    # 1. 出库
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "时间线客户", "route": "北京-上海",
        "expected_return_date": future, "operator": "张出库"
    })

    # 2. 重复出库（触发系统标记）
    requests.post(f"{BASE_URL}/turnover/outbound", json={
        "box_no": box, "customer": "另一个客户", "route": "北京-广州",
        "expected_return_date": future
    })

    # 3. 签收
    requests.post(f"{BASE_URL}/turnover/sign", json={
        "box_no": box, "location": "上海配送站", "operator": "李签收",
        "remark": "货物完好"
    })

    # 4. 正常温度
    requests.post(f"{BASE_URL}/turnover/temperature", json={
        "box_no": box, "temperature": 5.0
    })

    # 5. 温度越界
    requests.post(f"{BASE_URL}/turnover/temperature", json={
        "box_no": box, "temperature": 12.5
    })

    # 6. 客服投诉
    requests.post(f"{BASE_URL}/turnover/complaint", json={
        "box_no": box, "customer": "时间线客户",
        "complaint_type": "温度异常",
        "description": "客户反映货物温度偏高"
    })

    # 7. 回仓
    requests.post(f"{BASE_URL}/turnover/return", json={
        "box_no": box, "location": "总仓", "operator": "王回仓"
    })

    # 查时间线
    tl = requests.get(f"{BASE_URL}/turnover/timeline/{box}").json()
    pprint("时间线结构", list(tl.keys()))
    pprint("箱体信息", tl["box"])
    pprint("事件总数", tl["total_events"])
    pprint("建议下一步动作", tl.get("next_suggested_action"))

    events = tl["events"]
    pprint("事件列表", [e["event_type"] for e in events])

    # 验证时间线包含所有类型的事件
    event_types = [e["event_type"] for e in events]
    assert any("出库" in t for t in event_types), "应有出库事件"
    assert any("签收" in t for t in event_types), "应有签收事件"
    assert any("温度异常" in t for t in event_types), "应有温度异常事件"
    assert any("客户投诉" in t for t in event_types), "应有客户投诉事件"
    assert any("回仓" in t for t in event_types), "应有回仓事件"
    assert any("同箱重复出库" in t for t in event_types), "应有同箱重复出库提醒"
    assert any("温控异常" in t for t in event_types), "应有温控异常提醒"
    assert any("系统标记" in t for t in event_types), "应有重复任务系统标记"

    # 验证时间线是按时间排序的
    times = [datetime.fromisoformat(e["event_time"].replace("Z", "")) for e in events]
    for i in range(1, len(times)):
        assert times[i] >= times[i-1], f"事件应按时间升序排列: 事件{i}({times[i]}) < 事件{i-1}({times[i-1]})"

    # 每个事件都有必要字段
    for e in events:
        assert "event_type" in e
        assert "event_time" in e
        assert "title" in e
        assert "description" in e
        assert "icon" in e

    pprint("✅ 时间线验证通过，所有事件类型齐全，排序正确")

print("\n" + "="*70)
print("🚀 低温箱周转异常服务 - 规则闭环与逻辑修复验证")
print("="*70)

all_pass = True
try:
    test_push_records()
    test_high_occupation_dedup()
    test_duplicate_task_flag()
    test_temp_abnormal_state()
    test_box_timeline()

    print("\n" + "="*70)
    print("🎉 所有 5 项测试全部通过！")
    print("="*70)

    print("\n📊 功能修复总结:")
    print("  1️⃣  ✅ 提醒推送记录可追踪 - 能查看角色、渠道、状态、推送时间")
    print("  2️⃣  ✅ 客户高占用去重 - 同箱重复出库不增加占用数")
    print("  3️⃣  ✅ 同箱重复出库任务标记 - 后台清楚标记且可筛选")
    print("  4️⃣  ✅ 温控异常状态稳定 - 签收不覆盖，回仓才恢复空闲")
    print("  5️⃣  ✅ 箱体全链路时间线 - 所有事件串联显示，含责任节点判断")

    print("\n🌐 访问地址:")
    print("   管理后台: http://localhost:8000/static/index.html")
    print("   API 文档: http://localhost:8000/docs")

except Exception as e:
    all_pass = False
    print(f"\n❌ 测试过程中出现异常: {e}")
    import traceback
    traceback.print_exc()

exit(0 if all_pass else 1)
