"""
02_generate.py — 用 LLM 生成问答对
从文档段落中采样，调用 mimo-v2.5-pro 生成用户可能问的问题

用法: conda run -n emb python scripts/02_generate.py
"""

import json
import random
import time
import os
import requests
from pathlib import Path
from collections import defaultdict

# ============ 配置 ============
# mimo API 直连（不走 proxy，proxy 只支持 Responses API 格式）
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com")
LLM_URL = f"{MIMO_BASE_URL}/v1/chat/completions"
LLM_MODEL = "mimo-v2.5-pro"

# 自动加载 .env
def _load_env():
    global MIMO_API_KEY
    env_file = Path.home() / "mimo_proxy" / ".env"
    if env_file.exists() and not MIMO_API_KEY:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                k, _, v = line.partition('=')
                if k.strip() == 'MIMO_API_KEY':
                    MIMO_API_KEY = v.strip().strip('"\'')
_load_env()
CHUNKS_FILE = Path(__file__).parent.parent / "data" / "chunks.jsonl"
RAW_PAIRS_FILE = Path(__file__).parent.parent / "data" / "raw_pairs.jsonl"  # 增量保存的中间文件
TRAIN_FILE = Path(__file__).parent.parent / "data" / "train.jsonl"
TEST_FILE = Path(__file__).parent.parent / "data" / "test.jsonl"

SAMPLE_SIZE = 400        # 采样段落数
QUESTIONS_PER_CHUNK = 3  # 每段生成几个问题
MAX_RETRIES = 3          # LLM 调用失败重试次数
TEMPERATURE = 0.8        # 生成多样性

# 测试集用的文档（最后2个）
TEST_DOCS = [
    "2022-03-28",  # 招商证券
    "2022-03-31",  # 国泰君安
]

# ============ Prompt ============
QUESTION_PROMPT = """你是一个金融领域的普通用户，正在使用一个金融问答系统。
请根据以下金融文档段落，生成{num}个用户可能会问的问题。

要求：
1. 问题要口语化，像真人在问（不要照抄文档原话）
2. 问题要多样化：有的直接问，有的换个角度问，有的问细节
3. 问题必须能从这个段落中找到答案
4. 不要生成和段落内容无关的问题

文档段落：
\"\"\"
{chunk_text}
\"\"\"

请直接输出问题列表，每行一个，不要编号，不要其他内容：
"""


def load_chunks() -> list[dict]:
    """加载所有段落"""
    chunks = []
    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            chunks.append(json.loads(line.strip()))
    return chunks


def sample_chunks(chunks: list[dict], n: int) -> list[dict]:
    """采样段落，确保每个文档都有代表"""
    # 按文档分组
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c['source']].append(c)

    sampled = []
    docs = list(by_doc.keys())
    per_doc = max(n // len(docs), 5)

    for doc in docs:
        doc_chunks = by_doc[doc]
        # 过滤掉太短或包含表格/列表的段落
        good_chunks = [
            c for c in doc_chunks
            if c['char_count'] >= 100
            and not _is_table_or_list(c['text'])
        ]
        if len(good_chunks) >= per_doc:
            sampled.extend(random.sample(good_chunks, per_doc))
        else:
            sampled.extend(good_chunks)

    # 如果不够，从剩余的补
    if len(sampled) < n:
        remaining = [c for c in chunks if c not in sampled and c['char_count'] >= 100]
        extra = random.sample(remaining, min(n - len(sampled), len(remaining)))
        sampled.extend(extra)

    random.shuffle(sampled)
    return sampled[:n]


def _is_table_or_list(text: str) -> bool:
    """判断是否是表格或列表数据（不适合生成问题）"""
    lines = text.strip().split('\n')
    if len(lines) < 3:
        return False
    # 超过一半的行是表格格式
    table_lines = sum(1 for l in lines if l.startswith('|') or l.startswith('-') or l.strip().startswith('['))
    return table_lines / len(lines) > 0.5


def call_llm(prompt: str) -> str:
    """调用 LLM 生成回答"""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                LLM_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {MIMO_API_KEY}",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": TEMPERATURE,
                    "max_tokens": 2000,
                },
                timeout=120,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            # mimo 是推理模型，最终回答在 content，推理过程在 reasoning_content
            return msg.get("content", "") or msg.get("reasoning_content", "")
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"    LLM调用失败，重试 ({attempt+1}/{MAX_RETRIES}): {e}")
                time.sleep(3)
            else:
                print(f"    LLM调用最终失败: {e}")
                return ""


def parse_questions(response: str) -> list[str]:
    """从 LLM 回答中提取问题列表"""
    questions = []
    for line in response.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # 去掉编号（1. 2. 3. 或 - 等）
        line = line.lstrip('0123456789.-)） ')
        # 去掉引号
        line = line.strip('"\'""''')
        # 基本过滤：必须是问句或包含关键词
        if len(line) >= 5 and ('?' in line or '？' in line or
                                any(kw in line for kw in ['什么', '怎么', '如何', '为什么', '哪些', '多少', '是否', '能否', '可以'])):
            questions.append(line)
    return questions


