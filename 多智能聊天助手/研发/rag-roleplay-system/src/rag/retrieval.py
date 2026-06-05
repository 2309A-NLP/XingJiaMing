# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8
"""
向量检索模块（Retrieval）

本模块负责与 Milvus 向量数据库交互，是 RAG 系统的核心检索组件。

主要功能：
1. Milvus 连接管理（带重试机制和降级策略）
2. 向量相似性搜索（核心检索：将用户查询向量与知识库向量匹配）
3. 向量数据插入（知识库构建：将文档向量写入数据库）
4. 集合创建（初始化知识库：创建向量存储空间）

技术栈：
- pymilvus: Milvus Python 客户端库，提供向量数据库的 CRUD 操作
- socket: 用于连接端口检测

架构说明：
- 连接失败时自动降级（返回空结果），不阻塞主流程
- Milvus 不可用时，RAG 系统以降级模式运行（仅靠 LLM 自身知识）

Milvus 检索流程：
用户查询 → 嵌入向量 → Milvus search → 返回 top_k 相似文本 → 送入 Rerank
"""

import time          # 时间模块，用于重试间隔
import socket        # socket 模块，用于检测 Milvus 端口连通性
from ..config.settings import MILVUS_CONFIG  # 导入 Milvus 连接配置

# ==================== 全局变量 ====================
client = None                    # Milvus 客户端实例（全局单例）
COLLECTION_NAME = MILVUS_CONFIG["collection_name"]  # 默认集合名称（law_rag）
milvus_available = False         # Milvus 是否可用标志（降级策略依据）
collections = []                 # 已存在的集合列表缓存


def test_port(host, port, timeout=2):
    """
    测试指定主机的端口是否开放

    通过 TCP 三次握手的 connect_ex 判断端口是否可连接。
    用于在正式连接 Milvus 前快速检查服务是否启动。

    Args:
        host: 主机地址（IP 或域名）
        port: 端口号
        timeout: 连接超时时间（秒），默认 2 秒

    Returns:
        bool: 端口开放返回 True，否则返回 False
    """
    try:
        # 创建 TCP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)       # 设置超时，避免长时间阻塞
        result = sock.connect_ex((host, port))  # connect_ex 返回 0 表示成功
        sock.close()                   # 关闭 socket
        return result == 0             # 返回 True（端口开放）或 False（关闭）
    except Exception as e:
        return False                   # 异常情况视为端口不可用


