import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_full_frontend():
    """完整的前端测试"""
    print("=" * 60)
    print("前端完整测试")
    print("=" * 60)

    # 1. 测试主页加载
    print("\n[1] 测试主页加载")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"    状态码: {response.status_code}")
        if response.status_code == 200:
            print("    ✅ 主页加载成功")
            if "一问三不知" in response.text:
                print("    ✅ Logo已修改为一问三不知")
            else:
                print("    ❌ Logo未修改")
            if "page-login" in response.text:
                print("    ✅ 登录页存在")
            if "page-register" in response.text:
                print("    ✅ 注册页存在")
            if "page-roles" in response.text:
                print("    ✅ 角色选择页存在")
            if "page-chat" in response.text:
                print("    ✅ 聊天页存在")
        else:
            print("    ❌ 主页加载失败")
    except Exception as e:
        print(f"    ❌ 主页加载异常: {e}")

    # 2. 测试短信发送接口
    print("\n[2] 测试短信发送接口")
    try:
        response = requests.post(f"{BASE_URL}/api/sms/send",
                                json={"phone": "13600136000"})
        print(f"    状态码: {response.status_code}")
        result = response.json()
        print(f"    响应: {result}")
        if result.get("code") == 200:
            print("    ✅ 短信发送成功")
        else:
            print("    ❌ 短信发送失败")
    except Exception as e:
        print(f"    ❌ 短信发送异常: {e}")

    # 3. 测试用户注册
    print("\n[3] 测试用户注册")
    try:
        response = requests.post(f"{BASE_URL}/api/register",
                                json={"phone": "13600136000",
                                      "password": "test123",
                                      "code": "123456",
                                      "name": "测试用户"})
        print(f"    状态码: {response.status_code}")
        result = response.json()
        print(f"    响应: {result}")

        # 检查响应格式
        if result.get("success") == True or result.get("code") == 200:
            print("    ✅ 注册成功(兼容success/code格式)")
            token = result.get("token") or result.get("data", {}).get("token")
            if token:
                print(f"    ✅ Token已获取: {token[:30]}...")
            else:
                print("    ⚠️ Token为空")
        else:
            print(f"    ❌ 注册失败: {result.get('message')}")
    except Exception as e:
        print(f"    ❌ 注册异常: {e}")

    # 4. 测试用户登录
    print("\n[4] 测试用户登录")
    try:
        response = requests.post(f"{BASE_URL}/api/login",
                                json={"phone": "13600136000",
                                      "password": "test123"})
        print(f"    状态码: {response.status_code}")
        result = response.json()
        print(f"    响应: {result}")

        # 检查响应格式
        if result.get("success") == True or result.get("code") == 200:
            print("    ✅ 登录成功(兼容success/code格式)")
            token = result.get("token") or result.get("data", {}).get("token")
            if token:
                print(f"    ✅ Token已获取: {token[:30]}...")
                return token
        else:
            print(f"    ❌ 登录失败: {result.get('message')}")
    except Exception as e:
        print(f"    ❌ 登录异常: {e}")

    return None

def test_chat(token):
    """测试聊天功能"""
    print("\n[5] 测试聊天功能")

    # 测试律师聊天
    print("\n    [5.1] 测试律师聊天(lawyer)")
    try:
        response = requests.post(f"{BASE_URL}/api/chat/send",
                                json={"roleId": "lawyer", "message": "你好"},
                                headers={"Authorization": f"Bearer {token}"})
        print(f"        状态码: {response.status_code}")
        result = response.json()
        if result.get("code") == 200:
            reply = result.get("data", {}).get("reply", "")
            print(f"        回复: {reply[:80]}...")
            print("        ✅ 律师聊天成功")
        else:
            print(f"        ❌ 聊天失败: {result}")
    except Exception as e:
        print(f"        ❌ 聊天异常: {e}")

    # 测试医生聊天
    print("\n    [5.2] 测试医生聊天(doctor)")
    try:
        response = requests.post(f"{BASE_URL}/api/chat/send",
                                json={"roleId": "doctor", "message": "感冒了怎么办"},
                                headers={"Authorization": f"Bearer {token}"})
        print(f"        状态码: {response.status_code}")
        result = response.json()
        if result.get("code") == 200:
            reply = result.get("data", {}).get("reply", "")
            print(f"        回复: {reply[:80]}...")
            print("        ✅ 医生聊天成功")
        else:
            print(f"        ❌ 聊天失败: {result}")
    except Exception as e:
        print(f"        ❌ 聊天异常: {e}")

    # 测试心理咨询师聊天
    print("\n    [5.3] 测试心理咨询师聊天(psych)")
    try:
        response = requests.post(f"{BASE_URL}/api/chat/send",
                                json={"roleId": "psych", "message": "最近压力很大"},
                                headers={"Authorization": f"Bearer {token}"})
        print(f"        状态码: {response.status_code}")
        result = response.json()
        if result.get("code") == 200:
            reply = result.get("data", {}).get("reply", "")
            print(f"        回复: {reply[:80]}...")
            print("        ✅ 心理咨询师聊天成功")
        else:
            print(f"        ❌ 聊天失败: {result}")
    except Exception as e:
        print(f"        ❌ 聊天异常: {e}")

def test_navigation():
    """测试页面导航元素"""
    print("\n[6] 测试页面导航元素")
    try:
        response = requests.get(f"{BASE_URL}/")
        html = response.text

        # 检查登录页是否有返回键
        login_section = html[html.find('id="page-login"'):html.find('id="page-register"')]
        if 'back-btn' in login_section and 'goBack' in login_section:
            print("    ⚠️ 登录页仍有返回键")
        else:
            print("    ✅ 登录页已移除返回键")

        # 检查注册页是否有返回键
        register_section = html[html.find('id="page-register"'):html.find('id="page-roles"')]
        if 'back-btn' in register_section:
            print("    ✅ 注册页保留返回键")
        else:
            print("    ❌ 注册页返回键丢失")

        # 检查Logo
        if "一问三不知" in html:
            print("    ✅ Logo已改为'一问三不知'")
        else:
            print("    ❌ Logo未修改")

    except Exception as e:
        print(f"    ❌ 导航检查异常: {e}")

if __name__ == "__main__":
    token = test_full_frontend()
    test_navigation()
    if token:
        test_chat(token)
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
