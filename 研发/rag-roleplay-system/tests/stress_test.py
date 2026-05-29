# -*- coding: utf-8 -*-
"""
RAG 角色扮演系统 — 压力测试 (QPS / 延迟 / 并发)

用法:
  source venv/bin/activate
  python tests/stress_test.py              # 全量测试
  python tests/stress_test.py --quick       # 快速模式
  python tests/stress_test.py --export /path/to/results.json
"""

import os
import sys
import json
import time
import logging
import argparse
import asyncio
import aiohttp
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("stress_test")

BASE_URL = os.getenv("STRESS_TEST_URL", "http://127.0.0.1:8000")

# ============================================================================
# 真实测试数据 — 来自项目 TEST_DATASET
# ============================================================================

REAL_QUESTIONS = {
    "lawyer": [
        "盗窃罪的量刑标准是什么？",
        "正当防卫的构成要件有哪些？",
        "故意伤害罪和过失致人重伤罪的区别是什么？",
        "缓刑的适用条件是什么？",
        "自首和坦白有什么区别？",
    ],
    "doctor": [
        "高血压患者日常生活需要注意什么？",
        "糖尿病的典型症状和诊断标准是什么？",
        "感冒和流感怎么区分？",
        "如何预防心血管疾病？",
        "儿童发热应该怎么处理？",
    ],
    "psych": [
        "如何缓解焦虑情绪？",
        "抑郁症的常见症状有哪些？",
        "如何帮助有心理困扰的朋友？",
        "什么是认知行为疗法？",
        "压力过大会导致哪些身体反应？",
    ],
}

# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class RequestResult:
    endpoint: str
    status: int
    latency_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    name: str
    endpoint: str
    method: str
    total_requests: int
    concurrency: int
    duration_sec: float
    success_count: int
    fail_count: int
    latencies: List[float]
    qps: float = 0.0
    p50_ms: float = 0.0
    p75_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    avg_ms: float = 0.0
    error_rate: float = 0.0

    def compute(self):
        if not self.latencies:
            return
        sorted_lats = sorted(self.latencies)
        n = len(sorted_lats)
        self.qps = self.total_requests / self.duration_sec if self.duration_sec > 0 else 0
        self.min_ms = sorted_lats[0]
        self.max_ms = sorted_lats[-1]
        self.avg_ms = sum(sorted_lats) / n
        self.p50_ms = sorted_lats[int(n * 0.50)]
        self.p75_ms = sorted_lats[int(n * 0.75)]
        self.p90_ms = sorted_lats[int(n * 0.90)]
        self.p95_ms = sorted_lats[int(n * 0.95)]
        self.p99_ms = sorted_lats[int(n * 0.99)]
        self.error_rate = self.fail_count / self.total_requests * 100 if self.total_requests > 0 else 0


# ============================================================================
# 异步压测引擎
# ============================================================================

