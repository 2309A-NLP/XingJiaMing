"""运行 RAG 评估测试

使用年报测试用例评估系统性能
"""
import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置 WSL 路径（必须在导入项目模块之前）
os.environ['EMBEDDING_MODEL_PATH'] = '/mnt/e/AI_models/BGE-M3'
os.environ['RERANK_MODEL_PATH'] = '/mnt/e/AI_models/bge-reranker-base'

from scripts.pipeline.rag_evaluator import RAGEvaluator, TestCase


def load_test_cases(file_path: str) -> list:
    """从 JSON 文件加载测试用例"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cases = []
    for item in data:
        cases.append(TestCase(
            question=item['question'],
            expected_keywords=item.get('expected_keywords', []),
            expected_sources=item.get('expected_sources', []),
            category=item.get('category', 'general'),
        ))
    return cases


def main():
    """主函数"""
    print("=" * 60)
    print("  RAG 年报数据集评估测试")
    print("=" * 60)
    print()

    # 加载测试用例
    test_cases_file = project_root / "tests" / "annual_report_test_cases.json"
    if not test_cases_file.exists():
        print(f"错误: 测试用例文件不存在: {test_cases_file}")
        return

    test_cases = load_test_cases(test_cases_file)
    print(f"加载了 {len(test_cases)} 个测试用例")
    print()

    # 初始化组件
    print("正在初始化 RAG 组件...")
    from api.init import get_components
    comp = get_components()
    print("组件初始化完成")
    print()

    # 构造查询函数
    def query_fn(question: str, top_k: int, language: str):
        from api.routes.query import _search, _build_context_from_results
        from api.models import QueryRequest

        start = time.time()
        mock_req = QueryRequest(
            question=question,
            top_k=top_k,
            language=language,
            search_mode='hybrid'
        )
        results = _search(comp, mock_req)
        contexts = _build_context_from_results(results)
        answer = comp['generator'].generate(question, contexts, language)
        elapsed = (time.time() - start) * 1000

        sources = [{
            'chunk_id': r['chunk_id'],
            'section_title': r.get('section_title', ''),
            'source_file': r.get('source_file', ''),
            'content': r['content'][:200],
        } for r in results]

        return answer, sources, elapsed

    # 运行评估
    print("开始评估测试...")
    print("-" * 60)

    evaluator = RAGEvaluator(test_cases=test_cases)
    report = evaluator.evaluate(query_fn, top_k=5, language='zh')

    # 输出结果
    print()
    print(report.summary())

    # 输出详细结果
    print()
    print("=" * 60)
    print("  详细结果")
    print("=" * 60)
    for i, result in enumerate(report.results, 1):
        print(f"\n问题 {i}: {result.question}")
        print(f"  回答: {result.answer[:100]}...")
        print(f"  准确率: {result.precision*100:.1f}% ({result.keyword_hits}/{result.keyword_total} 关键词命中)")
        print(f"  召回率: {result.recall*100:.1f}%")
        print(f"  响应时间: {result.response_time_ms:.0f}ms")

    # 保存报告
    report_file = project_root / "docs" / "evaluation_report_annual.json"
    report_data = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_cases_count": report.total_questions,
        "metrics": {
            "avg_precision": round(report.avg_precision, 3),
            "avg_recall": round(report.avg_recall, 3),
            "avg_response_time_ms": round(report.avg_response_time_ms, 1),
            "precision_at_90": round(report.precision_at_90, 3),
            "recall_at_95": round(report.recall_at_95, 3),
            "response_time_under_3s": round(report.response_time_under_3s, 3),
        },
        "category_scores": report.category_scores,
        "details": [
            {
                "question": r.question,
                "answer": r.answer[:200],
                "precision": round(r.precision, 3),
                "recall": round(r.recall, 3),
                "response_time_ms": round(r.response_time_ms, 1),
                "keyword_hits": r.keyword_hits,
                "keyword_total": r.keyword_total,
            }
            for r in report.results
        ]
    }

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print()
    print(f"评估报告已保存到: {report_file}")


if __name__ == "__main__":
    main()
