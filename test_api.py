import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api"

def print_response(title, response):
    print(f"\n{'='*60}")
    print(f"【{title}】")
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except:
        print(f"响应: {response.text}")
    print(f"{'='*60}\n")

print("=" * 60)
print("低温箱周转异常监控服务 - API 测试")
print("=" * 60)

try:
    r = requests.get("http://localhost:8000/health")
    print_response("健康检查", r)

    r = requests.get(f"{BASE_URL}/admin/dashboard")
    print_response("仪表盘统计", r)

    future_date = (datetime.now() + timedelta(days=3)).isoformat()
    outbound_data = {
        "box_no": "BOX-TEST-001",
        "customer": "测试客户A",
        "route": "北京-上海",
        "expected_return_date": future_date,
        "operator": "张出库"
    }
    r = requests.post(f"{BASE_URL}/turnover/outbound", json=outbound_data)
    print_response("订单出库 - BOX-TEST-001", r)

    outbound_data2 = {
        "box_no": "BOX-TEST-002",
        "customer": "测试客户A",
        "route": "北京-广州",
        "expected_return_date": future_date,
        "operator": "张出库"
    }
    r = requests.post(f"{BASE_URL}/turnover/outbound", json=outbound_data2)
    print_response("订单出库 - BOX-TEST-002", r)

    outbound_data3 = {
        "box_no": "BOX-TEST-001",
        "customer": "测试客户B",
        "route": "北京-深圳",
        "expected_return_date": future_date,
        "operator": "李出库"
    }
    r = requests.post(f"{BASE_URL}/turnover/outbound", json=outbound_data3)
    print_response("同箱重复出库测试 - BOX-TEST-001", r)

    sign_data = {
        "box_no": "BOX-TEST-001",
        "location": "上海配送站",
        "operator": "王签收",
        "remark": "客户正常签收"
    }
    r = requests.post(f"{BASE_URL}/turnover/sign", json=sign_data)
    print_response("签收回传 - BOX-TEST-001", r)

    temp_data_normal = {
        "box_no": "BOX-TEST-001",
        "temperature": 5.0
    }
    r = requests.post(f"{BASE_URL}/turnover/temperature", json=temp_data_normal)
    print_response("温度回传（正常）- 5.0°C", r)

    temp_data_abnormal = {
        "box_no": "BOX-TEST-001",
        "temperature": 12.5
    }
    r = requests.post(f"{BASE_URL}/turnover/temperature", json=temp_data_abnormal)
    print_response("温度回传（异常）- 12.5°C", r)

    complaint_data = {
        "box_no": "BOX-TEST-001",
        "customer": "测试客户A",
        "complaint_type": "温度异常",
        "description": "客户反映到货时箱体温度偏高"
    }
    r = requests.post(f"{BASE_URL}/turnover/complaint", json=complaint_data)
    print_response("客服投诉回传", r)

    return_data = {
        "box_no": "BOX-TEST-002",
        "location": "总仓",
        "operator": "赵回仓",
        "remark": "箱体完好回仓"
    }
    r = requests.post(f"{BASE_URL}/turnover/return", json=return_data)
    print_response("回仓回传 - BOX-TEST-002", r)

    r = requests.get(f"{BASE_URL}/alerts?is_handled=false")
    print_response("查询待处理提醒", r)

    r = requests.get(f"{BASE_URL}/turnover/handover/BOX-TEST-001")
    print_response("查询交接记录 - BOX-TEST-001", r)

    r = requests.get(f"{BASE_URL}/admin/configs")
    print_response("系统配置列表", r)

    r = requests.get(f"{BASE_URL}/admin/customer-configs")
    print_response("客户周转配置", r)

    r = requests.get(f"{BASE_URL}/admin/recipients")
    print_response("提醒接收人", r)

    r = requests.get(f"{BASE_URL}/admin/boxes")
    print_response("箱体列表", r)

    r = requests.get(f"{BASE_URL}/admin/tasks")
    print_response("周转任务列表", r)

    r = requests.post(f"{BASE_URL}/alerts/check/run")
    print_response("执行规则检查", r)

    r = requests.get(f"{BASE_URL}/admin/dashboard")
    print_response("测试后仪表盘统计", r)

    print("\n✅ 所有测试完成！")
    print(f"管理后台: http://localhost:8000/static/index.html")
    print(f"API 文档: http://localhost:8000/docs")

except Exception as e:
    print(f"\n❌ 测试出错: {e}")
    import traceback
    traceback.print_exc()