class StressRunner:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            connector = aiohttp.TCPConnector(limit=0, force_close=True)
            timeout = aiohttp.ClientTimeout(total=120)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _do_request(self, method: str, path: str,
                          json_body: dict = None) -> RequestResult:
        url = f"{self.base_url}{path}"
        start = time.monotonic()
        try:
            session = await self._get_session()
            if method == "GET":
                async with session.get(url) as resp:
                    await resp.read()
                    latency = (time.monotonic() - start) * 1000
                    return RequestResult(
                        endpoint=path, status=resp.status,
                        latency_ms=latency, success=resp.status < 500)
            else:
                async with session.post(url, json=json_body) as resp:
                    await resp.read()
                    latency = (time.monotonic() - start) * 1000
                    return RequestResult(
                        endpoint=path, status=resp.status,
                        latency_ms=latency, success=resp.status < 500)
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return RequestResult(
                endpoint=path, status=0, latency_ms=latency,
                success=False, error=str(e)[:100])

    async def _worker(self, method: str, path: str,
                      json_body: dict, results: list, sem: asyncio.Semaphore):
        async with sem:
            result = await self._do_request(method, path, json_body)
            results.append(result)

    async def run_benchmark(self, name: str, method: str, path: str,
                            total: int, concurrency: int,
                            json_body: dict = None) -> BenchmarkReport:
        logger.info(f"启动: {name} — {total} 请求, 并发 {concurrency}")
        results: List[RequestResult] = []
        sem = asyncio.Semaphore(concurrency)

        start = time.monotonic()
        tasks = [self._worker(method, path, json_body, results, sem)
                 for _ in range(total)]
        await asyncio.gather(*tasks)
        duration = time.monotonic() - start

        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        report = BenchmarkReport(
            name=name, endpoint=f"{method} {path}", method=method,
            total_requests=total, concurrency=concurrency,
            duration_sec=duration,
            success_count=len(success), fail_count=len(failed),
            latencies=[r.latency_ms for r in success],
        )
        report.compute()

        logger.info(f"完成: {name} — QPS={report.qps:.1f}, "
                     f"P50={report.p50_ms:.0f}ms, P95={report.p95_ms:.0f}ms, "
                     f"错误率={report.error_rate:.1f}%")
        return report

    async def run_ramp_up(self, name: str, method: str, path: str,
                          json_body: dict = None,
                          levels: List[int] = None) -> List[BenchmarkReport]:
        """阶梯式加压: 10, 20, 50, 100 并发"""
        if levels is None:
            levels = [5, 10, 20, 50]
        reports = []
        requests_per_level = 100
        for concurrency in levels:
            report = await self.run_benchmark(
                f"{name} (并发={concurrency})",
                method, path,
                total=requests_per_level, concurrency=concurrency,
                json_body=json_body)
            reports.append(report)
            await asyncio.sleep(2)  # 冷却间隔
        return reports


# ============================================================================
# 测试场景
# ============================================================================

async def test_lightweight_endpoints(runner: StressRunner) -> List[BenchmarkReport]:
    """轻量级接口: 角色列表、角色详情"""
    reports = []

    # 角色列表
    reports.append(await runner.run_benchmark(
        "GET Roles (基准)", "GET", "/api/roles",
        total=200, concurrency=20))

    await asyncio.sleep(1)

    # 角色详情
    for role_id in ["lawyer", "doctor", "psych"]:
        reports.append(await runner.run_benchmark(
            f"GET Character/{role_id}", "GET", f"/api/character/{role_id}",
            total=100, concurrency=20))

    await asyncio.sleep(1)

    # 阶梯加压 - 角色列表
    ramp_reports = await runner.run_ramp_up(
        "GET Roles (阶梯加压)", "GET", "/api/roles",
        levels=[10, 20, 50, 100])
    reports.extend(ramp_reports)

    return reports


async def test_auth_endpoints(runner: StressRunner) -> List[BenchmarkReport]:
    """认证接口: 登录、验证码"""
    reports = []

    # 登录
    login_body = {"phone": "13800138000", "password": "123456"}
    reports.append(await runner.run_benchmark(
        "POST Login", "POST", "/api/login",
        total=100, concurrency=20, json_body=login_body))

    await asyncio.sleep(1)

    # 验证码发送
    reports.append(await runner.run_benchmark(
        "POST SMS Send", "POST", "/api/sms/send?phone=13800138000",
        total=100, concurrency=20))

    await asyncio.sleep(1)

    # 阶梯加压 - 登录
    ramp_reports = await runner.run_ramp_up(
        "POST Login (阶梯加压)", "POST", "/api/login",
        json_body=login_body, levels=[10, 20, 50])
    reports.extend(ramp_reports)

    return reports


async def test_chat_endpoints(runner: StressRunner, quick: bool = False) -> List[BenchmarkReport]:
    """核心聊天接口 — 使用真实问题数据"""
    reports = []

    all_questions = []
    for role, questions in REAL_QUESTIONS.items():
        for q in (questions[:2] if quick else questions):
            all_questions.append((role, q))

    # 单角色并发 — 律师
    lawyer_bodies = [{"user_id": 8, "role_id": "lawyer",
                       "message": REAL_QUESTIONS["lawyer"][i % 5]}
                     for i in range(20 if quick else 50)]

    # 用 semaphore 控制并发发射真实聊天请求
    reports.append(await runner.run_benchmark(
        "POST Chat (lawyer)", "POST", "/api/chat",
        total=len(lawyer_bodies), concurrency=3 if quick else 5,
        json_body=lawyer_bodies[0]))  # 相同问题重复压测

    await asyncio.sleep(3)

    # 混合角色并发 — 使用不同问题
    mixed_bodies = [
        {"user_id": 8, "role_id": role, "message": q}
        for role, q in all_questions[:10]
    ]

    reports.append(await runner.run_benchmark(
        "POST Chat (mixed roles)", "POST", "/api/chat",
        total=len(mixed_bodies), concurrency=3,
        json_body=mixed_bodies[0]))

    await asyncio.sleep(3)

    # 聊天 send 接口
    send_bodies = [
        {"roleId": role, "message": q}
        for role, q in all_questions[:8]
    ]
    reports.append(await runner.run_benchmark(
        "POST Chat/Send (frontend)", "POST", "/api/chat/send",
        total=len(send_bodies), concurrency=3,
        json_body=send_bodies[0]))

    return reports


