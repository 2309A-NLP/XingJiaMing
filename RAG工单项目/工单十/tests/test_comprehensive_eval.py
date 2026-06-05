"""RAG 系统全方位评估脚本

评估维度：
  A. 关键词匹配（现有方法）
  B. LLM-as-Judge（现有方法）
  C. RAGAS 风格指标（手动实现：Faithfulness, Answer Relevancy, Context Precision, Context Recall）
  D. ROUGE 分数（ROUGE-1, ROUGE-2, ROUGE-L）
  E. BERTScore（语义相似度）
  F. 检索质量指标（Hit Rate, MRR, NDCG）
  G. 性能指标（响应时间）

使用方式：
  cd 工单七
  .venv/Scripts/python.exe tests/test_comprehensive_eval.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import logging
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 设置项目根目录
_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
load_dotenv(override=True)

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('rag_eval')
logger.setLevel(logging.INFO)

# ============================================================
# 数据结构
# ============================================================

@dataclass
class TestCase:
    """测试用例"""
    id: int
    question: str
    ground_truth: str
    expected_keywords: List[str]
    expected_sources: List[str]
    category: str = "general"
    difficulty: str = "medium"


@dataclass
class QueryResult:
    """单次查询结果"""
    question: str
    answer: str
    contexts: List[str]          # 检索到的上下文文本列表
    context_details: List[dict]  # 检索到的上下文详情
    response_time_ms: float
    ground_truth: str = ""


@dataclass
class EvalScores:
    """单条评估分数"""
    # 关键词匹配
    keyword_hits: int = 0
    keyword_total: int = 0
    keyword_precision: float = 0.0

    # LLM-as-Judge
    llm_correct: Optional[bool] = None
    llm_reason: str = ""

    # RAGAS 风格指标（手动实现）
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0

    # ROUGE 分数
    rouge1_f: float = 0.0
    rouge2_f: float = 0.0
    rougeL_f: float = 0.0

    # BERTScore
    bertscore_p: float = 0.0
    bertscore_r: float = 0.0
    bertscore_f1: float = 0.0

    # 检索质量
    hit_rate: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0

    # 性能
    response_time_ms: float = 0.0


@dataclass
class EvalReport:
    """综合评估报告"""
    total_questions: int = 0
    avg_keyword_precision: float = 0.0
    llm_accuracy: float = 0.0
    avg_faithfulness: float = 0.0
    avg_answer_relevancy: float = 0.0
    avg_context_precision: float = 0.0
    avg_context_recall: float = 0.0
    avg_rouge1: float = 0.0
    avg_rouge2: float = 0.0
    avg_rougeL: float = 0.0
    avg_bertscore_f1: float = 0.0
    avg_hit_rate: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg: float = 0.0
    avg_response_time_ms: float = 0.0
    results: List[dict] = field(default_factory=list)


# ============================================================
# 评估方法实现
# ============================================================

def eval_keyword_matching(answer: str, expected_keywords: List[str]) -> tuple:
    """A. 关键词匹配评估"""
    hits = 0
    for kw in expected_keywords:
        if kw in answer:
            hits += 1
    total = len(expected_keywords)
    precision = hits / max(total, 1)
    return hits, total, precision


def eval_llm_judge(question: str, ground_truth: str, answer: str, client, model: str) -> tuple:
    """B. LLM-as-Judge 评估"""
    try:
        judge_prompt = f"""请判断以下AI回答是否正确。

问题：{question}
参考答案：{ground_truth}
AI回答：{answer[:500]}

评判标准：
1. AI回答是否包含参考答案中的关键信息
2. AI回答的事实是否与参考答案一致
3. AI回答是否有明显的错误或遗漏

请只返回JSON格式：{{"ok": true/false, "r": "简短原因"}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0,
            max_tokens=200,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r'\{[^}]+\}', content)
        if m:
            j = json.loads(m.group())
            return j.get('ok', None), j.get('r', '')
    except Exception as e:
        logger.warning('LLM Judge 失败: %s', str(e)[:80])
    return None, ""


