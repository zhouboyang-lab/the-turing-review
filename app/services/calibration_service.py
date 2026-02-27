"""校准测试服务 — 验证社区审稿人是否能生成合格的审稿报告。"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GuestReviewer
from app.reviewers.guest_reviewer import build_guest_runner

logger = logging.getLogger(__name__)

# 校准论文 — 一篇有趣但有明显问题的"论文"，用于测试审稿人的判断力
CALIBRATION_PAPER = {
    "title": "On the Computational Complexity of Tea Brewing: A Formal Analysis",
    "authors": "A. Turing, C. Shannon",
    "abstract": (
        "We present a formal analysis of the computational complexity of optimal tea brewing. "
        "We model the tea brewing process as a constraint satisfaction problem and prove that "
        "finding the optimal brewing parameters (temperature, steeping time, water-to-leaf ratio) "
        "is NP-hard in the general case. We propose a polynomial-time approximation algorithm "
        "that achieves a 1.5-approximation ratio and validate it through experiments with 12 "
        "varieties of tea. Our results suggest that most humans use suboptimal brewing strategies "
        "and could improve their tea quality by 23% using our algorithm."
    ),
    "keywords": "computational complexity, optimization, beverage science, NP-hardness",
    "content": """On the Computational Complexity of Tea Brewing: A Formal Analysis

1. Introduction

Tea brewing is one of humanity's oldest optimization problems, yet it has received surprisingly little attention from the theoretical computer science community. In this paper, we formalize the Tea Brewing Problem (TBP) and analyze its computational complexity.

The key parameters of tea brewing include: water temperature T (in Celsius), steeping time t (in seconds), water-to-leaf ratio r (in ml/g), and agitation frequency f (stirs per minute). The objective is to maximize a quality function Q(T, t, r, f) that captures the subjective experience of the brewed tea.

2. Problem Formulation

Definition 1 (Tea Brewing Problem). Given a set of tea leaves L with chemical composition vector c ∈ R^n, find parameters (T*, t*, r*, f*) that maximize Q(T, t, r, f | c).

We assume Q is a black-box function that can be evaluated through taste tests. Each evaluation requires brewing and tasting one cup, which takes approximately 5 minutes.

Theorem 1. The Tea Brewing Problem is NP-hard.

Proof sketch: We reduce from 3-SAT. Given a 3-SAT instance with n variables and m clauses, we construct a tea blend with n+m chemical compounds such that the optimal brewing parameters encode a satisfying assignment. The quality function Q maps satisfying assignments to high-quality brews and unsatisfying assignments to bitter or bland results. The full reduction is straightforward but tedious, so we leave the details to the appendix (which is not included in this version).

3. Approximation Algorithm

We propose GREEDY-BREW, a polynomial-time algorithm that iteratively adjusts each parameter while holding others fixed.

Algorithm 1: GREEDY-BREW
Input: Tea leaves L, initial parameters (T0, t0, r0, f0)
For each parameter p in {T, t, r, f}:
    Binary search for optimal value of p
    Update current best parameters
Return final parameters

Theorem 2. GREEDY-BREW achieves a 1.5-approximation ratio for the Tea Brewing Problem.

Proof: By the submodularity of the quality function Q... (proof omitted for brevity).

4. Experimental Results

We tested GREEDY-BREW on 12 varieties of tea (4 green, 4 black, 2 oolong, 2 herbal). For each variety, we compared our algorithm's output against: (a) manufacturer's recommended parameters, (b) expert barista parameters, and (c) random parameters.

Results: GREEDY-BREW achieved an average quality improvement of 23% over manufacturer recommendations, 8% over expert baristas, and 67% over random parameters. Quality was assessed by a panel of 5 tasters on a 1-10 scale.

Statistical significance was evaluated using a t-test (p < 0.05 for all comparisons except vs. expert baristas where p = 0.08).

5. Discussion

Our results demonstrate that tea brewing is a computationally hard problem, but good approximate solutions can be found efficiently. The main limitation of this work is the small sample size (5 tasters) and the subjective nature of the quality metric.

We note that our NP-hardness proof relies on a specific model of the quality function. Real tea brewing may have additional structure that makes it tractable in practice.

6. Conclusion

We have shown that optimal tea brewing is NP-hard but efficiently approximable. Future work includes extending our framework to coffee brewing (which we conjecture is PSPACE-hard due to the additional pressure variable in espresso) and applying reinforcement learning to the sequential tea brewing problem.

References:
[1] Knuth, D.E. "The Art of Tea Programming", 1975.
[2] Dijkstra, E.W. "A Note on Two Problems in Connection with Teapots", 1959.
[3] Various fabricated references.""",
}


def validate_review_format(result) -> list[str]:
    """验证审稿结果格式，返回错误列表（空列表=通过）。"""
    errors = []

    # 检查是否为回退结果（JSON 解析失败）
    if result.strengths == ["Unable to parse structured review"]:
        errors.append("Response is not valid JSON in ReviewResult format")
        return errors

    # 分数范围
    for name, val in [
        ("novelty_score", result.novelty_score),
        ("soundness_score", result.soundness_score),
        ("writing_score", result.writing_score),
    ]:
        if not (1 <= val <= 10):
            errors.append(f"{name} = {val}, must be 1-10")

    # strengths/weaknesses 数量
    if len(result.strengths) < 3:
        errors.append(f"Only {len(result.strengths)} strengths, need at least 3")
    if len(result.weaknesses) < 3:
        errors.append(f"Only {len(result.weaknesses)} weaknesses, need at least 3")

    # 详评长度
    if len(result.detailed_comments) < 200:
        errors.append(f"detailed_comments is {len(result.detailed_comments)} chars, need 200+")

    # decision 合法性
    valid_decisions = {"accept", "minor_revision", "major_revision", "reject"}
    if result.decision not in valid_decisions:
        errors.append(f"decision '{result.decision}' not in {valid_decisions}")

    return errors


async def run_calibration_test(guest_reviewer: GuestReviewer, db: AsyncSession) -> tuple[bool, str]:
    """
    对社区审稿人运行校准测试。

    返回: (passed, error_message)
    """
    runner = build_guest_runner(guest_reviewer)

    try:
        result, raw = await runner.review(
            title=CALIBRATION_PAPER["title"],
            abstract=CALIBRATION_PAPER["abstract"],
            keywords=CALIBRATION_PAPER["keywords"],
            content=CALIBRATION_PAPER["content"],
            authors=CALIBRATION_PAPER["authors"],
        )
    except Exception as e:
        error_msg = f"API call failed: {str(e)[:500]}"
        logger.error(f"Calibration failed for {guest_reviewer.display_name}: {error_msg}")
        guest_reviewer.calibration_passed = 0
        guest_reviewer.calibration_error = error_msg
        await db.commit()
        return False, error_msg

    # 验证格式
    errors = validate_review_format(result)

    if errors:
        error_msg = "; ".join(errors)
        guest_reviewer.calibration_passed = 0
        guest_reviewer.calibration_error = error_msg
        await db.commit()
        return False, error_msg

    # 通过
    guest_reviewer.calibration_passed = 1
    guest_reviewer.calibration_error = ""
    guest_reviewer.level = 1  # 晋升为 Candidate
    await db.commit()
    logger.info(f"Calibration passed for {guest_reviewer.display_name}, promoted to Candidate")
    return True, ""
