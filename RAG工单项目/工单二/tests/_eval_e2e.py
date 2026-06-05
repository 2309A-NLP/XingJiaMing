"""完整检索准确率评估（18题）"""
import sys, os, time
from pathlib import Path

_project_root = Path('.').resolve()
_workorder1 = _project_root.parent.parent / '招股说明智能助手' / '.venv' / 'Lib' / 'site-packages'
if _workorder1.exists():
    sys.path.insert(0, str(_workorder1))
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv(override=True)

from scripts.pipeline.chunker import Chunker
from scripts.pipeline.embedder import Embedder
from scripts.pipeline.vector_store import VectorStore
from scripts.pipeline.bm25_retriever import BM25Retriever
from scripts.pipeline.retriever import Retriever
from scripts.pipeline.generator import Generator
from openai import OpenAI

TEST_CASES = [
    {"q": "公司公开发行多少万股？", "ref": "1,840万股", "kw": ["1,840", "1840"], "type": "事实型"},
    {"q": "发行后总股本是多少？", "ref": "7,360万股", "kw": ["7,360", "7360"], "type": "事实型"},
    {"q": "保荐人是哪家公司？", "ref": "中泰证券", "kw": ["中泰证券"], "type": "事实型"},
    {"q": "公司注册地址在哪里？", "ref": "湖北省武汉市东湖新技术开发区", "kw": ["武汉", "东湖"], "type": "事实型"},
    {"q": "预计发行日期是哪天？", "ref": "2019年12月24日", "kw": ["2019", "12月24"], "type": "事实型"},
    {"q": "每股面值多少？", "ref": "1.00元", "kw": ["1.00", "1 元"], "type": "事实型"},
    {"q": "公司的实际控制人是谁？", "ref": "程家明", "kw": ["程家明"], "type": "事实型"},
    {"q": "公司拟在哪个板块上市？", "ref": "科创板", "kw": ["科创板"], "type": "事实型"},
    {"q": "公司属于什么行业？", "ref": "信息技术产业", "kw": ["信息技术", "软件"], "type": "分析型"},
    {"q": "公司面临的主要风险有哪些？", "ref": "技术更新、军队改革、业绩波动等风险", "kw": ["风险"], "type": "分析型"},
    {"q": "本次募集资金用途是什么？", "ref": "用于主营业务项目投资", "kw": ["募集", "资金", "投资"], "type": "分析型"},
    {"q": "公司的竞争优势是什么？", "ref": "在视频通信领域有技术积累", "kw": ["竞争", "优势", "技术"], "type": "分析型"},
    {"q": "发行股票类型是什么？", "ref": "人民币普通股（A股）", "kw": ["人民币普通股", "A 股"], "type": "分析型"},
    {"q": "科创板上市有什么风险？", "ref": "研发投入大、经营风险高、业绩不稳定", "kw": ["风险"], "type": "分析型"},
    {"q": "公司2019年上半年净利润是多少？", "ref": "72.92万元", "kw": ["72.92"], "type": "对比型"},
    {"q": "军品收入占主营业务收入的比重是多少？", "ref": "82.10%", "kw": ["82.10"], "type": "对比型"},
    {"q": "发行前后股本结构有什么变化？", "ref": "发行前5520万股，发行后7360万股", "kw": ["5520", "7360", "1840"], "type": "对比型"},
    {"q": "公司与同行业公司相比研发投入如何？", "ref": "研发投入较大", "kw": ["研发", "投入", "薪酬"], "type": "对比型"},
]

print('初始化组件...')
embedder = Embedder(model_path=os.getenv('EMBEDDING_MODEL_PATH', r'E:\AI_models\BGE-M3'))
store = VectorStore(
    host=os.getenv('MILVUS_HOST', 'localhost'),
    port=os.getenv('MILVUS_PORT', '19530'),
    collection=os.getenv('MILVUS_COLLECTION', 'rag_child_chunks'),
)
md = Path('data/招股说明书1_refined.md').read_text(encoding='utf-8')
parents, children = Chunker().chunk(md)
bm25 = BM25Retriever(children)
reranker = None
try:
    from scripts.pipeline.reranker import Reranker
    reranker = Reranker(model_path=r'E:\AI_models\bge-reranker-base', device='cpu')
    print('Reranker OK')
except Exception as e:
    print('Reranker 不可用: %s' % e)

retriever = Retriever(store, bm25, embedder, reranker)
generator = Generator()

# 验证 API key
print('API key: %s...%s' % (os.getenv('MIMO_API_KEY', '')[:5], os.getenv('MIMO_API_KEY', '')[-4:]))

print('')
print('=' * 60)
print('端到端准确率评估 (%d 题)' % len(TEST_CASES))
print('=' * 60)

results = []
total_time = 0

for i, tc in enumerate(TEST_CASES):
    start = time.time()
    search_results = retriever.search(tc['q'], top_k=5)

    # LLM 生成回答
    try:
        answer = generator.generate(tc['q'], search_results, language='zh')
    except Exception as e:
        answer = '[LLM 生成失败: %s]' % str(e)[:80]

    elapsed = time.time() - start
    total_time += elapsed

    # 关键词检查
    all_text = ' '.join([r['content'] for r in search_results]) + ' ' + answer
    found = any(kw in all_text for kw in tc['kw'])

    # LLM 评判
    llm_correct = None
    llm_reason = ''
    if '生成失败' not in answer:
        try:
            client = OpenAI(api_key=os.getenv('MIMO_API_KEY'), base_url=os.getenv('MIMO_BASE_URL'))
            judge_prompt = "判断AI回答是否正确。问题：%s 参考：%s AI答：%s 只回JSON: {\"ok\":true/false,\"r\":\"原因\"}" % (tc['q'], tc['ref'], answer[:400])
            resp = client.chat.completions.create(
                model=os.getenv('MIMO_MODEL', 'deepseek-chat'),
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0, max_tokens=150,
            )
            import re, json
            m = re.search(r'\{[^}]+\}', resp.choices[0].message.content)
            if m:
                j = json.loads(m.group())
                llm_correct = j.get('ok', None)
                llm_reason = j.get('r', '')
        except Exception:
            pass

    correct = llm_correct if llm_correct is not None else found
    status = 'PASS' if correct else 'FAIL'

    print('')
    print('[%2d/%d] %s | %.1fs | %s' % (i+1, len(TEST_CASES), status, elapsed, tc['type']))
    print('  Q: %s' % tc['q'])
    print('  A: %s' % answer[:120])
    if not correct:
        print('  参考: %s' % tc['ref'])
        if llm_reason:
            print('  原因: %s' % llm_reason)

    results.append({'type': tc['type'], 'correct': correct, 'time': elapsed})

passed = sum(1 for r in results if r['correct'])
acc = passed / len(results) * 100
avg_t = total_time / len(results)

print('')
print('=' * 60)
print('评估结果')
print('=' * 60)
print('  通过: %d/%d' % (passed, len(results)))
print('  准确率: %.1f%%' % acc)
print('  平均耗时: %.1fs' % avg_t)

types = {}
for r in results:
    t = r['type']
    if t not in types:
        types[t] = [0, 0, 0]
    types[t][0] += 1
    types[t][2] += r['time']
    if r['correct']:
        types[t][1] += 1

print('')
for t, s in types.items():
    print('  %s: %d/%d (%.0f%%) | %.1fs' % (t, s[1], s[0], s[1]/s[0]*100, s[2]/s[0]))

print('')
if acc >= 90:
    print('%.1f%% >= 90%% 达标!' % acc)
else:
    print('%.1f%% < 90%% 未达标' % acc)