def eval_ragas_style(question: str, contexts: List[str], answer: str,
                     ground_truth: str, client, model: str) -> Dict[str, float]:
    """C. RAGAS 风格指标评估（手动实现）

    使用 LLM-as-Judge 实现 RAGAS 的四个核心指标：
    - Faithfulness: 回答是否基于检索到的内容
    - Answer Relevancy: 回答是否切题
    - Context Precision: 检索内容是否精准
    - Context Recall: 相关内容是否都被检索到
    """
    results = {
        'faithfulness': 0.0,
        'answer_relevancy': 0.0,
        'context_precision': 0.0,
        'context_recall': 0.0,
    }

    context_text = '\n'.join(contexts[:5])[:2000]

    # Faithfulness: 回答是否基于检索内容
    try:
        faith_prompt = f"""评估以下回答是否完全基于提供的检索内容（没有编造信息）。

检索内容：
{context_text}

AI回答：{answer[:500]}

评分标准（0-10）：
- 10: 回答完全基于检索内容，没有编造
- 7-9: 回答大部分基于检索内容，有少量推断
- 4-6: 回答部分基于检索内容，有明显推断
- 1-3: 回答大部分是编造的
- 0: 回答完全不基于检索内容

请只返回JSON格式：{{"score": 0-10, "reason": "简短原因"}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": faith_prompt}],
            temperature=0,
            max_tokens=150,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r'\{[^}]+\}', content)
        if m:
            j = json.loads(m.group())
            results['faithfulness'] = j.get('score', 0) / 10.0
    except Exception as e:
        logger.warning('Faithfulness 评估失败: %s', str(e)[:80])

    # Answer Relevancy: 回答是否切题
    try:
        relevancy_prompt = f"""评估以下回答是否与问题相关。

问题：{question}
AI回答：{answer[:500]}

评分标准（0-10）：
- 10: 回答完全切题，直接解答了问题
- 7-9: 回答基本切题，有少量偏题
- 4-6: 回答部分切题，有明显偏题
- 1-3: 回答大部分偏题
- 0: 回答完全不相关

请只返回JSON格式：{{"score": 0-10, "reason": "简短原因"}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": relevancy_prompt}],
            temperature=0,
            max_tokens=150,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r'\{[^}]+\}', content)
        if m:
            j = json.loads(m.group())
            results['answer_relevancy'] = j.get('score', 0) / 10.0
    except Exception as e:
        logger.warning('Answer Relevancy 评估失败: %s', str(e)[:80])

    # Context Precision: 检索内容是否精准
    try:
        precision_prompt = f"""评估检索到的内容是否精准（是否包含回答问题所需的信息，而非无关信息）。

问题：{question}
检索内容：
{context_text}

评分标准（0-10）：
- 10: 检索内容完全精准，都是回答问题所需的信息
- 7-9: 检索内容大部分精准，有少量无关内容
- 4-6: 检索内容部分精准，有明显无关内容
- 1-3: 检索内容大部分是无关的
- 0: 检索内容完全无关

请只返回JSON格式：{{"score": 0-10, "reason": "简短原因"}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": precision_prompt}],
            temperature=0,
            max_tokens=150,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r'\{[^}]+\}', content)
        if m:
            j = json.loads(m.group())
            results['context_precision'] = j.get('score', 0) / 10.0
    except Exception as e:
        logger.warning('Context Precision 评估失败: %s', str(e)[:80])

    # Context Recall: 相关内容是否都被检索到
    try:
        recall_prompt = f"""评估检索到的内容是否包含了回答问题所需的所有信息。

问题：{question}
标准答案：{ground_truth}
检索内容：
{context_text}

评分标准（0-10）：
- 10: 检索内容包含了标准答案中的所有关键信息
- 7-9: 检索内容包含了大部分关键信息
- 4-6: 检索内容包含了部分关键信息
- 1-3: 检索内容只包含少量关键信息
- 0: 检索内容不包含任何关键信息