def generate_questions(chunks: list[dict], output_file: Path) -> list[dict]:
    """为每个采样段落生成问题，边生成边保存"""
    results = []
    total = len(chunks)

    # 增量保存：每处理一个chunk就追加写入
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, chunk in enumerate(chunks):
            elapsed = (i) * 15  # 估算已用时间
            remaining = (total - i) * 15
            print(f"\r  生成中: {i+1}/{total} ({(i+1)/total*100:.0f}%) 预计剩余{remaining//60}分钟", end="", flush=True)

            prompt = QUESTION_PROMPT.format(
                num=QUESTIONS_PER_CHUNK,
                chunk_text=chunk['text'][:800],
            )

            response = call_llm(prompt)
            if not response:
                continue

            questions = parse_questions(response)
            for q in questions:
                record = {
                    "question": q,
                    "positive_id": chunk['chunk_id'],
                    "positive_text": chunk['text'],
                    "source": chunk['source'],
                }
                results.append(record)
                # 立即写入文件
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()

    print()  # 换行
    return results


def split_and_save(all_pairs: list[dict], chunks_map: dict):
    """按文档拆分训练集和测试集"""
    train_pairs = []
    test_pairs = []

    for pair in all_pairs:
        # 判断来源文档是否是测试文档
        is_test = any(d in pair['source'] for d in TEST_DOCS)
        if is_test:
            test_pairs.append(pair)
        else:
            train_pairs.append(pair)

    # 保存训练集（triplet格式，负例占位，后续03脚本填充）
    with open(TRAIN_FILE, 'w', encoding='utf-8') as f:
        for p in train_pairs:
            record = {
                "anchor": p['question'],
                "positive": p['positive_text'],
                "positive_id": p['positive_id'],
                "source": p['source'],
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    # 保存测试集（query + relevant_id 格式）
    # 先按问题分组，一个问题可能对应多个段落
    test_by_question = defaultdict(lambda: {"relevant_ids": [], "source": ""})
    for p in test_pairs:
        key = p['question']
        test_by_question[key]['relevant_ids'].append(p['positive_id'])
        test_by_question[key]['source'] = p['source']

    with open(TEST_FILE, 'w', encoding='utf-8') as f:
        for q, info in test_by_question.items():
            record = {
                "query": q,
                "relevant_ids": list(set(info['relevant_ids'])),
                "source": info['source'],
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    return len(train_pairs), len(test_pairs)


def main():
    print("=" * 50)
    print("LLM 问答对生成脚本")
    print("=" * 50)

    # 加载段落
    chunks = load_chunks()
    print(f"\n总段落数: {len(chunks)}")

    # 采样
    sampled = sample_chunks(chunks, SAMPLE_SIZE)
    print(f"采样段落数: {len(sampled)}")

    # 统计每个文档的采样数
    by_doc = defaultdict(int)
    for c in sampled:
        by_doc[c['source']] += 1
    print(f"覆盖文档数: {len(by_doc)}")
    for doc, count in sorted(by_doc.items()):
        print(f"  {doc[:30]}...: {count} 段")

    # 测试 LLM 连接
    print(f"\n测试 LLM 连接 ({LLM_URL})...")
    test_resp = call_llm("你好，请回复'连接成功'")
    if not test_resp:
        print("❌ LLM 连接失败，请检查 mimo proxy 是否运行")
        return
    print(f"✅ LLM 连接正常: {test_resp[:30]}")

    # 生成问题（增量保存到 raw_pairs.jsonl）
    print(f"\n开始生成问题（每段{QUESTIONS_PER_CHUNK}个）...")
    print(f"中间结果实时保存到: {RAW_PAIRS_FILE}")
    all_pairs = generate_questions(sampled, RAW_PAIRS_FILE)
    print(f"\n生成问答对总数: {len(all_pairs)}")

    # 按文档拆分并保存
    chunks_map = {c['chunk_id']: c for c in chunks}
    train_count, test_count = split_and_save(all_pairs, chunks_map)

    # 输出统计
    print(f"\n{'=' * 50}")
    print(f"训练集: {train_count} 条 → {TRAIN_FILE}")
    print(f"测试集: {test_count} 条 → {TEST_FILE}")

    # 展示样例
    print(f"\n--- 训练集样例 ---")
    with open(TRAIN_FILE, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= 2:
                break
            r = json.loads(line)
            print(f"  问题: {r['anchor']}")
            print(f"  正例: {r['positive'][:80]}...")
            print()

    print(f"\n--- 测试集样例 ---")
    with open(TEST_FILE, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= 2:
                break
            r = json.loads(line)
            print(f"  查询: {r['query']}")
            print(f"  相关段落ID: {r['relevant_ids'][:3]}")
            print()


if __name__ == "__main__":
    main()
