#!/usr/bin/env python3
"""
VLM微调数据转换脚本
将IMDR数据集转换为VLM微调格式（JSONL）
格式：{image, question, answer}
"""

import json
import os
import re

# 配置路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "questions.jsonl")
OUTPUT_FILE = os.path.join(BASE_DIR, "vlm_finetune_data.jsonl")
IMAGE_DIR = os.path.join(BASE_DIR, "images")

# 页面图片映射（根据题目中提到的页码）
PAGE_IMAGE_MAP = {
    "CN100342976C": {
        7: "CN100342976C_p7_img1.png"
    },
    "CN100347506C": {
        11: "CN100347506C_p11_img1.png"
    },
    "CN100364694C": {
        18: "CN100364694C_p18_img1.png"
    },
    "CN100391686C": {
        7: "CN100391686C_p7_img1.png"
    },
    "CN100398667C": {
        22: "CN100398667C_p22_img1.png"
    },
    "CN100408139C": {
        7: "CN100408139C_p7_img1.png"
    },
    "CN100408987C": {
        10: "CN100408987C_p10_img1.png"
    }
}


def extract_page_from_question(question: str) -> int:
    """从问题中提取页码"""
    match = re.search(r'第(\d+)页', question)
    if match:
        return int(match.group(1))
    return None


def get_answer_text(options: list, answer_letter: str) -> str:
    """将答案字母转换为完整答案文本"""
    answer_idx = ord(answer_letter.upper()) - ord('A')
    if 0 <= answer_idx < len(options):
        answer_text = options[answer_idx]
        answer_text = re.sub(r'^[A-D][\.\、\s]+', '', answer_text)
        return answer_text
    return answer_letter


def convert_question_to_prompt(question: str, options: list) -> str:
    """将问题和选项转换为提示文本"""
    prompt = f"请仔细阅读以下问题并选择正确答案。\n\n问题：{question}\n\n选项：\n"
    for opt in options:
        prompt += f"{opt}\n"
    prompt += "\n请直接输出正确答案的字母（A/B/C/D）。"
    return prompt


def convert_data():
    """主转换函数"""
    print("=== 开始转换VLM微调数据 ===\n")
    
    # 读取原始数据
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        questions = [json.loads(line.strip()) for line in f]
    
    vlm_data = []
    
    for i, q in enumerate(questions, 1):
        doc_name = q['document'].replace('.pdf', '')
        group = q.get('group', 1)
        question = q['question']
        options = q.get('options', [])
        answer_letter = q['answer']
        
        # 获取答案文本
        answer_text = get_answer_text(options, answer_letter)
        
        # 构建提示
        prompt = convert_question_to_prompt(question, options)
        
        # 获取图片路径
        image_path = None
        if group in [2, 3]:  # 图文题
            page_num = extract_page_from_question(question)
            if page_num and doc_name in PAGE_IMAGE_MAP:
                if page_num in PAGE_IMAGE_MAP[doc_name]:
                    img_name = PAGE_IMAGE_MAP[doc_name][page_num]
                    img_path = os.path.join(IMAGE_DIR, img_name)
                    if os.path.exists(img_path):
                        image_path = f"图片/{img_name}"
        
        # 构建VLM数据
        vlm_item = {
            "image": image_path,
            "conversations": [
                {
                    "from": "human",
                    "value": prompt
                },
                {
                    "from": "gpt",
                    "value": answer_text
                }
            ]
        }
        
        vlm_data.append(vlm_item)
        
        # 输出进度
        img_status = "✓ 有图" if image_path else "✗ 纯文本"
        print(f"【{i}】Group {group} | {img_status} | {doc_name}")
        print(f"   问题: {question[:40]}...")
        print(f"   答案: {answer_text}")
        print()
    
    # 保存VLM数据
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for item in vlm_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"=== 转换完成 ===")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"共 {len(vlm_data)} 条数据")
    print(f"  - 纯文本: {sum(1 for d in vlm_data if not d['image'])} 条")
    print(f"  - 图文混合: {sum(1 for d in vlm_data if d['image'])} 条")


if __name__ == "__main__":
    convert_data()