请只返回JSON格式：{{"score": 0-10, "reason": "简短原因"}}"""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": recall_prompt}],
            temperature=0,
            max_tokens=150,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r'\{[^}]+\}', content)
        if m:
            j = json.loads(m.group())
            results['context_recall'] = j.get('score', 0) / 10.0
    except Exception as e:
        logger.warning('Context Recall 评估失败: %s', str(e)[:80])

    return results


def eval_rouge(answer: str, ground_truth: str) -> tuple:
    """D. ROUGE 分数评估"""
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=False)
        scores = scorer.score(ground_truth, answer)
        return (
            scores['rouge1'].fmeasure,
            scores['rouge2'].fmeasure,
            scores['rougeL'].fmeasure,
        )
    except Exception as e:
        logger.warning('ROUGE 评估失败: %s', str(e)[:80])
        return 0.0, 0.0, 0.0


def eval_bertscore(answers: List[str], ground_truths: List[str]) -> tuple:
    """E. BERTScore 评估"""
    try:
        from bert_score import score as bert_score
        P, R, F1 = bert_score(answers, ground_truths, lang="zh", verbose=False)
        return (
            P.mean().item(),
            R.mean().item(),
            F1.mean().item(),
        )
    except Exception as e:
        logger.warning('BERTScore 评估失败: %s', str(e)[:80])
        return 0.0, 0.0, 0.0


def eval_retrieval_quality(context_details: List[dict], expected_keywords: List[str]) -> tuple:
    """F. 检索质量指标评估"""
    if not context_details:
        return 0.0, 0.0, 0.0

    relevances = []
    for ctx in context_details:
        content = ctx.get('content', '') if isinstance(ctx, dict) else str(ctx)
        is_relevant = any(kw in content for kw in expected_keywords)
        relevances.append(1 if is_relevant else 0)

    hit_rate = 1.0 if any(r > 0 for r in relevances) else 0.0

    mrr = 0.0
    for i, r in enumerate(relevances):
        if r > 0:
            mrr = 1.0 / (i + 1)
            break

    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_relevances))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    return hit_rate, mrr, ndcg


# ============================================================
# 主评估流程
# ============================================================

def load_test_cases(filepath: str) -> List[TestCase]:
    """加载测试用例"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cases = []
    for item in data:
        cases.append(TestCase(
            id=item['id'],
            question=item['question'],
            ground_truth=item['ground_truth'],
            expected_keywords=item.get('expected_keywords', []),
            expected_sources=item.get('expected_sources', []),
            category=item.get('category', 'general'),
            difficulty=item.get('difficulty', 'medium'),
        ))
    return cases


def init_rag_components():
    """初始化 RAG 组件"""
    print('🔧 初始化 RAG 组件...')

    from scripts.pipeline.chunker import Chunker
    from scripts.pipeline.embedder import Embedder
    from scripts.pipeline.vector_store import VectorStore
    from scripts.pipeline.bm25_retriever import BM25Retriever
    from scripts.pipeline.retriever import Retriever
    from scripts.pipeline.llm_generator import Generator

    data_dir = Path('data')
    md_files = sorted(data_dir.glob('*_refined.md'))

    if not md_files:
        print('❌ 未找到解析后的文档（*_refined.md），请先导入文档')
        sys.exit(1)

    print(f'📄 找到 {len(md_files)} 个文档:')
    for f in md_files:
        print(f'   - {f.name}')

    embedder = Embedder(model_path=os.getenv('EMBEDDING_MODEL_PATH', r'E:\AI_models\BGE-M3'), device='cpu')
    store = VectorStore(
        host=os.getenv('MILVUS_HOST', 'localhost'),
        port=os.getenv('MILVUS_PORT', '19530'),
        collection=os.getenv('MILVUS_COLLECTION', 'rag_workorder7'),
    )

    chunker = Chunker()
    all_children = []
    for md_file in md_files:
        md_text = md_file.read_text(encoding='utf-8')
        parents, children = chunker.chunk(md_text)
        all_children.extend(children)
        print(f'   📝 {md_file.name}: {len(children)} 个分块')

    bm25 = BM25Retriever(all_children)

    reranker = None
    try:
        from scripts.pipeline.reranker import create_reranker
        reranker = create_reranker(
            reranker_type="bge",
            model_path=os.getenv('RERANK_MODEL_PATH', ''),
            device="cpu"
        )
        print('   ✅ Reranker 已加载')
    except Exception as e:
        print(f'   ⚠️ Reranker 不可用: {str(e)[:60]}')

    retriever = Retriever(store, bm25, embedder, reranker)
    generator = Generator()

    print('✅ 组件初始化完成\n')
    return retriever, generator