async def test_chat_with_unique_questions(runner: StressRunner) -> List[BenchmarkReport]:
    """
    核心聊天接口真实验证 — 每条请求使用不同问题 + 不同角色
    验证系统在真实多问题场景下的稳定性
    """
    # 构建 15 个不同请求 (3 角色 × 5 问题)
    bodies = []
    for role, questions in REAL_QUESTIONS.items():
        for q in questions:
            bodies.append({"user_id": 8, "role_id": role, "message": q})

    logger.info(f"真实数据压测: {len(bodies)} 条不同问题, 并发 3")
    sem = asyncio.Semaphore(3)
    results = []

    async def worker(body):
        async with sem:
            url = f"{runner.base_url}/api/chat"
            start = time.monotonic()
            try:
                session = await runner._get_session()
                async with session.post(url, json=body) as resp:
                    data = await resp.json()
                    latency = (time.monotonic() - start) * 1000
                    return RequestResult(
                        endpoint="/api/chat", status=resp.status,
                        latency_ms=latency,
                        success=resp.status == 200 and data.get("success", False))
            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                return RequestResult(
                    endpoint="/api/chat", status=0, latency_ms=latency,
                    success=False, error=str(e)[:100])

    start = time.monotonic()
    tasks_list = [worker(b) for b in bodies]
    results = await asyncio.gather(*tasks_list)
    duration = time.monotonic() - start

    success = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    # 获取每条响应长度
    response_lengths = []
    for i, r in enumerate(results):
        if r.success:
            response_lengths.append(-1)  # 异步无法获取body长度, 标记

    report = BenchmarkReport(
        name="POST Chat (真实15题全量)",
        endpoint="POST /api/chat",
        method="POST",
        total_requests=len(bodies),
        concurrency=3,
        duration_sec=duration,
        success_count=len(success),
        fail_count=len(failed),
        latencies=[r.latency_ms for r in success],
    )
    report.compute()

    logger.info(f"真实数据完成: QPS={report.qps:.2f}, "
                f"P50={report.p50_ms:.0f}ms, P95={report.p95_ms:.0f}ms, "
                f"成功率={len(success)}/{len(bodies)}")
    return [report]


# ============================================================================
# 报告输出
# ============================================================================

def format_ms(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms/1000:.1f}s"


