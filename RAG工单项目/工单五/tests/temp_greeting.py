import sys; sys.path.insert(0, '.')
from api.routes.query import _is_greeting
tests = ['你好', '您好', 'hello', '公司老板是谁']
for q in tests:
    print(f'{q} -> greeting: {_is_greeting(q)}')
