import requests

# 创建不使用代理的会话
session = requests.Session()
session.trust_env = False

print("=" * 60)
print("Full Function Test")
print("=" * 60)

# 1. 测试登录
print("\n1. Test Login")
print("-" * 40)
login_data = {
    "phone": "15215878596",
    "password": "123456"
}
try:
    response = session.post("http://localhost:8000/api/login", json=login_data)
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    if result.get("success") or result.get("code") == 200:
        token = result.get("token") or result.get("data", {}).get("token", "")
        print("SUCCESS: Login successful")
    else:
        print("FAILED: Login failed")
except Exception as e:
    print(f"ERROR: Login exception: {e}")

# 2. 测试心理医生角色
print("\n2. Test Psychology Role")
print("-" * 40)
try:
    response = session.post(
        "http://localhost:8000/api/chat/send",
        json={"roleId": "psych", "message": "你好"},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    if result.get("code") == 200 and result.get("data", {}).get("reply"):
        print(f"SUCCESS: Psychology reply: {result['data']['reply'][:50]}...")
    else:
        print("FAILED: Psychology reply failed")
except Exception as e:
    print(f"ERROR: Psychology test exception: {e}")

# 3. 测试医疗门诊角色
print("\n3. Test Doctor Role")
print("-" * 40)
try:
    response = session.post(
        "http://localhost:8000/api/chat/send",
        json={"roleId": "doctor", "message": "我有点发烧怎么办"},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    if result.get("code") == 200 and result.get("data", {}).get("reply"):
        print(f"SUCCESS: Doctor reply: {result['data']['reply'][:50]}...")
    else:
        print("FAILED: Doctor reply failed")
except Exception as e:
    print(f"ERROR: Doctor test exception: {e}")

# 4. 测试刑事律师角色
print("\n4. Test Lawyer Role")
print("-" * 40)
try:
    response = session.post(
        "http://localhost:8000/api/chat/send",
        json={"roleId": "lawyer", "message": "我被人诈骗了怎么办"},
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(f"Response: {result}")
    if result.get("code") == 200 and result.get("data", {}).get("reply"):
        print(f"SUCCESS: Lawyer reply: {result['data']['reply'][:50]}...")
    else:
        print("FAILED: Lawyer reply failed")
except Exception as e:
    print(f"ERROR: Lawyer test exception: {e}")

print("\n" + "=" * 60)
print("Test Completed!")
print("=" * 60)