import requests, json
BASE='http://localhost:8000/api'

print('=== Drill-down by type ===')
r = requests.get(BASE+'/alerts/dashboard/drill-down', params={'dimension':'alert_type','dimension_value':'温控异常'})
print('Status:', r.status_code)
if r.status_code == 200:
    d = r.json()
    print('Total:', d['total'])
    for a in d.get('alerts',[])[:2]:
        print('  ', a['alert_no'], a['box_no'], a['alert_type'], a.get('current_owner_role'))
else:
    print('Error:', r.text[:200])

print()
print('=== Drill-down by box_no ===')
r2 = requests.get(BASE+'/alerts/dashboard/drill-down', params={'dimension':'box_no','dimension_value':'BOX-DRILL-TEMP'})
print('Status:', r2.status_code)
if r2.status_code == 200:
    d2 = r2.json()
    print('Total:', d2['total'])

print()
print('=== CSV Export ===')
r3 = requests.get(BASE+'/alerts/export')
print('Status:', r3.status_code)
if r3.status_code == 200:
    lines = r3.text.strip().split('\n')
    print('CSV rows:', len(lines))
    print('Header:', lines[0][:100])
    if len(lines)>1:
        print('Data[1]:', lines[1][:100])
else:
    print('Error:', r3.text[:200])

print()
print('=== Drill-down by customer ===')
r4 = requests.get(BASE+'/alerts/dashboard/drill-down', params={'dimension':'customer','dimension_value':'看板下钻客户'})
print('Status:', r4.status_code)
if r4.status_code == 200:
    d4 = r4.json()
    print('Total:', d4['total'])
else:
    print('Error:', r4.text[:200])

print()
print('=== Drill-down by route ===')
r5 = requests.get(BASE+'/alerts/dashboard/drill-down', params={'dimension':'route','dimension_value':'看板下钻线路'})
print('Status:', r5.status_code)
if r5.status_code == 200:
    d5 = r5.json()
    print('Total:', d5['total'])
else:
    print('Error:', r5.text[:200])

print()
print('ALL API CHECKS DONE')
