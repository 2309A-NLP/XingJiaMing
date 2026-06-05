import requests

BASE_URL = "http://127.0.0.1:8000"

def test_register_flow():
    print("=" * 60)
    print("Testing Register Page - Captcha Flow")
    print("=" * 60)

    # 1. Check register page structure
    print("\n[1] Check Register Page Structure")
    try:
        response = requests.get(f"{BASE_URL}/")
        html = response.text
        
        # Check if captcha is hidden by default
        if 'id="captchaSection"' in html and 'style="display:none"' in html:
            print("    [OK] Captcha section is hidden by default")
        else:
            print("    [FAIL] Captcha section is not hidden")
        
        # Check send sms button exists
        if 'onclick="sendSmsCode()"' in html:
            print("    [OK] Send SMS button exists")
        else:
            print("    [FAIL] Send SMS button not found")
            
    except Exception as e:
        print(f"    [FAIL] Failed to get page: {e}")

    # 2. Test SMS send
    print("\n[2] Test SMS Send")
    try:
        response = requests.post(f"{BASE_URL}/api/sms/send",
                                json={"phone": "13900139002"})
        result = response.json()
        print(f"    Status: {response.status_code}")
        print(f"    Response: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    [OK] SMS sent successfully")
        else:
            print("    [FAIL] SMS send failed")
    except Exception as e:
        print(f"    [FAIL] SMS send exception: {e}")

    # 3. Test Register
    print("\n[3] Test Register")
    try:
        response = requests.post(f"{BASE_URL}/api/register",
                                json={"phone": "13900139002",
                                      "password": "test123456",
                                      "code": "1234",
                                      "name": "Test User"})
        result = response.json()
        print(f"    Status: {response.status_code}")
        print(f"    Response: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    [OK] Register success")
        else:
            print(f"    [FAIL] Register failed: {result.get('message')}")
    except Exception as e:
        print(f"    [FAIL] Register exception: {e}")

    # 4. Test Login
    print("\n[4] Test Login")
    try:
        response = requests.post(f"{BASE_URL}/api/login",
                                json={"phone": "13900139002",
                                      "password": "test123456"})
        result = response.json()
        print(f"    Status: {response.status_code}")
        print(f"    Response: {result}")
        if result.get("code") == 200 or result.get("success") == True:
            print("    [OK] Login success")
        else:
            print(f"    [FAIL] Login failed: {result.get('message')}")
    except Exception as e:
        print(f"    [FAIL] Login exception: {e}")

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_register_flow()