def connect_milvus_with_retry(max_retries=3, retry_delay=2):
    """
    带重试机制的 Milvus 连接

    在连接失败时自动重试，提高系统在服务启动阶段或网络不稳定时的健壮性。
    如果最终连接失败，系统不会崩溃，而是设置 milvus_available = False，
    后续检索操作会返回空结果，实现优雅降级。

    重试策略：
    1. 先测试端口是否开放（快速失败）
    2. 逐次尝试连接，每次间隔 retry_delay 秒
    3. 3 次重试后仍失败则标记为不可用

    Args:
        max_retries: 最大重试次数，默认 3 次
        retry_delay: 重试间隔（秒），默认 2 秒

    Returns:
        MilvusClient 或 None: 成功返回客户端实例，失败返回 None
    """
    global client, milvus_available, collections

    milvus_host = MILVUS_CONFIG['host']  # Milvus 服务器 IP
    milvus_port = MILVUS_CONFIG['port']  # Milvus 端口

    # 第一步：快速检查端口是否开放，避免长时间等待连接超时
    if not test_port(milvus_host, milvus_port):
        print(f"警告: Milvus 端口 {milvus_host}:{milvus_port} 未开放，将使用模拟数据")
        milvus_available = False
        return None

    try:
        # 延迟导入 pymilvus（避免未安装时影响其他模块）
        from pymilvus import MilvusClient, exceptions

        # 第二步：循环重试连接
        for attempt in range(max_retries):
            try:
                # 创建 Milvus HTTP 客户端（v2.x 版本使用 HTTP 协议）
                client = MilvusClient(
                    uri=f"http://{milvus_host}:{milvus_port}",  # HTTP 连接地址
                    timeout=5,          # 连接超时 5 秒
                    keep_alive=True     # 保持长连接，减少重复握手
                )

                # 通过列出集合验证连接是否正常
                collections = client.list_collections()

                print(f"Milvus 连接成功 (尝试 {attempt + 1}/{max_retries})")
                milvus_available = True  # 标记为可用
                return client

            except exceptions.MilvusException as e:
                # Milvus 服务端返回的异常（如连接拒绝、超时等）
                print(f"Milvus 连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # 非最后一次尝试，等待后重试
                    print(f"   等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    # 最后一次尝试也失败了，标记为不可用
                    print(f"警告: Milvus 连接失败，已重试 {max_retries} 次，将使用模拟数据")
                    milvus_available = False
                    collections = []
                    return None

    except ImportError:
        # pymilvus 库未安装
        print("警告: pymilvus 未安装，将使用模拟数据")
        milvus_available = False
        return None


# 模块加载时自动建立 Milvus 连接
# 这样在应用启动阶段就能确定 Milvus 的可用性
client = connect_milvus_with_retry()


def search_vector(vector, collection_name=COLLECTION_NAME, top_k=5):
    """
    在 Milvus 中搜索相似向量（核心检索功能）

    将用户查询的向量表示与知识库中的向量进行相似性匹配。
    使用 L2 距离（欧氏距离）度量向量相似度，距离越小越相似。

    返回的文本将经过 Rerank 精排后，作为 LLM 的参考上下文。

    Args:
        vector: 查询向量（1024 维，PyTorch Tensor 或 list 格式）
        collection_name: 集合名称，默认 law_rag（法律知识库）
        top_k: 返回的相似结果数量，默认 5 条

    Returns:
        list: 搜索结果列表，格式为 [[{id, distance, entity: {text}}, ...], ...]
              每个搜索结果包含距离分数和原文文本
    """
    # 检查 Milvus 是否可用，不可用时返回空列表（降级）
    if not milvus_available or client is None:
        print("Milvus 不可用，返回空结果")
        return []

    try:
        # 将向量转换为 Python list 格式
        # 兼容不同的输入类型：PyTorch Tensor、NumPy array、Python list
        if hasattr(vector, 'tolist'):     # PyTorch Tensor / Milvus 向量
            vec_list = vector.tolist()
        elif hasattr(vector, 'numpy'):    # 某些自定义类型
            vec_list = vector.numpy().tolist()
        else:
            vec_list = list(vector)       # 已经是 list 或可迭代对象

        # 执行向量相似性搜索
        # client.search 是 Milvus 的核心搜索 API
        results = client.search(
            collection_name=collection_name,   # 搜索哪个知识库
            data=[vec_list],                   # 查询向量（包装为列表，支持多向量搜索）
            limit=top_k,                       # 返回 top_k 个最相似结果
            output_fields=["text"]             # 需要返回的字段（文本内容）
        )
        return results

    except Exception as e:
        print(f"Milvus 搜索失败: {e}")
        return []  # 异常时返回空列表


def insert_vectors(vectors, texts, collection_name=COLLECTION_NAME):
    """
    向 Milvus 插入向量数据（用于知识库构建）

    将文档文本及其向量表示批量插入到指定集合中。
    通常在以下场景调用：
    1. 启动时初始化知识库
    2. 管理员手动更新知识库
    3. 新增文档入库

    Args:
        vectors: 向量列表，每个向量是 1024 维的 list
        texts: 文本列表，与向量一一对应（vectors[i] 对应 texts[i]）
        collection_name: 目标集合名称

    Returns:
        dict | None: 插入结果（包含插入数量等信息），失败返回 None
    """
    # 检查 Milvus 是否可用
    if not milvus_available or client is None:
        print("Milvus 不可用，跳过插入")
        return None

    try:
        # 构建实体列表：每个实体包含向量和原文文本
        entities = [
            {"vector": vectors[i], "text": texts[i]}  # vector 字段用于搜索，text 用于返回
            for i in range(len(vectors))
        ]

        # 批量插入到 Milvus
        result = client.insert(
            collection_name=collection_name,
            data=entities
        )
        return result

    except Exception as e:
        print(f"Milvus 插入失败: {e}")
        return None


def create_collection(collection_name, dim=MILVUS_CONFIG["dim"]):
    """
    创建 Milvus 集合（即数据库中的"表"）

    在知识库构建前调用，如果集合已存在则直接返回。
    集合相当于关系数据库中的表，用于存储具有相同维度的向量。

    Args:
        collection_name: 集合名称
        dim: 向量维度，默认 1024（必须与 BGE-M3 模型输出维度一致）

    Returns:
        bool: 创建成功（或已存在）返回 True，失败返回 False
    """
    # 检查 Milvus 是否可用
    if not milvus_available or client is None:
        print("Milvus 不可用，跳过创建集合")
        return False

    try:
        # 检查集合是否已存在，避免重复创建报错
        if collection_name in client.list_collections():
            print(f"集合 {collection_name} 已存在")
            return True

        # 创建新集合
        # 需要指定向量维度和距离度量方式
        client.create_collection(
            collection_name=collection_name,  # 集合名
            dimension=dim,                    # 向量维度（1024）
            metric_type="L2"                  # 距离度量：L2 欧氏距离
        )
        print(f"集合 {collection_name} 创建成功")
        return True

    except Exception as e:
        print(f"创建集合失败: {e}")
        return False
