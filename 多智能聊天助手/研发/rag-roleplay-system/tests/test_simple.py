import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_full_frontend():
    print("=" * 60)
    print("Frontend Complete Test")
    print("=" * 60)

    all_passed = True

    # 1. Test homepage
    print("\n[1] Test Homepage")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            print("    PASS: Homepage loaded")
            if "page-login" in response.text and "page-register" in response.text:
                print("    PASS: All pages exist")
            if "一问三不知" in response.text:
                print("    PASS: Logo changed to 一问三不知")
            else:
                print("    FAIL: Logo not changed")
                all_passed = False
        else:
            print("    FAIL: Homepage failed")
            all_passed = False
    except Exception as e:
        print(f"    FAIL: {e}")
        all_passed = False

    # 2. Test SMS
    print("\n[2] Test SMS Send")
    try:
        response = requests.post(f"{BASE_URL}/api/sms/send",
                                json={"phone": "13500135000"})
        result = response.json()
        print(f"    Status: {response.status_code}, Response: {result}")
        if result.get("code") == 200:
            print("    PASS: SMS sent")
        else:
            print("    FAIL: SMS failed")
            all_passed = False
    except Exception as e:
        print(f"    FAIL: {e}")
        all_passed = False

    # 3. Test Register
    print("\n[3] Test Register")
    try:
        response = requests.post(f"{BASE_URL}/api/register",
                                json={"phone": "13500135000",
                                      "password": "test123",
                                      "code": "123456",
                                      "name": "Test User"})
        result = response.json()
        print(f"    Status: {response.status_code}")
        print(f"    Response: {result}")

        if result.get("success") == True or result.get("code") == 200:
            print("    PASS: Register success (compatible format)")
            token = result.get("token") or result.get("data", {}).get("token")
            if token:
                print(f"    PASS: Token received: {token[:30]}...")
            return token
        else:
            print(f"    FAIL: Register failed: {result.get('message')}")
            all_passed = False
    except Exception as e:
        print(f"    FAIL: {e}")
        all_passed = False

    return None

def test_login():
    print("\n[4] Test Login")
    try:
        response = requests.post(f"{BASE_URL}/api/login",
                                json={"phone": "13500135000",
                                      "password": "test123"})
        result = response.json()
        print(f"    Status: {response.status_code}")
        print(f"    Response: {result}")

        if result.get("success") == True or result.get("code") == 200:
            print("    PASS: Login success (compatible format)")
            token = result.get("token") or result.get("data", {}).get("token")
            if token:
                print(f"    PASS: Token received: {token[:30]}...")
                return token
        else:
            print(f"    FAIL: Login failed")
            all_passed = False
    except Exception as e:
        print(f"    FAIL: {e}")
    return None

def test_chat(token):
    print("\n[5] Test Chat")

    roles = [
        ("lawyer", "Hello"),
        ("doctor", "I have a cold"),
        ("psych", "I feel stressed")
    ]

    for role_id, message in roles:
        print(f"\n    Testing {role_id}...")
        try:
            response = requests.post(f"{BASE_URL}/api/chat/send",
                                    json={"roleId": role_id, "message": message},
                                    headers={"Authorization": f"Bearer {token}"})
            result = response.json()
            if result.get("code") == 200:
                reply = result.get("data", {}).get("reply", "")
                print(f"    PASS: Got reply: {reply[:60]}...")
            else:
                print(f"    FAIL: Chat failed")
        except Exception as e:
            print(f"    FAIL: {e}")

def test_navigation():
    print("\n[6] Test Navigation Elements")
    try:
        response = requests.get(f"{BASE_URL}/")
        html = response.text

        # Login page should NOT have back button
        login_start = html.find('id="page-login"')
        login_end = html.find('id="page-register"')
        login_section = html[login_start:login_end]

        if 'back-btn' not in login_section:
            print("    PASS: Login page has NO back button")
        else:
            print("    FAIL: Login page still has back button")

        # Register page SHOULD have back button
        register_start = html.find('id="page-register"')
        register_end = html.find('id="page-roles"')
        register_section = html[register_start:register_end]

        if 'back-btn' in register_section:
            print("    PASS: Register page has back button")
        else:
            print("    FAIL: Register page missing back button")

        # Check logo
        if "一问三不知" in html:
            print("    PASS: Logo is '一问三不知'")
        else:
            print("    FAIL: Logo not changed")

    except Exception as e:
        print(f"    FAIL: {e}")

if __name__ == "__main__":
    token = test_full_frontend()
    test_navigation()
    if not token:
        token = test_login()
    if token:
        test_chat(token)
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
