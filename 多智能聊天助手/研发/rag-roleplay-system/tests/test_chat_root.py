import requests

# 创建不使用代理的会话
session = requests.Session()
session.trust_env = False

# 测试心理医生角色
response = session.post(
    'http://localhost:8000/api/chat',
    json={'user_id': 8, 'role_id': 'psych', 'message': '你好'}
)
print("心理医生回复:", response.text)

# 测试医疗门诊角色
response = session.post(
    'http://localhost:8000/api/chat',
    json={'user_id': 8, 'role_id': 'doctor', 'message': '你好'}
)
print("医疗门诊回复:", response.text)

# 测试刑事律师角色
response = session.post(
    'http://localhost:8000/api/chat',
    json={'user_id': 8, 'role_id': 'lawyer', 'message': '你好'}
)
print("刑事律师回复:", response.text)