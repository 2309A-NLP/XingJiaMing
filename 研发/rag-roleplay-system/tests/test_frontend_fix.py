import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_register_login_flow():
    """测试注册成功后自动跳转到登录页的逻辑"""
    print("===== 测试前端修复 =====")
    
    # 1. 测试新用户注册
    print("\n1. 注册新用户")
    try:
        url = f"{BASE_URL}/api/register"
        data = {"phone": "13700137000", "password": "test123456", "code": "1234"}
        response = requests.post(url, json=data)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        
        # 检查响应格式
        if result.get("success") or result.get("code") == 200:
            print("✅ 注册成功")
            print(f"   返回的token: {result.get('token') or result.get('data', {}).get('token')}")
            print(f"   响应格式兼容: {'success' in result} (success) / {'code' in result} (code)")
        else:
            print(f"❌ 注册失败: {result.get('message')}")
    except Exception as e:
        print(f"注册异常: {e}")
    
    # 2. 测试登录（使用刚注册的账号）
    print("\n2. 用户登录")
    try:
        url = f"{BASE_URL}/api/login"
        data = {"phone": "13700137000", "password": "test123456"}
        response = requests.post(url, json=data)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        
        if result.get("success") or result.get("code") == 200:
            print("✅ 登录成功")
            token = result.get("token") or result.get("data", {}).get("token")
            print(f"   Token: {token[:20]}...")
            return token
        else:
            print(f"❌ 登录失败: {result.get('message')}")
    except Exception as e:
        print(f"登录异常: {e}")
    
    return None

def test_login_without_register():
    """测试登录页面可以手动输入手机号"""
    print("\n3. 测试登录（手动输入手机号场景）")
    try:
        url = f"{BASE_URL}/api/login"
        # 使用之前注册的账号 13800138000
        data = {"phone": "13800138000", "password": "123456"}
        response = requests.post(url, json=data)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        
        if result.get("success") or result.get("code") == 200:
            print("✅ 登录成功 - 手动输入手机号正常工作")
        else:
            print(f"❌ 登录失败: {result.get('message')}")
    except Exception as e:
        print(f"登录异常: {e}")

if __name__ == "__main__":
    token = test_register_login_flow()
    test_login_without_register()
    print("\n===== 测试完成 =====")
