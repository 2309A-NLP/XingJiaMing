"""BM25 关键词检索（jieba 分词版）

支持三种增强检索模式：
- 布尔查询：AND/OR/NOT 组合条件
- 短语匹配：引号内内容必须完整出现
- 模糊匹配：基于编辑距离的相似词匹配
"""
from __future__ import annotations
import logging
import re
from typing import List, Tuple
from difflib import SequenceMatcher
import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# 停用词：常见的无意义词，过滤掉能减少噪音
_STOPWORDS = frozenset([
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
    "吗", "吧", "啊", "呢", "嗯", "哦", "哈", "呀", "嘛", "啦",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "but", "or",
    "not", "no", "so", "if", "then", "than", "that", "this", "these",
    "those", "it", "its", "they", "them", "their", "we", "our", "you",
])


def _preprocess_table(text: str) -> str:
    """预处理表格格式，将 ['a','b','c'] 转换为空格分隔的文本"""
    # 处理 ['姓名','职务','任职状态',...] 格式
    # 将方括号内的逗号分隔内容转换为空格分隔
    text = re.sub(r"\['([^']*?)'\]", r'\1', text)
    text = re.sub(r'\["([^"]*?)"\]', r'\1', text)
    # 处理剩余的逗号
    text = text.replace(',', ' ')
    return text


def _tokenize(text: str) -> List[str]:
    """jieba 分词 + 过滤停用词和单字符"""
    # 预处理表格格式
    text = _preprocess_table(text)
    text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)
    words = jieba.lcut(text)
    return [w.strip().lower() for w in words if w.strip() and w.strip().lower() not in _STOPWORDS and len(w.strip()) >= 2]


def _extract_phrases(query: str) -> Tuple[List[str], str]:
    """提取引号内的短语，返回 (短语列表, 剩余文本)"""
    # 支持中文引号和英文引号
    pattern = r'[""「]([^""」]+)[""」]'
    phrases = re.findall(pattern, query)
    remaining = re.sub(pattern, ' ', query).strip()
    return phrases, remaining


def _parse_boolean(query: str) -> dict:
    """解析布尔查询，返回结构化的查询条件

    支持格式：
    - AND: 人工智能 AND 机器学习
    - OR: 深度学习 OR 神经网络
    - NOT: 人工智能 NOT 机器人
    - 组合: (深度学习 OR 神经网络) AND 图像识别
    """
    # 用大写标准化操作符
    q = query.strip()

    # 检测是否有布尔操作符
    has_and = ' AND ' in q.upper()
    has_or = ' OR ' in q.upper()
    has_not = ' NOT ' in q.upper()

    if not (has_and or has_or or has_not):
        return {'type': 'simple', 'query': q}

    # 分割 NOT（优先级最高）
    if has_not:
        parts = re.split(r'\s+NOT\s+', q, flags=re.IGNORECASE)
        must_include = parts[0].strip()
        must_exclude = parts[1].strip() if len(parts) > 1 else ''
        return {'type': 'not', 'include': must_include, 'exclude': must_exclude}

    # 分割 OR
    if has_or:
        parts = re.split(r'\s+OR\s+', q, flags=re.IGNORECASE)
        return {'type': 'or', 'terms': [p.strip() for p in parts]}

    # 分割 AND
    if has_and:
        parts = re.split(r'\s+AND\s+', q, flags=re.IGNORECASE)
        return {'type': 'and', 'terms': [p.strip() for p in parts]}

    return {'type': 'simple', 'query': q}


