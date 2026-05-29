# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8，确保中文路径和注释正常
"""
文本嵌入模块（Embedding）

本模块负责将文本转换为向量表示，是 RAG 系统的核心组件之一。

主要功能：
1. 加载预训练的文本嵌入模型（BGE-M3）
2. 支持 GPU/CPU 自动检测和设备选择
3. 单文本嵌入（用于用户查询向量化）
4. 批量文本嵌入（用于知识库构建）

技术栈：
- Hugging Face Transformers: 模型加载和推理
- PyTorch: 张量计算和设备管理
- BGE-M3: 中文文本嵌入模型，输出 1024 维向量

工作流程：
用户输入文本 → Tokenizer 分词 → BGE-M3 模型推理 → [CLS] token 提取 → L2 归一化 → 向量

模型配置：
- 默认模型路径: D:\AI_models\BGE-M3
- 输出向量维度: 1024
- 支持半精度（GPU）和全精度（CPU）推理
"""

import gc                      # 垃圾回收模块，用于在内存不足时手动释放内存
import logging                 # 日志模块
from src.config.settings import MODEL_PATH   # 从配置中心获取模型路径
from src.utils.logger import get_logger      # 统一日志接口

logger = get_logger(__name__)  # 获取当前模块的 logger（日志名称自动反映模块路径）

# 从配置中读取嵌入模型的本地存储路径
embedding_model_path = MODEL_PATH["embedding"]

# 全局模型和分词器变量（初始为 None，首次调用时延迟加载）
# 延迟加载很重要：避免模块导入时加载大模型导致启动缓慢或 OOM
model = None        # BGE-M3 模型实例
tokenizer = None    # 对应的分词器实例
device = None       # 计算设备（GPU 或 CPU），初始为 None，首次使用时检测


def check_gpu_availability():
    """
    检查 GPU 可用性并返回推荐设备

    通过 PyTorch 的 cuda.is_available() 判断 GPU 是否存在。
    如果存在 GPU，记录 GPU 信息（名称、数量、显存）供运维参考。

    Returns:
        torch.device: "cuda:0"（有 GPU 时）或 "cpu"（无 GPU 时）
    """
    import torch  # 延迟导入，避免模块加载时 PyTorch 未安装导致崩溃

    if torch.cuda.is_available():
        # GPU 可用，获取并记录 GPU 详细信息
        gpu_count = torch.cuda.device_count()             # GPU 数量
        gpu_name = torch.cuda.get_device_name(0)          # GPU 型号名称
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3  # 显存大小（GB）

        logger.info(f"发现 {gpu_count} 个GPU")
        logger.info(f"GPU名称: {gpu_name}")
        logger.info(f"GPU内存: {gpu_memory:.2f} GB")

        return torch.device("cuda:0")  # 返回主 GPU
    else:
        logger.warning("未检测到GPU，使用CPU")  # CPU 模式下速度会慢很多
        return torch.device("cpu")


def load_model_with_memory_optimization():
    """
    使用内存优化策略加载嵌入模型

    支持多级降级策略（Graceful Degradation）：
    1. 优先使用 GPU 半精度加载（float16），速度最快
    2. 如果 GPU 内存不足（OOM），自动回退到 CPU 全精度
    3. 如果仍失败，记录错误并返回 False

    Returns:
        bool: 模型加载成功返回 True，失败返回 False
    """
    global model, tokenizer, device  # 修改全局变量

    # 首次加载时检测设备
    if device is None:
        device = check_gpu_availability()
        logger.info(f"最终使用设备: {device}")

    try:
        logger.info(f"正在加载模型: {embedding_model_path}")

        # 延迟导入 Transformers 库，避免未安装时阻塞其他功能
        from transformers import AutoModel, AutoTokenizer
        import torch

        # 根据设备类型选择不同的加载策略
        if device.type == "cuda":
            # GPU 模式：使用半精度（float16）加载，显存占用减半，推理速度翻倍
            model = AutoModel.from_pretrained(
                embedding_model_path,
                torch_dtype=torch.float16,      # 半精度浮点（GPU 专用）
                low_cpu_mem_usage=True,         # CPU 内存优化：分片加载而非一次性读入
                device_map="auto"               # 自动分配到可用设备（多 GPU 时自动均衡）
            )
            logger.info("模型以半精度(GPU)加载成功")
        else:
            # CPU 模式：全精度（float32），加载速度较慢但兼容性最好
            model = AutoModel.from_pretrained(
                embedding_model_path,
                torch_dtype=torch.float32,      # 全精度浮点
                low_cpu_mem_usage=True          # 减少 CPU 内存峰值
            )
            model = model.to(device)            # 显式移到 CPU
            logger.info("模型以全精度(CPU)加载成功")

        # 加载对应的分词器（tokenizer）
        # 分词器负责将中文文本转换为模型可理解的 token ID 序列
        tokenizer = AutoTokenizer.from_pretrained(embedding_model_path)
        logger.info("Tokenizer加载成功")

        return True  # 加载成功

    except RuntimeError as e:
        # 捕获 RuntimeError，主要处理 CUDA out-of-memory（OOM）错误
        error_msg = str(e).lower()

        if "out of memory" in error_msg or "内存不足" in error_msg:
            # GPU OOM: 自动降级到 CPU 模式
            logger.warning("内存不足，尝试极限优化模式...")

            try:
                # 先清理内存缓存
                gc.collect()                     # Python 垃圾回收
                if device.type == "cuda":
                    torch.cuda.empty_cache()     # 清空 CUDA 缓存

                # CPU 模式重新加载
                from transformers import AutoModel, AutoTokenizer
                import torch

                model = AutoModel.from_pretrained(
                    embedding_model_path,
                    torch_dtype=torch.float32,   # CPU 模式必须用 float32
                    low_cpu_mem_usage=True,
                    device_map="cpu"             # 强制使用 CPU
                )
                tokenizer = AutoTokenizer.from_pretrained(embedding_model_path)

                logger.info("模型以极限优化模式(CPU)加载成功")
                return True

            except Exception as e2:
                logger.error(f"极限优化模式也失败: {e2}")
                return False  # CPU 模式也失败，返回 False
        else:
            logger.error(f"模型加载失败: {e}")
            return False
    except Exception as e:
        # 其他未知异常
        logger.error(f"模型加载失败: {e}")
        return False


