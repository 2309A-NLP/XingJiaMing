# -*- coding: utf-8 -*-
from pymilvus import connections, Collection

# 直接填你的真实信息（不读配置）
connections.connect(
    host="192.168.72.128",
    port=19530
)

# 你的集合名
coll = Collection("law_rag")
schema = coll.schema

print("===== 集合 law_rag 所有字段 =====")
for field in schema.fields:
    print(f"字段名：{field.name}")