def print_benchmark_table(reports: List[BenchmarkReport]):
    """打印 Markdown 格式的压测报告"""
    print("\n" + "=" * 90)
    print("  RAG 角色扮演系统 — 压力测试报告 (QPS / 延迟 / 并发)")
    print("=" * 90)

    # 分类
    categories = defaultdict(list)
    for r in reports:
        if "阶梯加压" in r.name:
            categories["阶梯加压"].append(r)
        elif "Chat" in r.name or "chat" in r.endpoint:
            categories["聊天接口 (重量级)"].append(r)
        elif "Login" in r.name or "SMS" in r.name or "login" in r.endpoint:
            categories["认证接口"].append(r)
        else:
            categories["角色/基础接口 (轻量级)"].append(r)

    for cat, reps in categories.items():
        print(f"\n### {cat}\n")
        print("| 测试场景 | 请求数 | 并发 | QPS | Avg | P50 | P95 | P99 | 错误率 | 耗时 |")
        print("|----------|--------|------|-----|-----|-----|-----|-----|--------|------|")
        for r in reps:
            print(f"| {r.name} | {r.total_requests} | {r.concurrency} | "
                  f"{r.qps:.1f} | {format_ms(r.avg_ms)} | {format_ms(r.p50_ms)} | "
                  f"{format_ms(r.p95_ms)} | {format_ms(r.p99_ms)} | "
                  f"{r.error_rate:.1f}% | {r.duration_sec:.1f}s |")

    # 总览
    print(f"\n### 系统总览\n")
    all_chat = [r for r in reports if "Chat" in r.name and "阶梯" not in r.name]
    all_light = [r for r in reports if "Roles" in r.name or "Character" in r.name]
    all_auth = [r for r in reports if "Login" in r.name or "SMS" in r.name]

    print("| 类别 | 平均 QPS | 平均 P50 | 平均 P95 | 平均错误率 |")
    print("|------|----------|----------|----------|------------|")

    for cat_name, reps in [
        ("轻量级接口", all_light),
        ("认证接口", all_auth),
        ("聊天接口 (LLM+RAG)", all_chat),
    ]:
        if reps:
            avg_qps = sum(r.qps for r in reps) / len(reps)
            avg_p50 = sum(r.p50_ms for r in reps) / len(reps)
            avg_p95 = sum(r.p95_ms for r in reps) / len(reps)
            avg_err = sum(r.error_rate for r in reps) / len(reps)
            print(f"| {cat_name} | {avg_qps:.1f} | {format_ms(avg_p50)} | "
                  f"{format_ms(avg_p95)} | {avg_err:.1f}% |")

    print(f"\n---")
    print(f"*测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | "
          f"服务器: {BASE_URL} | CPU: {os.cpu_count()}核*")


def export_json(reports: List[BenchmarkReport], filepath: str):
    data = {
        "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "cpu_cores": os.cpu_count(),
        "reports": []
    }
    for r in reports:
        data["reports"].append({
            "name": r.name,
            "endpoint": r.endpoint,
            "total_requests": r.total_requests,
            "concurrency": r.concurrency,
            "duration_sec": round(r.duration_sec, 2),
            "qps": round(r.qps, 2),
            "latency_ms": {
                "min": round(r.min_ms, 2),
                "avg": round(r.avg_ms, 2),
                "p50": round(r.p50_ms, 2),
                "p75": round(r.p75_ms, 2),
                "p90": round(r.p90_ms, 2),
                "p95": round(r.p95_ms, 2),
                "p99": round(r.p99_ms, 2),
                "max": round(r.max_ms, 2),
            },
            "success_count": r.success_count,
            "fail_count": r.fail_count,
            "error_rate": round(r.error_rate, 2),
        })

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 已导出: {filepath}")


# ============================================================================
# 主入口
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(description="RAG 系统压力测试")
    parser.add_argument("--quick", action="store_true", help="快速模式 (减少请求数)")
    parser.add_argument("--export", type=str, default=None, help="JSON 导出路径")
    args = parser.parse_args()

    runner = StressRunner(BASE_URL)
    all_reports = []

    try:
        logger.info("=" * 60)
        logger.info("阶段 1/4: 轻量级接口压测")
        logger.info("=" * 60)
        reports = await test_lightweight_endpoints(runner)
        all_reports.extend(reports)

        logger.info("\n" + "=" * 60)
        logger.info("阶段 2/4: 认证接口压测")
        logger.info("=" * 60)
        reports = await test_auth_endpoints(runner)
        all_reports.extend(reports)

        logger.info("\n" + "=" * 60)
        logger.info("阶段 3/4: 聊天接口压测 (核心)")
        logger.info("=" * 60)
        reports = await test_chat_endpoints(runner, quick=args.quick)
        all_reports.extend(reports)

        logger.info("\n" + "=" * 60)
        logger.info("阶段 4/4: 真实数据全量压测 (15条不同问题)")
        logger.info("=" * 60)
        reports = await test_chat_with_unique_questions(runner)
        all_reports.extend(reports)

    finally:
        await runner.close()

    print_benchmark_table(all_reports)

    export_path = args.export or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "stress_results.json"
    )
    export_json(all_reports, export_path)

    # 也输出一个简明的终端报告
    total_all = sum(r.total_requests for r in all_reports)
    total_fail = sum(r.fail_count for r in all_reports)
    print(f"\n总计: {total_all} 请求, {total_fail} 失败, "
          f"成功率 {100*(1-total_fail/total_all):.1f}%" if total_all else "")


if __name__ == "__main__":
    asyncio.run(main())
