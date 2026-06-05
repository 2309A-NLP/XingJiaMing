"""RAGAS 评估脚本

使用 RAGAS 框架评估 RAG 系统质量
指标：忠实度、答案相关性、上下文精确度、上下文召回率
"""
import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置 WSL 路径
os.environ['EMBEDDING_MODEL_PATH'] = '/mnt/e/AI_models/BGE-M3'
os.environ['RERANK_MODEL_PATH'] = '/mnt/e/AI_models/bge-reranker-base'


def load_test_cases(file_path: str) -> list:
    """从 JSON 文件加载测试用例"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def run_ragas_evaluation():
    """运行 RAGAS 评估"""
    print("=" * 60)
    print("  RAGAS 评估")
    print("=" * 60)
    print()

    # 检查 RAGAS 是否可用
    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
        from datasets import Dataset
        print("✓ RAGAS 模块加载成功")
    except ImportError as e:
        print(f"✗ RAGAS 模块加载失败: {e}")
        print("请在 Windows 环境中运行此脚本")
        return

    # 加载测试用例
    test_cases_file = project_root / "tests" / "annual_report_test_cases.json"
    test_cases = load_test_cases(test_cases_file)
    print(f"✓ 加载了 {len(test_cases)} 个测试用例")

    # 初始化组件
    print("正在初始化 RAG 组件...")
    from api.init import get_components
    comp = get_components()
    print("✓ 组件初始化完成")

    # 准备 RAGAS 评估数据
    print("\n正在运行查询...")
    questions = []
    answers = []
    contexts_list = []
    ground_truths = []

    for i, case in enumerate(test_cases, 1):
        question = case['question']
        print(f"  [{i}/{len(test_cases)}] {question[:30]}...")

        # 运行查询
        from api.routes.query import _search, _build_context_from_results
        from api.models import QueryRequest

        mock_req = QueryRequest(
            question=question,
            top_k=5,
            language='zh',
            search_mode='hybrid'
        )
        results = _search(comp, mock_req)
        contexts = _build_context_from_results(results)
        answer = comp['generator'].generate(question, contexts, 'zh')

        # 提取上下文文本
        context_texts = []
        for r in results:
            if isinstance(r, dict):
                context_texts.append(r.get('content', ''))
            else:
                context_texts.append(str(r))

        questions.append(question)
        answers.append(answer)
        contexts_list.append(context_texts)
        # RAGAS 需要 ground_truths，但我们没有，用空列表
        ground_truths.append([""])

    print(f"\n✓ 完成 {len(questions)} 个查询")

    # 创建 RAGAS 数据集
    print("\n正在创建 RAGAS 数据集...")
    data = {
        'question': questions,
        'answer': answers,
        'contexts': contexts_list,
        'ground_truth': ground_truths,
    }
    dataset = Dataset.from_dict(data)

    # 运行 RAGAS 评估
    print("正在运行 RAGAS 评估...")
    try:
        result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
        )

        print("\n" + "=" * 60)
        print("  RAGAS 评估结果")
        print("=" * 60)
        print(f"\n忠实度 (Faithfulness): {result['faithfulness']:.3f}")
        print(f"答案相关性 (Answer Relevancy): {result['answer_relevancy']:.3f}")
        print(f"上下文精确度 (Context Precision): {result['context_precision']:.3f}")
        print(f"上下文召回率 (Context Recall): {result['context_recall']:.3f}")

        # 保存结果
        report_file = project_root / "docs" / "ragas_evaluation_report.json"
        report_data = {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": {
                "faithfulness": round(result['faithfulness'], 3),
                "answer_relevancy": round(result['answer_relevancy'], 3),
                "context_precision": round(result['context_precision'], 3),
                "context_recall": round(result['context_recall'], 3),
            },
            "questions_count": len(questions),
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 评估报告已保存到: {report_file}")

    except Exception as e:
        print(f"\n✗ RAGAS 评估失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_ragas_evaluation()
