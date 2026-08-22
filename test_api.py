import urllib.request, json, random
from datetime import datetime, timedelta

base = 'http://localhost:8000'

# 测试异常检测接口
sequence = [[random.uniform(0.5, 0.9), random.uniform(5, 40), random.uniform(0.01, 0.1),
             random.uniform(25, 130), random.uniform(0.1, 2.0), random.uniform(0.01, 0.5),
             random.uniform(-0.5, 0.5), random.uniform(100, 5000)] for _ in range(60)]

body = json.dumps({'equipment_id': 'I-9-01', 'sequence_data': sequence}).encode('utf-8')
req = urllib.request.Request(base + '/api/v1/anomaly/detect', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read().decode('utf-8'))
    print('✅ POST /api/v1/anomaly/detect')
    print(json.dumps(result, ensure_ascii=False, indent=2))

print()

# 测试热力图接口
end = datetime.now()
start = end - timedelta(hours=24)
url = base + '/api/v1/carbon/heatmap?start_time=' + start.isoformat() + '&end_time=' + end.isoformat()
req2 = urllib.request.Request(url)
with urllib.request.urlopen(req2, timeout=10) as resp2:
    result2 = json.loads(resp2.read().decode('utf-8'))
    print('✅ GET /api/v1/carbon/heatmap')
    data = result2.get('data', {})
    if isinstance(data, dict):
        records = data.get('records', [])
        print('  设备数:', len(records))
        if records:
            print('  第一条:', json.dumps(records[0], ensure_ascii=False))
    else:
        print(json.dumps(result2, ensure_ascii=False, indent=2)[:400])
