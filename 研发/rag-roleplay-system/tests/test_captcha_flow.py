import requests

BASE_URL = "http://127.0.0.1:8000"

def test_register_flow():
    """测试注册页面的人机验证流程"""
    print("=" * 60)
    print("测试注册页面 - 人机验证优化")
    print("=" * 60)

    # 1. 获取注册页面，检查人机验证是否默认隐藏
    print("\n[1] 检查注册页面结构")
    try:
        response = requests.get(f"{BASE_URL}/")
        html = response.text
        
        # 检查人机验证区域是否默认隐藏
        if 'id="captchaSection"' in html and 'style="display:none"' in html:
            print("    ✅ 人机验证区域默认隐藏")
        else:
            print("    ❌ 人机验证区域未隐藏")
        
        # 检查发送验证码按钮存在
        if 'onclick="sendSmsCode()"' in html:
            print("    ✅ 发送验证码按钮存在")
        else:
            print("    ❌ 发送验证码按钮不存在")
            
    except Exception as e:
        print(f"    ❌ 获取页面失败: {e}")

    # 2. 测试短信发送接口
    print("\n[2] 测试短信发送")
    try:
        response = requests.post(f"{BASE_URL}/api/sms/send",
                                json={"phone": "13900139001"})
        result = response.json()
        print(f"    状态码: {response.status_code}")
        print(f"    响应: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    ✅ 短信发送成功")
        else:
            print("    ❌ 短信发送失败")
    except Exception as e:
        print(f"    ❌ 短信发送异常: {e}")

    # 3. 测试用户注册
    print("\n[3] 测试用户注册")
    try:
        response = requests.post(f"{BASE_URL}/api/register",
                                json={"phone": "13900139001",
                                      "password": "test123456",
                                      "code": "1234",
                                      "name": "测试用户"})
        result = response.json()
        print(f"    状态码: {response.status_code}")
        print(f"    响应: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    ✅ 注册成功")
        else:
            print(f"    ❌ 注册失败: {result.get('message')}")
    except Exception as e:
        print(f"    ❌ 注册异常: {e}")

    # 4. 测试登录
    print("\n[4] 测试登录")
    try:
        response = requests.post(f"{BASE_URL}/api/login",
                                json={"phone": "13900139001",
                                      "password": "test123456"})
        result = response.json()
        print(f"    状态码: {response.status_code}")
        print(f"    响应: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    ✅ 登录成功")
        else:
            print(f"    ❌ 登录失败: {result.get('message')}")
    except Exception as e:
        print(f"    ❌ 登录异常: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_register_flow()
