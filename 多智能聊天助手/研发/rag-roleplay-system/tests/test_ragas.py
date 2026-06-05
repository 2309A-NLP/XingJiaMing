# -*- coding: utf-8 -*-
"""
RAGAS 评估测试 — 基于官方 ragas 库的 RAG 系统质量评估

使用项目 DeepSeek LLM 作裁判 + BGE-M3 作嵌入评估器。

评估指标:
  1. Faithfulness      — 回答是否基于上下文（非幻觉）
  2. AnswerRelevancy   — 回答与问题语义相关度
  3. ContextPrecision  — 检索文档中相关比例
  4. ContextRecall     — 标准答案信息在上下文中的覆盖

用法:
  source venv/bin/activate
  python tests/test_ragas.py               # 全量 (15题)
  python tests/test_ragas.py --quick        # 快速 (6题)
  python tests/test_ragas.py --role psych   # 单角色
"""

import os
import sys
import json
import time
import logging
import argparse
from typing import List, Tuple
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ragas_test")


# ============================================================================
# 测试数据集 — 每个角色 5 道题 + 参考答案
# ============================================================================

@dataclass
class TestQuestion:
    question: str
    ground_truth: str


TEST_DATASET = {
    "lawyer": {
        "role_name": "林律（刑事律师）",
        "knowledge_base": "law_rag",
        "questions": [
            TestQuestion(
                "盗窃罪的量刑标准是什么？",
                "盗窃公私财物数额较大的（1000元以上）处三年以下有期徒刑、拘役或管制；"
                "数额巨大（3万元以上）处三年以上十年以下有期徒刑；"
                "数额特别巨大（30万元以上）处十年以上有期徒刑或无期徒刑。"
            ),
            TestQuestion(
                "正当防卫的构成要件有哪些？",
                "正当防卫需同时满足：1.存在不法侵害；2.不法侵害正在进行；"
                "3.防卫目的是保护合法权益；4.防卫行为针对不法侵害人本人；"
                "5.防卫未明显超过必要限度。"
            ),
            TestQuestion(
                "故意伤害罪和过失致人重伤罪的区别是什么？",
                "故意伤害罪主观上有伤害故意，最高可判死刑；过失致人重伤罪主观上是过失，"
                "处三年以下有期徒刑或拘役。核心区别在于主观罪过形式不同。"
            ),
            TestQuestion(
                "缓刑的适用条件是什么？",
                "缓刑适用于被判处拘役或三年以下有期徒刑的犯罪分子，需满足：犯罪情节较轻、"
                "有悔罪表现、没有再犯危险、宣告缓刑对所居住社区无重大不良影响。"
            ),
            TestQuestion(
                "自首和坦白有什么区别？",
                "自首是犯罪后自动投案并如实供述，可从轻或减轻处罚；"
                "坦白是被动归案后如实供述，可从轻处罚。自首的从宽幅度大于坦白。"
            ),
        ]
    },
    "psych": {
        "role_name": "张心理（心理医生）",
        "knowledge_base": "psychology_rag",
        "questions": [
            TestQuestion(
                "如何缓解焦虑情绪？",
                "缓解焦虑的方法：深呼吸练习、正念冥想、规律运动、保持充足睡眠、"
                "认知行为疗法(CBT)、必要时寻求专业心理咨询。"
            ),
            TestQuestion(
                "抑郁症的常见症状有哪些？",
                "抑郁症常见症状：持续情绪低落、兴趣减退、睡眠障碍、食欲改变、"
                "疲劳无力、注意力下降、自我否定、严重时有自杀意念。"
            ),
            TestQuestion(
                "如何帮助有心理困扰的朋友？",
                "帮助方法：倾听不评判、表达关心和支持、鼓励寻求专业帮助、"
                "陪伴参加活动、关注自杀风险信号、保护自己的心理边界。"
            ),
            TestQuestion(
                "什么是认知行为疗法？",
                "认知行为疗法(CBT)是通过识别和改变负面的自动化思维和行为模式，"
                "来改善情绪和心理状态的结构化心理治疗方法，对抑郁和焦虑有显著效果。"
            ),
            TestQuestion(
                "压力过大会导致哪些身体反应？",
                "压力过大的身体反应：头痛、肌肉紧张、失眠、消化问题、心悸、"
                "免疫力下降、食欲变化、内分泌失调等。"
            ),
        ]
    },
    "doctor": {
        "role_name": "刘医学（医疗门诊）",
        "knowledge_base": "medical_rag",
        "questions": [
            TestQuestion(
                "高血压患者日常生活需要注意什么？",
                "高血压注意事项：低盐饮食(每日<6g)、规律运动、控制体重、戒烟限酒、"
                "定期监测血压、遵医嘱服药、保持情绪稳定。"
            ),
            TestQuestion(
                "糖尿病的典型症状和诊断标准是什么？",
                "糖尿病典型症状：多饮多尿多食体重减轻(三多一少)；"
                "诊断标准：空腹血糖≥7.0mmol/L或餐后2h血糖≥11.1mmol/L或HbA1c≥6.5%。"
            ),
            TestQuestion(
                "感冒和流感怎么区分？",
                "感冒症状较轻(流涕、咽痛)，发热不明显；流感症状重"
                "(高热39-40℃、全身酸痛、乏力)，易引发并发症。流感需及早抗病毒治疗。"
            ),
            TestQuestion(
                "如何预防心血管疾病？",
                "预防心血管疾病：均衡饮食(多蔬果少油脂)、每周150分钟中等强度运动、"
                "控制三高、戒烟限酒、保持健康体重、定期体检。"
            ),
            TestQuestion(
                "儿童发热应该怎么处理？",
                "儿童发热处理：体温<38.5°C物理降温(温水擦浴、减少衣物)；"
                "≥38.5°C可用退烧药(布洛芬或对乙酰氨基酚)；观察精神状态，持续高热或精神差及时就医。"
            ),
        ]
    }
}