def _edit_distance(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离（Levenshtein distance）"""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def _fuzzy_match_score(term: str, text: str, threshold: float = 0.6) -> float:
    """计算 term 与 text 中词语的模糊匹配得分

    threshold: 相似度阈值，低于此值不匹配
    返回最高匹配得分（0-1）
    """
    words = _tokenize(text)
    if not words:
        return 0.0

    term_lower = term.lower()
    max_score = 0.0

    for word in words:
        # 完全匹配
        if term_lower == word:
            return 1.0

        # 包含关系
        if term_lower in word or word in term_lower:
            score = min(len(term_lower), len(word)) / max(len(term_lower), len(word))
            max_score = max(max_score, score)
            continue

        # 编辑距离匹配（只对长度 >= 3 的词做模糊匹配）
        if len(term_lower) >= 3 and len(word) >= 3:
            dist = _edit_distance(term_lower, word)
            max_len = max(len(term_lower), len(word))
            similarity = 1.0 - (dist / max_len)
            if similarity >= threshold:
                max_score = max(max_score, similarity)

    return max_score


class BM25Retriever:
    """BM25 关键词检索器，支持标准/布尔/短语/模糊四种检索模式。"""

    def __init__(self, chunks: list):
        self._chunks = chunks
        self._texts = [c.content for c in chunks]
        if chunks:
            tokenized = [_tokenize(t) for t in self._texts]
            self._bm25 = BM25Okapi(tokenized)
            logger.info('BM25 索引建立完成: %d 个文档', len(chunks))
        else:
            self._bm25 = None
            logger.info('BM25 初始化为空')

    def search(self, query: str, top_k: int = 20, match_mode: str = "standard") -> List[dict]:
        """统一检索入口，根据 match_mode 分发到不同检索策略"""
        if not self._bm25:
            return []

        if match_mode == "auto":
            match_mode = self._detect_query_type(query)

        if match_mode == "boolean":
            results = self._boolean_search(query, top_k)
        elif match_mode == "phrase":
            results = self._phrase_search(query, top_k)
        elif match_mode == "fuzzy":
            results = self._fuzzy_search(query, top_k)
        else:
            results = self._standard_search(query, top_k)

        return results

    def _detect_query_type(self, query: str) -> str:
        """自动检测查询类型"""
        # 有引号 → 短语匹配
        if re.search(r'[""「]', query):
            return "phrase"
        # 有布尔操作符 → 布尔查询
        if re.search(r'\s+(AND|OR|NOT)\s+', query, re.IGNORECASE):
            return "boolean"
        return "standard"

    def _standard_search(self, query: str, top_k: int) -> List[dict]:
        """标准 BM25 检索"""
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        return self._build_results(scores, top_k)

    def _boolean_search(self, query: str, top_k: int) -> List[dict]:
        """布尔查询：支持 AND, OR, NOT

        AND: 所有词都必须出现
        OR: 任一词出现即可
        NOT: 排除包含某词的结果
        """
        parsed = _parse_boolean(query)
        logger.info('布尔查询解析: %s', parsed)

        if parsed['type'] == 'simple':
            return self._standard_search(parsed['query'], top_k)

        if parsed['type'] == 'and':
            # 对每个子查询做 BM25 检索，取交集（按得分排序）
            all_results = []
            for term in parsed['terms']:
                results = self._standard_search(term, top_k * 2)
                all_results.append({r['chunk_id']: r for r in results})
            if not all_results:
                return []
            # 取交集：所有子查询都出现的 chunk
            common_ids = set(all_results[0].keys())
            for result_set in all_results[1:]:
                common_ids &= set(result_set.keys())
            # 合并得分
            merged = []
            for cid in common_ids:
                total_score = sum(rs[cid]['score'] for rs in all_results if cid in rs)
                merged.append({**all_results[0][cid], 'score': total_score})
            merged.sort(key=lambda x: x['score'], reverse=True)
            return merged[:top_k]

        if parsed['type'] == 'or':
            # 对每个子查询做 BM25 检索，取并集（按得分排序）
            seen = {}
            for term in parsed['terms']:
                results = self._standard_search(term, top_k * 2)
                for r in results:
                    cid = r['chunk_id']
                    if cid not in seen or r['score'] > seen[cid]['score']:
                        seen[cid] = r
            merged = sorted(seen.values(), key=lambda x: x['score'], reverse=True)
            return merged[:top_k]

        if parsed['type'] == 'not':
            # 先检索包含的词，再排除含有排除词的结果
            include_results = self._standard_search(parsed['include'], top_k * 3)
            exclude_tokens = set(_tokenize(parsed['exclude']))
            if not exclude_tokens:
                return include_results[:top_k]
            filtered = []
            for r in include_results:
                content_tokens = set(_tokenize(r['content']))
                if not content_tokens & exclude_tokens:
                    filtered.append(r)
            return filtered[:top_k]

        return self._standard_search(query, top_k)

    def _phrase_search(self, query: str, top_k: int) -> List[dict]:
        """短语匹配：引号内的内容必须完整出现在文本中

        先用 BM25 初筛，再用精确短语匹配过滤和重新排序。
        没有引号的部分走标准 BM25。
        """
        phrases, remaining = _extract_phrases(query)
        logger.info('短语匹配: phrases=%s, remaining=%s', phrases, remaining)

        # 如果没有提取到短语，回退到标准检索
        if not phrases:
            return self._standard_search(query, top_k)

        # 先用 BM25 做初筛（用剩余文本 + 短语文本）
        bm25_query = remaining if remaining.strip() else ' '.join(phrases)
        candidates = self._standard_search(bm25_query, top_k * 3)

        # 用精确短语匹配过滤和评分
        results = []
        for r in candidates:
            content = r['content']
            phrase_hits = 0
            for phrase in phrases:
                if phrase in content:
                    phrase_hits += 1

            if phrase_hits > 0:
                # 短语匹配命中，大幅加分
                phrase_boost = phrase_hits * 2.0
                results.append({**r, 'score': r['score'] + phrase_boost, 'phrase_hits': phrase_hits})

        results.sort(key=lambda x: x['score'], reverse=True)

        # 如果短语匹配没有结果，返回 BM25 标准结果（但标注无短语命中）
        if not results:
            logger.info('短语匹配无结果，回退到标准检索')
            return self._standard_search(query, top_k)

        return results[:top_k]

    def _fuzzy_search(self, query: str, top_k: int) -> List[dict]:
        """模糊匹配：基于编辑距离的相似词匹配

        适合容忍拼写错误、近义词场景。
        先用 BM25 标准检索，再用模糊匹配对候选结果重新评分。
        """
        tokens = _tokenize(query)
        if not tokens:
            return []

        # 先用 BM25 标准检索获取候选
        candidates = self._standard_search(query, top_k * 3)

        # 对每个候选重新评分：BM25 分数 + 模糊匹配加分
        for r in candidates:
            fuzzy_bonus = 0.0
            for token in tokens:
                match_score = _fuzzy_match_score(token, r['content'])
                if match_score > 0:
                    fuzzy_bonus += match_score
            r['score'] = r['score'] + fuzzy_bonus * 0.5

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:top_k]

    def _build_results(self, scores, top_k: int) -> List[dict]:
        """从 BM25 分数数组构建结果列表"""
        import numpy as np
        top_indices = np.argsort(scores)[-top_k:][::-1]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    'chunk_id': self._chunks[idx].chunk_id,
                    'parent_id': self._chunks[idx].parent_id,
                    'content': self._texts[idx],
                    'section_title': self._chunks[idx].metadata.get('section_title', ''),
                    'page_numbers': self._chunks[idx].metadata.get('page_numbers', []),
                    'score': float(scores[idx]),
                })
        return results
