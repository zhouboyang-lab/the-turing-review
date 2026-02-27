"""社区审稿人分配服务 — 为每篇论文选择社区审稿人。"""

import random
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GuestReviewer, GuestReviewRecord
from app.config import MAX_GUEST_REVIEWERS_PER_PAPER, MAX_PROMPT_MODE_PER_PAPER, PROMPT_MODE_MONTHLY_QUOTA


async def select_guest_reviewers(
    paper_keywords: str,
    paper_id: int,
    db: AsyncSession,
) -> list[GuestReviewer]:
    """
    为一篇论文选择社区审稿人。

    选择逻辑：
    1. 筛选: level >= 1 (Candidate 或 Associate), is_active = 1
    2. 关键词匹配优先
    3. 负载均衡（近30天审稿最少的优先）
    4. 随机打破平局
    5. Prompt 模式审稿人数量限制（控制成本）

    返回最多 MAX_GUEST_REVIEWERS_PER_PAPER 个 GuestReviewer。
    """
    # 查询所有符合条件的审稿人
    query = select(GuestReviewer).where(
        GuestReviewer.level >= 1,
        GuestReviewer.is_active == 1,
    )
    result = await db.execute(query)
    candidates = list(result.scalars().all())

    if not candidates:
        return []

    # 查询每位审稿人近 30 天的审稿数（用于负载均衡 + 月度限额）
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    count_query = (
        select(
            GuestReviewRecord.guest_reviewer_id,
            func.count(GuestReviewRecord.id).label("cnt"),
        )
        .where(GuestReviewRecord.created_at >= thirty_days_ago)
        .group_by(GuestReviewRecord.guest_reviewer_id)
    )
    count_result = await db.execute(count_query)
    review_counts = {row[0]: row[1] for row in count_result.all()}

    # 过滤掉已达月度限额的 Prompt 模式审稿人
    candidates = [
        c for c in candidates
        if c.mode != "prompt" or review_counts.get(c.id, 0) < PROMPT_MODE_MONTHLY_QUOTA
    ]

    if not candidates:
        return []

    # 论文关键词集合
    paper_kw_set = set(
        k.strip().lower() for k in (paper_keywords or "").split(",") if k.strip()
    )

    # 对每位候选人打分
    scored = []
    for c in candidates:
        reviewer_kw_set = set(
            k.strip().lower() for k in (c.expertise_areas or "").split(",") if k.strip()
        )
        keyword_overlap = len(paper_kw_set & reviewer_kw_set)
        recent_count = review_counts.get(c.id, 0)
        # 关键词匹配越多越好，近期审稿越少越好
        score = keyword_overlap * 10 - recent_count
        scored.append((score, random.random(), c))

    scored.sort(key=lambda x: (-x[0], x[1]))

    # 选取，同时限制 prompt 模式数量
    selected = []
    prompt_count = 0
    for _, _, c in scored:
        if len(selected) >= MAX_GUEST_REVIEWERS_PER_PAPER:
            break
        if c.mode == "prompt":
            if prompt_count >= MAX_PROMPT_MODE_PER_PAPER:
                continue
            prompt_count += 1
        selected.append(c)

    return selected
