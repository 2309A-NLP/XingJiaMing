import requests

BASE_URL = "http://127.0.0.1:8000"

def test_all_characters():
    """测试所有角色的对话功能"""
    print("=" * 60)
    print("Testing All Characters")
    print("=" * 60)

    # 登录
    print("\n[1] Login")
    login_data = {"phone": "13900139000", "password": "test123456"}
    response = requests.post(f"{BASE_URL}/api/login", json=login_data)
    result = response.json()
    print(f"    Status: {response.status_code}")
    if result.get("code") == 200 or result.get("success") == True:
        token = result.get("data", {}).get("token") or result.get("token")
        print(f"    Token: {token[:30]}...")
        headers = {"Authorization": f"Bearer {token}"}
    else:
        print(f"    Login failed: {result.get('message')}")
        return

    # 测试所有角色
    roles = [
        {"roleId": "lawyer", "name": "刑事律师", "question": "抢劫罪会怎么判？"},
        {"roleId": "doctor", "name": "医学专家", "question": "你好，我感冒了怎么办？"},
        {"roleId": "psych", "name": "心理咨询师", "question": "最近压力很大，怎么办？"}
    ]

    for role in roles:
        print(f"\n[{role['name']}]")
        print(f"    Question: {role['question']}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/chat/send",
                json={"roleId": role["roleId"], "message": role["question"]},
                headers=headers
            )
            result = response.json()
            print(f"    Status: {response.status_code}")
            
            if result.get("code") == 200:
                reply = result.get("data", {}).get("reply", "")
                print(f"    Reply: {reply[:100]}...")
                print(f"    PASS: {role['name']} response received")
            else:
                print(f"    FAIL: {result}")
                
        except Exception as e:
            print(f"    EXCEPTION: {e}")

    # 测试问候语
    print("\n[测试问候语]")
    greetings = ["你好", "hi", "在吗"]
    for greeting in greetings:
        try:
            response = requests.post(
                f"{BASE_URL}/api/chat/send",
                json={"roleId": "lawyer", "message": greeting},
                headers=headers
            )
            result = response.json()
            if result.get("code") == 200:
                reply = result.get("data", {}).get("reply", "")
                print(f"    '{greeting}' -> {reply[:50]}")
        except Exception as e:
            print(f"    '{greeting}' -> Exception: {e}")

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_all_characters()