# ============================================================================
# RAG 管线封装
# ============================================================================

class RAGPipeline:
    """封装项目 RAG 管线"""

    def __init__(self):
        self._llm_client = None
        self._llm_model = None

    def _init_llm(self):
        if self._llm_client is None:
            from openai import OpenAI
            from src.config.settings import LLM_CONFIG
            self._llm_client = OpenAI(
                api_key=LLM_CONFIG['api_key'],
                base_url=LLM_CONFIG['api_url']
            )
            self._llm_model = LLM_CONFIG['model']

    def retrieve(self, question: str, knowledge_base: str,
                 top_k: int = 5) -> Tuple[List[str], bool]:
        """向量检索 + 重排序 → (文档列表, 是否真实检索)"""
        from src.rag.retrieval import milvus_available, client, collections, search_vector
        from src.rag.embedding import embed_query
        from src.rag.rerank import rerank

        collection_name = f"{knowledge_base}_rag"

        if milvus_available and client and collection_name in collections:
            try:
                vec = embed_query(question)
                results = search_vector(vec, collection_name, top_k=top_k)
                if results:
                    docs = [hit["entity"]["text"] for hit in results[0]]
                    docs = rerank(question, docs)
                    return docs[:3], True
            except Exception as e:
                logger.warning(f"真实检索失败: {e}")

        return [], False

    def generate(self, question: str, contexts: List[str],
                 role_name: str) -> str:
        """调用 DeepSeek 生成回答"""
        self._init_llm()

        context_text = "\n---\n".join(contexts) if contexts else "暂无相关知识"

        system_prompt = f"""你是{role_name}，请根据以下知识回答问题。

【可用知识】
{context_text}

【要求】
1. 基于上述知识回答，不要编造信息
2. 回答要专业、准确、完整
3. 如果知识中没有答案，诚实说明"""

        try:
            response = self._llm_client.chat.completions.create(
                model=self._llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                temperature=0.3,
                max_tokens=512
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return f"[生成失败: {e}]"


# ============================================================================
# 创建 RAGAS 评估器（使用官方 ragas 库）
# ============================================================================

def _build_bge_embeddings(model_path: str):
    """
    将项目本地 BGE-M3 模型包装为 ragas 兼容的嵌入器。
    同时实现 embed_query / embed_documents (旧接口) 和
    embed_text / embed_texts (新接口)。
    """
    from ragas.embeddings.base import BaseRagasEmbeddings

    class BGERagasEmbeddings(BaseRagasEmbeddings):
        def __init__(self):
            super().__init__()
            from src.rag.embedding import embed_query, embed_texts as bge_embed_texts
            self._embed_query_fn = embed_query
            self._embed_texts_fn = bge_embed_texts

        def embed_query(self, text: str) -> list:
            vec = self._embed_query_fn(text)
            return vec.tolist() if hasattr(vec, 'tolist') else list(vec)

        def embed_documents(self, texts: list) -> list:
            vecs = self._embed_texts_fn(texts)
            result = []
            for v in vecs:
                result.append(v.tolist() if hasattr(v, 'tolist') else list(v))
            return result

        async def aembed_query(self, text: str) -> list:
            return self.embed_query(text)

        async def aembed_documents(self, texts: list) -> list:
            return self.embed_documents(texts)

        def embed_text(self, text: str, **kwargs) -> list:
            return self.embed_query(text)

        async def aembed_text(self, text: str, **kwargs) -> list:
            return self.embed_query(text)

    return BGERagasEmbeddings()


def build_ragas_evaluator():
    """
    构建 RAGAS 评估组件：
    - 裁判 LLM: DeepSeek API (via ragas llm_factory)
    - 嵌入模型: BGE-M3 本地 (via sentence-transformers)
    - 使用 ragas.metrics 内部 _Faithfulness, _AnswerRelevancy 等 Metric 子类
    """
    from openai import OpenAI
    from src.config.settings import LLM_CONFIG, MODEL_PATH
    from ragas.llms import llm_factory
    from ragas.embeddings.base import BaseRagasEmbeddings
    from ragas.metrics import (
        _Faithfulness,
        _AnswerRelevancy,
        _ContextPrecision,
        _ContextRecall,
    )

    # 裁判 LLM — DeepSeek API
    judge_client = OpenAI(
        api_key=LLM_CONFIG['api_key'],
        base_url=LLM_CONFIG['api_url']
    )
    judge_llm = llm_factory(
        model="deepseek-v4-flash",
        provider="openai",
        client=judge_client,
        temperature=0.0,
        max_tokens=8192,
    )

    # 评估用嵌入模型 — 本地 BGE-M3 (适配 ragas 接口)
    eval_embeddings = _build_bge_embeddings(MODEL_PATH["embedding"])

    # 构建指标 (使用 Metric 子类，而非 collections 中的 SimpleBaseMetric)
    metrics = [
        _Faithfulness(llm=judge_llm),
        _AnswerRelevancy(llm=judge_llm, embeddings=eval_embeddings),
        _ContextPrecision(llm=judge_llm),
        _ContextRecall(llm=judge_llm),
    ]

    return metrics, judge_llm


# ============================================================================
# 评估执行
# ============================================================================

def run_evaluation(roles: List[str], quick: bool = False) -> dict:
    """运行 RAGAS 评估，返回结果字典"""
    from ragas import EvaluationDataset, SingleTurnSample, evaluate as ragas_evaluate

    pipeline = RAGPipeline()
    metrics, _ = build_ragas_evaluator()

    all_samples = []
    results_detail = []

    for role_key in roles:
        if role_key not in TEST_DATASET:
            logger.warning(f"未知角色: {role_key}")
            continue

        role_data = TEST_DATASET[role_key]
        questions = role_data["questions"]
        if quick:
            questions = questions[:2]

        logger.info(f"\n{'='*60}")
        logger.info(f"评估: {role_data['role_name']} ({len(questions)} 题)")
        logger.info(f"{'='*60}")

        for i, tq in enumerate(questions):
            logger.info(f"[{i+1}/{len(questions)}] {tq.question}")

            # Step 1: 检索
            kb = role_data["knowledge_base"]
            contexts, real_retrieval = pipeline.retrieve(tq.question, kb, top_k=5)

            if not contexts:
                logger.info("  -> Milvus 为空，使用 ground_truth 作模拟上下文")
                contexts = [tq.ground_truth]
                real_retrieval = False

            # Step 2: 生成
            answer = pipeline.generate(tq.question, contexts, role_data['role_name'])
            logger.info(f"  回答: {answer[:80]}...")

            # Step 3: 构建 RAGAS 样本
            sample = SingleTurnSample(
                user_input=tq.question,
                response=answer,
                retrieved_contexts=contexts,
                reference=tq.ground_truth,
            )
            all_samples.append(sample)
            results_detail.append({
                "role": role_data['role_name'],
                "question": tq.question,
                "answer": answer,
                "contexts": contexts,
                "used_real_retrieval": real_retrieval,
                "reference": tq.ground_truth,
            })

            time.sleep(0.3)

    # 保存中间数据，防止后续报告解析崩溃时丢失
    import pickle
    import tempfile
    intermediate_path = os.path.join(tempfile.gettempdir(), "ragas_intermediate.pkl")
    with open(intermediate_path, 'wb') as f:
        pickle.dump((all_samples, results_detail), f)
    logger.info(f"中间数据已保存 (生成阶段完成): {intermediate_path}")

    # 批量评估
    logger.info(f"\n{'='*60}")
    logger.info(f"RAGAS 评分中... ({len(all_samples)} 样本, 4 指标)")
    logger.info(f"{'='*60}")

    dataset = EvaluationDataset(samples=all_samples)
    result = ragas_evaluate(dataset, metrics=metrics)

    # 立即保存原始 DataFrame，防止报告解析时丢失数据
    df_raw = result.to_pandas()
    cache_path = os.path.join(tempfile.gettempdir(), "ragas_raw_df.pkl")
    with open(cache_path, 'wb') as f:
        pickle.dump((df_raw, results_detail), f)
    logger.info(f"原始评分 DataFrame 已缓存: {cache_path}")

    return result, results_detail


# ============================================================================
# 报告输出
# ============================================================================

def _safe_numeric(val):
    """尝试将值转为 float；不可转换则返回 None（过滤掉 LLM 文本等）"""
    import numpy as np
    if isinstance(val, (int, float, np.floating, np.integer)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return None


def print_report(result, details: list):
    """打印评估报告 (pandas DataFrame 格式的 result)"""
    n = len(details)

    import numpy as np
    df = result.to_pandas()
    metric_cols = [c for c in df.columns if c != 'user_input']
    scores = {}
    for col in metric_cols:
        vals = df[col].dropna().values
        numeric_vals = [v for v in (_safe_numeric(x) for x in vals) if v is not None]
        scores[col] = float(np.mean(numeric_vals)) if numeric_vals else float('nan')

    valid_scores = {k: v for k, v in scores.items() if not np.isnan(v)}
    overall = sum(valid_scores.values()) / len(valid_scores) if valid_scores else 0

    print("\n" + "=" * 70)
    print("  RAGAS 评估报告 — RAG 角色扮演系统")
    print("  (基于官方 ragas 库, 裁判: DeepSeek, 嵌入: BGE-M3)")
    print("=" * 70)
    print(f"  样本数: {n}  |  真实检索: "
          f"{sum(1 for d in details if d['used_real_retrieval'])}/{n}")
    print()
    print("  ┌──────────────────────┬──────────┐")
    print("  │ 指标                 │   平均分 │")
    print("  ├──────────────────────┼──────────┤")
    for name, val in scores.items():
        print(f"  │ {name:<20} │    {val:.2f}  │")
    print("  ├──────────────────────┼──────────┤")
    print(f"  │ RAGAS Score          │    {overall:.2f}  │")
    print("  └──────────────────────┴──────────┘")
    print()

    if overall >= 0.80:
        print("  ✅ 优秀 — RAG 表现良好")
    elif overall >= 0.60:
        print("  ⚠️  良好 — 有改进空间")
    elif overall >= 0.40:
        print("  ⚠️  一般 — 建议优化检索策略或知识库覆盖度")
    else:
        print("  ❌ 较差 — 建议排查知识库、Prompt 或 LLM 配置")

    # 按角色汇总
    role_scores = {}
    for i, d in enumerate(details):
        role = d["role"]
        role_scores.setdefault(role, []).append(i)

    print("\n  --- 按角色 ---")
    for role, idxs in role_scores.items():
        role_avg = {}
        for col in metric_cols:
            vals = df.iloc[idxs][col].dropna().values
            sv = [v for v in (_safe_numeric(x) for x in vals) if v is not None]
            role_avg[col] = float(np.mean(sv)) if sv else float('nan')
        v_role = {k: v for k, v in role_avg.items() if not np.isnan(v)}
        r_score = sum(v_role.values()) / len(v_role) if v_role else 0
        parts = " ".join(f"{k}={v:.2f}" for k, v in role_avg.items())
        print(f"  {role}: {parts} → Score={r_score:.2f}")

    # 逐题
    print("\n  --- 逐题详情 ---")
    for i, d in enumerate(details):
        parts_i = []
        for col in metric_cols:
            raw = df.iloc[i][col]
            nv = _safe_numeric(raw)
            if nv is not None:
                parts_i.append(f"{col}={nv:.2f}")
            else:
                parts_i.append(f"{col}=N/A")
        print(f"  [{i+1}] {d['role']} | Q: {d['question']}")
        print(f"      {' '.join(parts_i)} | 真实检索={'是' if d['used_real_retrieval'] else '否'}")

    print("\n" + "=" * 70)
    return scores, overall


def export_json(result, details: list, filepath: str):
    """导出 JSON 结果"""
    df = result.to_pandas()
    metric_cols = [c for c in df.columns if c != 'user_input']

    n = len(details)
    data = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "ragas (official)",
        "judge_llm": "deepseek-v4-flash",
        "embedding_model": "BGE-M3",
        "total_samples": n,
        "avg_scores": {},
        "results": []
    }
    for col in metric_cols:
        vals = df[col].dropna().values
        numeric_vals = [v for v in (_safe_numeric(x) for x in vals) if v is not None]
        if numeric_vals:
            data["avg_scores"][col] = round(float(sum(numeric_vals) / len(numeric_vals)), 4)
        else:
            data["avg_scores"][col] = "N/A"

    for i, d in enumerate(details):
        entry = {**d}
        for col in metric_cols:
            nv = _safe_numeric(df.iloc[i][col])
            entry[col] = round(nv, 4) if nv is not None else "N/A"
        data["results"].append(entry)

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"结果已导出: {filepath}")


# ============================================================================
# 主入口
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS 评估 (官方 ragas 库)")
    parser.add_argument("--role", type=str, default=None,
                        help="指定角色: lawyer/psych/doctor")
    parser.add_argument("--quick", action="store_true",
                        help="快速模式 (每角色仅2题)")
    parser.add_argument("--export", type=str, default=None,
                        help="导出 JSON 路径")
    args = parser.parse_args()

    roles = [args.role] if args.role else ["lawyer", "psych", "doctor"]
    logger.info(f"RAGAS 评估开始: 角色={roles}, 快速={args.quick}")

    result, details = run_evaluation(roles, quick=args.quick)
    scores, overall = print_report(result, details)

    export_path = args.export or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ragas_results.json"
    )
    export_json(result, details, export_path)
