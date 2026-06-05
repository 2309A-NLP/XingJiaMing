import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_full_flow():
    """测试完整流程：注册 -> 登录 -> 聊天"""
    print("===== 测试完整RAG项目流程 =====")
    
    # 1. 测试注册新用户
    print("\n1. 注册新用户")
    try:
        url = f"{BASE_URL}/api/register"
        data = {"phone": "13900139000", "password": "test123456", "code": "1234"}
        response = requests.post(url, json=data)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        if result.get("success"):
            print("✅ 注册成功")
        else:
            print(f"❌ 注册失败: {result.get('message')}")
    except Exception as e:
        print(f"注册异常: {e}")
    
    # 2. 测试登录
    print("\n2. 用户登录")
    token = None
    try:
        url = f"{BASE_URL}/api/login"
        data = {"phone": "13900139000", "password": "test123456"}
        response = requests.post(url, json=data)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        token = result.get("token")
        if token:
            print("✅ 登录成功")
        else:
            print(f"❌ 登录失败: {result.get('message')}")
    except Exception as e:
        print(f"登录异常: {e}")
    
    # 3. 测试聊天（律师角色）
    if token:
        print("\n3. 测试聊天（律师角色）")
        try:
            url = f"{BASE_URL}/api/chat/send"
            headers = {"Authorization": f"Bearer {token}"}
            data = {"message": "你好", "roleId": "lawyer"}
            response = requests.post(url, json=data, headers=headers)
            print(f"状态码: {response.status_code}")
            # 使用response.text避免编码问题
            try:
                result = response.json()
                print(f"响应: {result}")
                if "data" in result and "reply" in result["data"]:
                    print(f"✅ 聊天成功，回复: {result['data']['reply']}")
            except json.JSONDecodeError:
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"聊天异常: {e}")
        
        # 4. 测试心理咨询师角色
        print("\n4. 测试聊天（心理咨询师角色）")
        try:
            url = f"{BASE_URL}/api/chat/send"
            headers = {"Authorization": f"Bearer {token}"}
            data = {"message": "最近压力很大", "roleId": "psych"}
            response = requests.post(url, json=data, headers=headers)
            print(f"状态码: {response.status_code}")
            try:
                result = response.json()
                print(f"响应: {result}")
                if "data" in result and "reply" in result["data"]:
                    print(f"✅ 聊天成功，回复: {result['data']['reply']}")
            except json.JSONDecodeError:
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"聊天异常: {e}")
        
        # 5. 测试医学专家角色
        print("\n5. 测试聊天（医学专家角色）")
        try:
            url = f"{BASE_URL}/api/chat/send"
            headers = {"Authorization": f"Bearer {token}"}
            data = {"message": "感冒了怎么办", "roleId": "doctor"}
            response = requests.post(url, json=data, headers=headers)
            print(f"状态码: {response.status_code}")
            try:
                result = response.json()
                print(f"响应: {result}")
                if "data" in result and "reply" in result["data"]:
                    print(f"✅ 聊天成功，回复: {result['data']['reply']}")
            except json.JSONDecodeError:
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"聊天异常: {e}")
    
    # 6. 测试获取角色列表
    print("\n6. 获取角色列表")
    try:
        url = f"{BASE_URL}/api/characters"
        response = requests.get(url)
        print(f"状态码: {response.status_code}")
        result = response.json()
        print(f"响应: {result}")
        if "characters" in result:
            print(f"✅ 获取角色列表成功，共{len(result['characters'])}个角色")
    except Exception as e:
        print(f"获取角色列表异常: {e}")
    
    print("\n===== 测试完成 =====")

if __name__ == "__main__":
    test_full_flow()
