from pymilvus import connections, Collection, utility
from sentence_transformers import SentenceTransformer

# 你的配置
MILVUS_CONFIG = {
    "host": "192.168.72.128",
    "port": 19530,
    "collection_name": "law_rag",
    "dim": 1024
}

# 连接 Milvus
connections.connect(
    alias="default",
    host=MILVUS_CONFIG["host"],
    port=MILVUS_CONFIG["port"]
)

# 查看集合是否存在
print("所有集合：", utility.list_collections())
if MILVUS_CONFIG["collection_name"] not in utility.list_collections():
    print("❌ 集合不存在！")
    exit()

# 加载集合并查看数据量
coll = Collection(MILVUS_CONFIG["collection_name"])
coll.load()
print(f"✅ 集合已加载，数据量：{coll.num_entities}")