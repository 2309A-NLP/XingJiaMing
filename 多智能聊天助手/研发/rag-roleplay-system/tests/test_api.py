import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def test_sms_send():
    """测试短信发送接口"""
    try:
        url = f"{BASE_URL}/api/sms/send"
        data = {"phone": "13800138000"}
        response = requests.post(url, json=data)
        print(f"短信接口: {response.status_code}")
        print(f"响应: {response.json()}")
        return True
    except Exception as e:
        print(f"短信接口测试失败: {e}")
        return False

def test_register():
    """测试注册接口"""
    try:
        url = f"{BASE_URL}/api/register"
        data = {"phone": "13800138000", "password": "123456", "code": "1234"}
        response = requests.post(url, json=data)
        print(f"注册接口: {response.status_code}")
        print(f"响应: {response.json()}")
        return True
    except Exception as e:
        print(f"注册接口测试失败: {e}")
        return False

def test_login():
    """测试登录接口"""
    try:
        url = f"{BASE_URL}/api/login"
        data = {"phone": "13800138000", "password": "123456"}
        response = requests.post(url, json=data)
        print(f"登录接口: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        return result.get("token")
    except Exception as e:
        print(f"登录接口测试失败: {e}")
        return None

def test_chat(token):
    """测试聊天接口"""
    try:
        url = f"{BASE_URL}/api/chat/send"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": "你好", "roleId": "lawyer"}
        response = requests.post(url, json=data, headers=headers)
        print(f"聊天接口: {response.status_code}")
        print(f"响应: {response.json()}")
        return True
    except Exception as e:
        print(f"聊天接口测试失败: {e}")
        return False

def test_homepage():
    """测试主页"""
    try:
        url = f"{BASE_URL}/"
        response = requests.get(url)
        print(f"主页: {response.status_code}")
        print(f"内容长度: {len(response.content)}")
        return True
    except Exception as e:
        print(f"主页测试失败: {e}")
        return False

if __name__ == "__main__":
    print("===== 开始测试API接口 =====")
    
    # 等待服务启动
    time.sleep(2)
    
    # 测试主页
    print("\n1. 测试主页")
    test_homepage()
    
    # 测试短信发送
    print("\n2. 测试短信发送")
    test_sms_send()
    
    # 测试注册
    print("\n3. 测试注册")
    test_register()
    
    # 测试登录
    print("\n4. 测试登录")
    token = test_login()
    
    # 测试聊天（如果登录成功）
    if token:
        print("\n5. 测试聊天")
        test_chat(token)
    
    print("\n===== 测试完成 =====")