def run_single_query(retriever, generator, test_case: TestCase, top_k: int = 8) -> QueryResult:
    """执行单次查询"""
    start = time.time()

    search_results = retriever.search(test_case.question, top_k=top_k)

    try:
        answer = generator.generate(test_case.question, search_results, language='zh')
    except Exception as e:
        answer = f'[生成失败: {str(e)[:80]}]'

    elapsed_ms = (time.time() - start) * 1000

    contexts = []
    context_details = []
    for r in search_results:
        content = r.get('content', '')
        contexts.append(content)
        context_details.append({
            'chunk_id': r.get('chunk_id', ''),
            'section_title': r.get('section_title', ''),
            'source_file': r.get('source_file', ''),
            'content': content,
        })

    return QueryResult(
        question=test_case.question,
        answer=answer,
        contexts=contexts,
        context_details=context_details,
        response_time_ms=elapsed_ms,
        ground_truth=test_case.ground_truth,
    )


def run_comprehensive_evaluation():
    """运行全方位评估"""
    print('=' * 60)
    print('  RAG 系统全方位评估')
    print('=' * 60)
    print()

    test_cases = load_test_cases('tests/eval_test_cases.json')
    print(f'📋 加载了 {len(test_cases)} 个测试用例')
    print()

    retriever, generator = init_rag_components()

    from openai import OpenAI
    llm_client = OpenAI(
        api_key=os.getenv('MIMO_API_KEY'),
        base_url=os.getenv('MIMO_BASE_URL'),
    )
    llm_model = os.getenv('MIMO_MODEL', 'deepseek-chat')

    # ─────────────────────────────────────────────
    # 阶段 1：执行所有查询
    # ─────────────────────────────────────────────
    print('─' * 60)
    print('  阶段 1：执行 RAG 查询')
    print('─' * 60)

    query_results: List[QueryResult] = []
    for i, tc in enumerate(test_cases):
        print(f'  [{i+1}/{len(test_cases)}] {tc.question}', end='', flush=True)
        result = run_single_query(retriever, generator, tc)
        query_results.append(result)
        print(f'  ✓ {result.response_time_ms:.0f}ms')

    print()

    # ─────────────────────────────────────────────
    # 阶段 2：运行各评估方法
    # ─────────────────────────────────────────────
    print('─' * 60)
    print('  阶段 2：运行评估方法')
    print('─' * 60)

    all_scores: List[EvalScores] = []

    # 2A. 关键词匹配
    print('  A. 关键词匹配...', end='', flush=True)
    for tc, qr in zip(test_cases, query_results):
        scores = EvalScores()
        hits, total, precision = eval_keyword_matching(qr.answer, tc.expected_keywords)
        scores.keyword_hits = hits
        scores.keyword_total = total
        scores.keyword_precision = precision
        scores.response_time_ms = qr.response_time_ms
        all_scores.append(scores)
    print(' ✓')

    # 2B. LLM-as-Judge
    print('  B. LLM-as-Judge...', end='', flush=True)
    for i, (tc, qr, scores) in enumerate(zip(test_cases, query_results, all_scores)):
        correct, reason = eval_llm_judge(tc.question, tc.ground_truth, qr.answer, llm_client, llm_model)
        scores.llm_correct = correct
        scores.llm_reason = reason
        if (i + 1) % 3 == 0:
            print(f'\r  B. LLM-as-Judge... {i+1}/{len(test_cases)}', end='', flush=True)
    print(' ✓')

    # 2C. RAGAS 风格指标
    print('  C. RAGAS 风格指标...', end='', flush=True)
    for i, (tc, qr, scores) in enumerate(zip(test_cases, query_results, all_scores)):
        ragas_scores = eval_ragas_style(
            tc.question, qr.contexts, qr.answer, tc.ground_truth,
            llm_client, llm_model
        )
        scores.faithfulness = ragas_scores['faithfulness']
        scores.answer_relevancy = ragas_scores['answer_relevancy']
        scores.context_precision = ragas_scores['context_precision']
        scores.context_recall = ragas_scores['context_recall']
        if (i + 1) % 3 == 0:
            print(f'\r  C. RAGAS 风格指标... {i+1}/{len(test_cases)}', end='', flush=True)
    print(' ✓')

    # 2D. ROUGE 分数
    print('  D. ROUGE 分数...', end='', flush=True)
    for tc, qr, scores in zip(test_cases, query_results, all_scores):
        r1, r2, rL = eval_rouge(qr.answer, tc.ground_truth)
        scores.rouge1_f = r1
        scores.rouge2_f = r2
        scores.rougeL_f = rL
    print(' ✓')

    # 2E. BERTScore
    print('  E. BERTScore...', end='', flush=True)
    answers = [qr.answer for qr in query_results]
    ground_truths = [tc.ground_truth for tc in test_cases]
    bert_p, bert_r, bert_f1 = eval_bertscore(answers, ground_truths)
    for scores in all_scores:
        scores.bertscore_p = bert_p
        scores.bertscore_r = bert_r
        scores.bertscore_f1 = bert_f1
    print(' ✓')

    # 2F. 检索质量指标
    print('  F. 检索质量指标...', end='', flush=True)
    for tc, qr, scores in zip(test_cases, query_results, all_scores):
        hit, mrr, ndcg = eval_retrieval_quality(qr.context_details, tc.expected_keywords)
        scores.hit_rate = hit
        scores.mrr = mrr
        scores.ndcg = ndcg
    print(' ✓')

    print()

    # ─────────────────────────────────────────────
    # 阶段 3：汇总评估结果
    # ─────────────────────────────────────────────
    print('─' * 60)
    print('  阶段 3：汇总评估结果')
    print('─' * 60)

    report = EvalReport()
    report.total_questions = len(test_cases)

    report.avg_keyword_precision = sum(s.keyword_precision for s in all_scores) / len(all_scores)

    llm_correct_count = sum(1 for s in all_scores if s.llm_correct is True)
    llm_total = sum(1 for s in all_scores if s.llm_correct is not None)
    report.llm_accuracy = llm_correct_count / max(llm_total, 1)

    report.avg_faithfulness = sum(s.faithfulness for s in all_scores) / len(all_scores)
    report.avg_answer_relevancy = sum(s.answer_relevancy for s in all_scores) / len(all_scores)
    report.avg_context_precision = sum(s.context_precision for s in all_scores) / len(all_scores)
    report.avg_context_recall = sum(s.context_recall for s in all_scores) / len(all_scores)

    report.avg_rouge1 = sum(s.rouge1_f for s in all_scores) / len(all_scores)
    report.avg_rouge2 = sum(s.rouge2_f for s in all_scores) / len(all_scores)
    report.avg_rougeL = sum(s.rougeL_f for s in all_scores) / len(all_scores)

    report.avg_bertscore_f1 = bert_f1

    report.avg_hit_rate = sum(s.hit_rate for s in all_scores) / len(all_scores)
    report.avg_mrr = sum(s.mrr for s in all_scores) / len(all_scores)
    report.avg_ndcg = sum(s.ndcg for s in all_scores) / len(all_scores)

    report.avg_response_time_ms = sum(s.response_time_ms for s in all_scores) / len(all_scores)

    # 逐题详情
    for tc, qr, scores in zip(test_cases, query_results, all_scores):
        report.results.append({
            'id': tc.id,
            'question': tc.question,
            'category': tc.category,
            'difficulty': tc.difficulty,
            'answer': qr.answer[:300],
            'ground_truth': tc.ground_truth,
            'keyword_precision': round(scores.keyword_precision, 3),
            'llm_correct': scores.llm_correct,
            'llm_reason': scores.llm_reason,
            'faithfulness': round(scores.faithfulness, 3),
            'answer_relevancy': round(scores.answer_relevancy, 3),
            'context_precision': round(scores.context_precision, 3),
            'context_recall': round(scores.context_recall, 3),
            'rouge1': round(scores.rouge1_f, 3),
            'rouge2': round(scores.rouge2_f, 3),
            'rougeL': round(scores.rougeL_f, 3),
            'hit_rate': scores.hit_rate,
            'mrr': round(scores.mrr, 3),
            'ndcg': round(scores.ndcg, 3),
            'response_time_ms': round(scores.response_time_ms, 1),
            'sources': [ctx.get('source_file', '') for ctx in qr.context_details],
        })

    return report


