import os
import requests
import base64
from PIL import Image
import io

api_key = os.getenv("VISION_API_KEY", "")
base_url = os.getenv("VISION_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
model = os.getenv("VISION_MODEL", "mimo-v2.5")

if not api_key:
    print("错误: 请设置 VISION_API_KEY 环境变量")
    exit(1)

# 创建一个测试图片
img = Image.new('RGB', (100, 100), color='red')
buffer = io.BytesIO()
img.save(buffer, format='JPEG')
img_base64 = base64.b64encode(buffer.getvalue()).decode()

print("=== 测试多模态 API ===")
resp = requests.post(
    f"{base_url}/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片的内容"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
            ]
        }],
        "max_tokens": 200
    }
)

print(f"状态码: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"✓ 成功!")
    print(f"  回复: {data['choices'][0]['message']['content']}")
else:
    print(f"✗ 失败: {resp.text[:300]}")