def embed_query(text):
    """
    将单条文本转换为向量嵌入

    这是 RAG 检索流程的第一步，将用户查询转换为向量后才能在向量数据库中检索。
    转换过程：文本 → 分词 → BGE-M3 推理 → [CLS] 向量提取 → L2 归一化

    Args:
        text: 输入文本（用户查询）

    Returns:
        torch.Tensor: 1024 维归一化向量（如果模型加载失败，返回零向量）
    """
    global model, tokenizer

    # 延迟加载：首次调用时自动加载模型
    if model is None or tokenizer is None:
        logger.info("首次调用，开始加载模型...")
        load_model_with_memory_optimization()

        # 如果加载后模型仍为 None，说明加载失败，返回零向量作为降级策略
        if model is None or tokenizer is None:
            logger.warning("模型加载失败，返回空向量")
            import torch
            return torch.zeros(1024, dtype=torch.float32)  # 零向量不会检索到任何结果

    try:
        import torch

        # ==== 第一步：分词 ====
        # 将文本转换为 PyTorch 张量格式的输入
        # return_tensors="pt" 表示返回 PyTorch 的 Tensor（而非 TensorFlow 或 NumPy）
        inputs = tokenizer(
            text,
            return_tensors="pt",     # 返回 PyTorch 张量
            padding=True,            # 填充到 batch 内最大长度（对齐）
            truncation=True,         # 超长文本截断
            max_length=256           # 最大 token 数（超出的部分截断）
        )

        # ==== 第二步：将输入数据移到目标设备 ====
        # 如果使用 GPU，将张量从 CPU 拷贝到 GPU 显存
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # ==== 第三步：模型推理 ====
        # torch.no_grad() 禁用梯度计算，大幅降低内存消耗并加速推理
        # 推理模式下不需要反向传播，所以不需要保存中间梯度
        with torch.no_grad():
            outputs = model(**inputs)

        # ==== 第四步：提取句子向量 ====
        # 使用 [CLS] token（第一个 token）的隐藏状态作为整个句子的表示
        # outputs.last_hidden_state 形状: (batch_size, seq_len, hidden_size)
        # [:, 0, :] 取出每个序列的第一个 token [CLS] 的向量
        embeddings = outputs.last_hidden_state[:, 0, :]

        # ==== 第五步：L2 归一化 ====
        # 归一化后向量长度为 1，可以保证余弦相似度 = 点积
        # 这是向量检索的前提条件
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        # ==== 第六步：返回向量 ====
        # 取出 batch 中第一个（也是唯一一个）样本，移到 CPU 并转为 float32
        return embeddings[0].cpu().float()

    except Exception as e:
        # 推理异常时返回零向量，保证不阻塞主流程
        logger.error(f"嵌入计算失败: {e}")
        import torch
        return torch.zeros(1024, dtype=torch.float32)


def embed_texts(texts, batch_size=32):
    """
    批量计算文本嵌入

    用于知识库构建阶段，将多篇文档批量转换为向量存储到向量数据库中。
    批处理比逐个处理效率更高（利用了 GPU 的并行计算能力）。

    Args:
        texts: 文本列表（如 [text1, text2, text3, ...]）
        batch_size: 每个批次处理的文本数量，默认 32
                   批次大小影响显存占用和速度的平衡

    Returns:
        list: 向量列表，每个元素是 1024 维向量的 Python list 形式
              （可直接存入 Milvus）
    """
    global model, tokenizer

    # 延迟加载模型
    if model is None or tokenizer is None:
        logger.info("首次调用，开始加载模型...")
        load_model_with_memory_optimization()
        if model is None or tokenizer is None:
            logger.warning("模型加载失败，返回零向量")
            import torch
            # 返回与输入等量的零向量，保证数据一致性
            return [torch.zeros(1024, dtype=torch.float32).tolist() for _ in texts]

    import torch
    all_embeddings = []  # 收集所有批次的结果

    # 按批次处理，避免一次性加载过多文本导致显存溢出
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]  # 取出当前批次
        # 每个批次内部的推理流程与单文本相同
        inputs = tokenizer(
            batch,                       # 可以传入字符串列表进行批处理
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0, :]
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        # 将结果转为 Python list 并添加到总结果中
        all_embeddings.extend(embeddings.cpu().float().tolist())

    return all_embeddings  # 返回所有向量（list of list 格式）