def generate_report(report: EvalReport) -> str:
    """生成 Markdown 评估报告"""
    lines = [
        "# RAG 系统全方位评估报告",
        "",
        "## 1. 评估概述",
        "",
        f"- **评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **测试问题数**: {report.total_questions}",
        f"- **评估维度**: 关键词匹配、LLM-as-Judge、RAGAS风格指标、ROUGE、BERTScore、检索质量、性能",
        "",
        "## 2. 评估指标总览",
        "",
        "| 评估维度 | 指标 | 得分 | 目标 | 状态 |",
        "|----------|------|------|------|------|",
        f"| 关键词匹配 | 准确率 | {report.avg_keyword_precision*100:.1f}% | ≥90% | {'✅' if report.avg_keyword_precision >= 0.9 else '❌'} |",
        f"| LLM-as-Judge | 准确率 | {report.llm_accuracy*100:.1f}% | ≥90% | {'✅' if report.llm_accuracy >= 0.9 else '❌'} |",
        f"| RAGAS风格 | Faithfulness | {report.avg_faithfulness:.3f} | ≥0.7 | {'✅' if report.avg_faithfulness >= 0.7 else '❌'} |",
        f"| RAGAS风格 | Answer Relevancy | {report.avg_answer_relevancy:.3f} | ≥0.7 | {'✅' if report.avg_answer_relevancy >= 0.7 else '❌'} |",
        f"| RAGAS风格 | Context Precision | {report.avg_context_precision:.3f} | ≥0.7 | {'✅' if report.avg_context_precision >= 0.7 else '❌'} |",
        f"| RAGAS风格 | Context Recall | {report.avg_context_recall:.3f} | ≥0.7 | {'✅' if report.avg_context_recall >= 0.7 else '❌'} |",
        f"| ROUGE | ROUGE-1 | {report.avg_rouge1:.3f} | ≥0.3 | {'✅' if report.avg_rouge1 >= 0.3 else '❌'} |",
        f"| ROUGE | ROUGE-2 | {report.avg_rouge2:.3f} | ≥0.2 | {'✅' if report.avg_rouge2 >= 0.2 else '❌'} |",
        f"| ROUGE | ROUGE-L | {report.avg_rougeL:.3f} | ≥0.3 | {'✅' if report.avg_rougeL >= 0.3 else '❌'} |",
        f"| BERTScore | F1 | {report.avg_bertscore_f1:.3f} | ≥0.7 | {'✅' if report.avg_bertscore_f1 >= 0.7 else '❌'} |",
        f"| 检索质量 | Hit Rate | {report.avg_hit_rate*100:.1f}% | ≥90% | {'✅' if report.avg_hit_rate >= 0.9 else '❌'} |",
        f"| 检索质量 | MRR | {report.avg_mrr:.3f} | ≥0.5 | {'✅' if report.avg_mrr >= 0.5 else '❌'} |",
        f"| 检索质量 | NDCG | {report.avg_ndcg:.3f} | ≥0.7 | {'✅' if report.avg_ndcg >= 0.7 else '❌'} |",
        f"| 性能 | 响应时间 | {report.avg_response_time_ms:.0f}ms | ≤3000ms | {'✅' if report.avg_response_time_ms <= 3000 else '❌'} |",
        "",
        "## 3. RAGAS 风格评估详情",
        "",
        "RAGAS 是业界公认的 RAG 评估框架。本评估使用 LLM-as-Judge 手动实现了 RAGAS 的四个核心指标：",
        "",
        "| 指标 | 说明 | 本次得分 |",
        "|------|------|----------|",
        f"| **Faithfulness** | 回答是否基于检索到的内容（检测幻觉） | {report.avg_faithfulness:.3f} |",
        f"| **Answer Relevancy** | 回答是否切题 | {report.avg_answer_relevancy:.3f} |",
        f"| **Context Precision** | 检索内容是否精准（排序质量） | {report.avg_context_precision:.3f} |",
        f"| **Context Recall** | 相关内容是否都被检索到 | {report.avg_context_recall:.3f} |",
        "",
        "## 4. 文本相似度评估",
        "",
        "| 指标 | 说明 | 本次得分 |",
        "|------|------|----------|",
        f"| **ROUGE-1** | 单字重叠率 | {report.avg_rouge1:.3f} |",
        f"| **ROUGE-2** | 双字重叠率 | {report.avg_rouge2:.3f} |",
        f"| **ROUGE-L** | 最长公共子序列 | {report.avg_rougeL:.3f} |",
        f"| **BERTScore** | 语义相似度（基于BERT嵌入） | {report.avg_bertscore_f1:.3f} |",
        "",
        "## 5. 检索质量评估",
        "",
        "| 指标 | 说明 | 本次得分 |",
        "|------|------|----------|",
        f"| **Hit Rate** | 检索结果中是否包含相关文档 | {report.avg_hit_rate*100:.1f}% |",
        f"| **MRR** | 第一个相关文档的排名倒数 | {report.avg_mrr:.3f} |",
        f"| **NDCG** | 排序质量（考虑分级相关性） | {report.avg_ndcg:.3f} |",
        "",
        "## 6. 性能评估",
        "",
        f"- **平均响应时间**: {report.avg_response_time_ms:.0f}ms",
        f"- **目标**: ≤3000ms",
        f"- **达标**: {'✅ 是' if report.avg_response_time_ms <= 3000 else '❌ 否'}",
        "",
        "## 7. 逐题评估详情",
        "",
        "| # | 问题 | 关键词命中 | LLM评判 | Faithfulness | ROUGE-L | Hit Rate | 响应时间 |",
        "|---|------|-----------|---------|-------------|---------|----------|----------|",
    ]

    for r in report.results:
        llm_status = '✅' if r['llm_correct'] else ('❌' if r['llm_correct'] is False else '⚠️')
        lines.append(
            f"| {r['id']} | {r['question'][:20]}... | {r['keyword_precision']*100:.0f}% | {llm_status} | {r['faithfulness']:.2f} | {r['rougeL']:.3f} | {'✅' if r['hit_rate'] > 0 else '❌'} | {r['response_time_ms']:.0f}ms |"
        )

    lines.extend([
        "",
        "## 8. 逐题详细结果",
        "",
    ])

    for r in report.results:
        lines.extend([
            f"### 问题 {r['id']}: {r['question']}",
            "",
            f"**类别**: {r['category']} | **难度**: {r['difficulty']}",
            "",
            f"**标准答案**: {r['ground_truth']}",
            "",
            f"**AI回答**: {r['answer'][:200]}...",
            "",
            "**评估结果**:",
            f"- 关键词命中率: {r['keyword_precision']*100:.0f}%",
            f"- LLM评判: {'正确' if r['llm_correct'] else '错误'} ({r['llm_reason']})",
            f"- Faithfulness: {r['faithfulness']:.2f}",
            f"- Answer Relevancy: {r['answer_relevancy']:.2f}",
            f"- Context Precision: {r['context_precision']:.2f}",
            f"- Context Recall: {r['context_recall']:.2f}",
            f"- ROUGE-L: {r['rougeL']:.3f}",
            f"- 检索命中: {'是' if r['hit_rate'] > 0 else '否'}",
            f"- 响应时间: {r['response_time_ms']:.0f}ms",
            "",
        ])

    lines.extend([
        "## 9. 问题分析与改进建议",
        "",
        "### 9.1 检索结果存在的问题",
        "",
    ])

    low_rouge = [r for r in report.results if r['rougeL'] < 0.3]
    llm_wrong = [r for r in report.results if r['llm_correct'] is False]
    slow_queries = [r for r in report.results if r['response_time_ms'] > 3000]
    low_faith = [r for r in report.results if r['faithfulness'] < 0.7]

    if low_rouge:
        lines.append(f"1. **文本相似度偏低**: {len(low_rouge)} 个问题的 ROUGE-L < 0.3，说明回答与标准答案差异较大")
    if llm_wrong:
        lines.append(f"2. **LLM评判错误**: {len(llm_wrong)} 个问题被 LLM 判定为回答错误")
    if slow_queries:
        lines.append(f"3. **响应时间超标**: {len(slow_queries)} 个问题响应时间超过 3 秒")
    if low_faith:
        lines.append(f"4. **忠实度不足**: {len(low_faith)} 个问题的 Faithfulness < 0.7，存在幻觉风险")

    lines.extend([
        "",
        "### 9.2 改进建议",
        "",
        "1. **检索优化**: 调整 RRF 融合权重，优化 BM25 分词策略",
        "2. **Rerank 优化**: 尝试不同的 Reranker 模型，提升排序质量",
        "3. **Prompt 优化**: 调整 LLM System Prompt，提升回答质量和忠实度",
        "4. **分块优化**: 调整分块大小和重叠策略，提升上下文质量",
        "",
        "---",
        "",
        "*报告由 RAG 全方位评估脚本自动生成*",
    ])

    return "\n".join(lines)


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    start_time = time.time()

    report = run_comprehensive_evaluation()
    report_md = generate_report(report)

    report_path = Path('docs/RAG_评估报告.md')
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report_md, encoding='utf-8')

    json_path = Path('docs/evaluation_results_comprehensive.json')
    json_data = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total_questions': report.total_questions,
            'keyword_precision': round(report.avg_keyword_precision, 3),
            'llm_accuracy': round(report.llm_accuracy, 3),
            'faithfulness': round(report.avg_faithfulness, 3),
            'answer_relevancy': round(report.avg_answer_relevancy, 3),
            'context_precision': round(report.avg_context_precision, 3),
            'context_recall': round(report.avg_context_recall, 3),
            'rouge1': round(report.avg_rouge1, 3),
            'rouge2': round(report.avg_rouge2, 3),
            'rougeL': round(report.avg_rougeL, 3),
            'bertscore_f1': round(report.avg_bertscore_f1, 3),
            'hit_rate': round(report.avg_hit_rate, 3),
            'mrr': round(report.avg_mrr, 3),
            'ndcg': round(report.avg_ndcg, 3),
            'avg_response_time_ms': round(report.avg_response_time_ms, 1),
        },
        'details': report.results,
    }
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding='utf-8')

    elapsed = time.time() - start_time

    print()
    print('=' * 60)
    print('  评估完成！')
    print('=' * 60)
    print(f'  总耗时: {elapsed:.1f}s')
    print(f'  测试问题: {report.total_questions}')
    print()
    print('  📊 核心指标:')
    print(f'     关键词命中率:       {report.avg_keyword_precision*100:>5.1f}%')
    print(f'     LLM准确率:          {report.llm_accuracy*100:>5.1f}%')
    print(f'     Faithfulness:       {report.avg_faithfulness:.3f}')
    print(f'     Answer Relevancy:   {report.avg_answer_relevancy:.3f}')
    print(f'     Context Precision:  {report.avg_context_precision:.3f}')
    print(f'     Context Recall:     {report.avg_context_recall:.3f}')
    print(f'     ROUGE-L:            {report.avg_rougeL:.3f}')
    print(f'     BERTScore F1:       {report.avg_bertscore_f1:.3f}')
    print(f'     Hit Rate:           {report.avg_hit_rate*100:.1f}%')
    print(f'     MRR:                {report.avg_mrr:.3f}')
    print(f'     平均响应时间:       {report.avg_response_time_ms:.0f}ms')
    print()
    print(f'  📄 报告已保存至: {report_path}')
    print(f'  📄 JSON结果: {json_path}')
    print()
