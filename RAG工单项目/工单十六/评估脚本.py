#!/usr/bin/env python3
"""
工单十六：VLM微调效果评估脚本
对比微调前后模型在图文问答任务上的表现
"""

import json
import time
import os
import sys
from typing import List, Dict
import argparse

from llamafactory.chat import ChatModel


def load_test_data(questions_path: str, 图片目录: str) -> List[Dict]:
    """加载测试数据"""
    test_cases = []
    with open(questions_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                doc_name = data['document'].replace('.pdf', '')
                image_files = [f for f in os.listdir(图片目录) 
                             if f.startswith(doc_name) and f.endswith('.png')]
                
                if image_files:
                    image_files.sort()
                    image_path = os.path.join(图片目录, image_files[0])
                else:
                    image_path = None
                
                test_cases.append({
                    'id': line_num,
                    'question': data['question'],
                    'options': data['options'],
                    'answer': data['answer'],
                    'group': data['group'],
                    'document': data['document'],
                    'image_path': image_path,
                    'has_image': data['group'] == 2
                })
            except json.JSONDecodeError as e:
                print(f"警告：第{line_num}行JSON解析失败: {e}")
                continue
    return test_cases


def build_prompt(test_case: Dict) -> str:
    """构建提示词"""
    options_text = '\n'.join(test_case['options'])
    prompt = f"""请仔细阅读以下问题并选择正确答案。

问题：{test_case['question']}

选项：
{options_text}

请直接输出正确答案的字母（A/B/C/D）。"""
    return prompt


def extract_answer(response: str) -> str:
    """从模型响应中提取答案字母"""
    response = response.strip().upper()
    
    if len(response) == 1 and response in 'ABCD':
        return response
    
    for letter in 'ABCD':
        if response.startswith(letter) or f'{letter}.' in response or f'{letter}、' in response:
            return letter
    
    patterns = ['答案是', '正确答案是', '选择', '答案：', '正确答案：']
    for pattern in patterns:
        if pattern in response:
            idx = response.find(pattern) + len(pattern)
            remaining = response[idx:].strip()
            if remaining and remaining[0].upper() in 'ABCD':
                return remaining[0].upper()
    
    for char in response:
        if char.upper() in 'ABCD':
            return char.upper()
    
    return ''


def extract_response_text(response) -> str:
    """从chat_model.chat()返回值中提取文本"""
    # 返回值是 [Response(response_text="...")] 格式
    if isinstance(response, list) and len(response) > 0:
        resp = response[0]
        if hasattr(resp, 'response_text'):
            return resp.response_text
        elif isinstance(resp, str):
            return resp
    elif isinstance(response, str):
        return response
    return str(response)


def evaluate_model(config_args: List[str], test_cases: List[Dict], model_name: str) -> Dict:
    """评估单个模型"""
    print(f"\n{'='*60}")
    print(f"评估模型: {model_name}")
    print(f"{'='*60}")
    
    try:
        chat_model = ChatModel(config_args)
    except Exception as e:
        print(f"模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    results = []
    total_time = 0
    correct_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] 测试问题 {test_case['id']}:")
        print(f"  文档: {test_case['document']}")
        print(f"  类型: {'图文' if test_case['has_image'] else '纯文本'}")
        print(f"  正确答案: {test_case['answer']}")
        
        prompt = build_prompt(test_case)
        messages = [{'role': 'user', 'content': prompt}]
        
        images = []
        if test_case['has_image'] and test_case['image_path']:
            images.append(test_case['image_path'])
        
        start_time = time.time()
        try:
            response = chat_model.chat(messages, images=images if images else None)
            response_text = extract_response_text(response)
        except Exception as e:
            print(f"  模型调用失败: {e}")
            response_text = ''
        end_time = time.time()
        
        response_time = end_time - start_time
        total_time += response_time
        
        predicted = extract_answer(response_text)
        is_correct = predicted == test_case['answer']
        if is_correct:
            correct_count += 1
        
        print(f"  模型回答: {response_text[:100]}...")
        print(f"  提取答案: {predicted}")
        print(f"  是否正确: {'✓' if is_correct else '✗'}")
        print(f"  响应时间: {response_time:.2f}s")
        
        results.append({
            'id': test_case['id'],
            'question': test_case['question'][:50] + '...',
            'document': test_case['document'],
            'type': '图文' if test_case['has_image'] else '纯文本',
            'correct_answer': test_case['answer'],
            'predicted_answer': predicted,
            'is_correct': is_correct,
            'response_time': response_time,
            'raw_response': response_text[:200]
        })
    
    accuracy = correct_count / len(test_cases) * 100
    avg_time = total_time / len(test_cases)
    
    image_cases = [r for r in results if r['type'] == '图文']
    text_cases = [r for r in results if r['type'] == '纯文本']
    
    image_accuracy = sum(1 for r in image_cases if r['is_correct']) / len(image_cases) * 100 if image_cases else 0
    text_accuracy = sum(1 for r in text_cases if r['is_correct']) / len(text_cases) * 100 if text_cases else 0
    
    summary = {
        'model_name': model_name,
        'total_questions': len(test_cases),
        'correct_count': correct_count,
        'accuracy': accuracy,
        'image_accuracy': image_accuracy,
        'text_accuracy': text_accuracy,
        'avg_response_time': avg_time,
        'total_time': total_time,
        'results': results
    }
    
    print(f"\n{'='*60}")
    print(f"{model_name} 评估结果:")
    print(f"  总体准确率: {accuracy:.1f}% ({correct_count}/{len(test_cases)})")
    print(f"  图文准确率: {image_accuracy:.1f}%")
    print(f"  文本准确率: {text_accuracy:.1f}%")
    print(f"  平均响应时间: {avg_time:.2f}s")
    print(f"{'='*60}")
    
    return summary


def generate_report(baseline_summary: Dict, finetuned_summary: Dict, output_path: str):
    """生成对比报告"""
    report = []
    report.append("# 工单十六：VLM微调效果评估报告\n")
    report.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    report.append("## 1. 评估概述\n")
    report.append("| 指标 | 基线模型 | 微调模型 | 提升 |")
    report.append("|------|----------|----------|------|")
    
    acc_diff = finetuned_summary['accuracy'] - baseline_summary['accuracy']
    acc_sign = '+' if acc_diff > 0 else ''
    report.append(f"| 总体准确率 | {baseline_summary['accuracy']:.1f}% | {finetuned_summary['accuracy']:.1f}% | {acc_sign}{acc_diff:.1f}% |")
    
    img_diff = finetuned_summary['image_accuracy'] - baseline_summary['image_accuracy']
    img_sign = '+' if img_diff > 0 else ''
    report.append(f"| 图文准确率 | {baseline_summary['image_accuracy']:.1f}% | {finetuned_summary['image_accuracy']:.1f}% | {img_sign}{img_diff:.1f}% |")
    
    txt_diff = finetuned_summary['text_accuracy'] - baseline_summary['text_accuracy']
    txt_sign = '+' if txt_diff > 0 else ''
    report.append(f"| 文本准确率 | {baseline_summary['text_accuracy']:.1f}% | {finetuned_summary['text_accuracy']:.1f}% | {txt_sign}{txt_diff:.1f}% |")
    
    time_diff = finetuned_summary['avg_response_time'] - baseline_summary['avg_response_time']
    time_sign = '+' if time_diff > 0 else ''
    report.append(f"| 平均响应时间 | {baseline_summary['avg_response_time']:.2f}s | {finetuned_summary['avg_response_time']:.2f}s | {time_sign}{time_diff:.2f}s |")
    
    report.append("\n## 2. 详细对比\n")
    report.append("| 问题ID | 类型 | 正确答案 | 基线模型 | 微调模型 | 结果 |")
    report.append("|--------|------|----------|----------|----------|------|")
    
    for base_result, ft_result in zip(baseline_summary['results'], finetuned_summary['results']):
        base_pred = base_result['predicted_answer']
        ft_pred = ft_result['predicted_answer']
        correct = base_result['correct_answer']
        
        if ft_pred == correct and base_pred != correct:
            status = "✅ 改进"
        elif ft_pred != correct and base_pred == correct:
            status = "❌ 退步"
        elif ft_pred == correct and base_pred == correct:
            status = "✅ 都对"
        else:
            status = "❌ 都错"
        
        report.append(f"| {base_result['id']} | {base_result['type']} | {correct} | {base_pred} | {ft_pred} | {status} |")
    
    report.append("\n## 3. 分析与结论\n")
    
    improved = sum(1 for b, f in zip(baseline_summary['results'], finetuned_summary['results']) 
                   if f['is_correct'] and not b['is_correct'])
    degraded = sum(1 for b, f in zip(baseline_summary['results'], finetuned_summary['results']) 
                   if not f['is_correct'] and b['is_correct'])
    
    report.append("### 改进统计\n")
    report.append(f"- 改进题目数: {improved}")
    report.append(f"- 退步题目数: {degraded}")
    report.append(f"- 净改进: {improved - degraded}\n")
    
    report.append("### 关键发现\n")
    
    if finetuned_summary['accuracy'] > baseline_summary['accuracy']:
        report.append("1. 微调后模型整体准确率提升，表明微调有效。\n")
    elif finetuned_summary['accuracy'] < baseline_summary['accuracy']:
        report.append("1. 微调后模型整体准确率下降，可能需要调整微调参数或数据。\n")
    else:
        report.append("1. 微调前后准确率相同。\n")
    
    if finetuned_summary['image_accuracy'] > baseline_summary['image_accuracy']:
        report.append("2. 图文理解能力提升，视觉特征提取效果改善。\n")
    
    if finetuned_summary['text_accuracy'] > baseline_summary['text_accuracy']:
        report.append("3. 纯文本理解能力也有提升，说明微调未损害文本能力。\n")
    
    report.append("\n## 4. 建议\n")
    
    if finetuned_summary['accuracy'] > baseline_summary['accuracy']:
        report.append("- 微调效果良好，可以考虑部署到生产环境。\n")
        report.append("- 建议增加训练数据量，进一步提升效果。\n")
    else:
        report.append("- 建议调整LoRA参数（rank、alpha）。\n")
        report.append("- 检查训练数据质量，确保标注准确。\n")
        report.append("- 考虑增加训练轮数或调整学习率。\n")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"\n报告已保存到: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='VLM微调效果评估')
    parser.add_argument('--questions', required=True, help='测试问题文件路径')
    parser.add_argument('--图片目录', required=True, help='图片目录路径')
    parser.add_argument('--output_dir', default='.', help='报告输出目录')
    
    args = parser.parse_args()
    
    print("加载测试数据...")
    test_cases = load_test_data(args.questions, args.图片目录)
    print(f"加载了 {len(test_cases)} 个测试问题")
    
    # 基线模型参数
    baseline_args = [
        '--model_name_or_path', '/root/autodl-tmp/Qwen2-VL-7B-Instruct',
        '--trust_remote_code', 'true',
        '--template', 'qwen2_vl',
    ]
    
    # 微调模型参数
    finetuned_args = [
        '--model_name_or_path', '/root/autodl-tmp/Qwen2-VL-7B-Instruct',
        '--adapter_name_or_path', '/root/autodl-tmp/工单十六/output',
        '--trust_remote_code', 'true',
        '--template', 'qwen2_vl',
    ]
    
    # 评估基线模型
    baseline_summary = evaluate_model(baseline_args, test_cases, "基线模型 (Qwen2-VL-7B-Instruct)")
    if not baseline_summary:
        print("基线模型评估失败，退出")
        return
    
    # 评估微调模型
    finetuned_summary = evaluate_model(finetuned_args, test_cases, "微调模型 (LoRA)")
    if not finetuned_summary:
        print("微调模型评估失败，退出")
        return
    
    # 生成报告
    report_path = os.path.join(args.output_dir, 'vlm_finetune_evaluation_report.md')
    generate_report(baseline_summary, finetuned_summary, report_path)
    
    # 保存详细结果
    results_path = os.path.join(args.output_dir, 'evaluation_results.json')
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump({
            'baseline': baseline_summary,
            'finetuned': finetuned_summary
        }, f, ensure_ascii=False, indent=2)
    print(f"详细结果已保存到: {results_path}")


if __name__ == '__main__':
    main()
