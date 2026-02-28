"""投稿频率限制服务 — 基于 email 限制每日/每月投稿数。"""

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper
from app.config import DAILY_SUBMIT_LIMIT, MONTHLY_SUBMIT_LIMIT


async def check_submission_limit(email: str, db: AsyncSession) -> tuple[bool, str]:
    """
    检查投稿频率是否超限。
    返回 (allowed, error_message)。allowed=True 表示可以投稿。
    """
    if not email or not email.strip():
        return False, "Email is required to submit a paper."

    email = email.strip().lower()
    now = datetime.utcnow()

    # 今日投稿数
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = await db.scalar(
        select(func.count(Paper.id)).where(
            Paper.email == email,
            Paper.submitted_at >= today_start,
        )
    )

    if daily_count >= DAILY_SUBMIT_LIMIT:
        return False, (
            f"Daily limit reached ({DAILY_SUBMIT_LIMIT} submissions/day). "
            f"Please try again tomorrow."
        )

    # 本月投稿数
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_count = await db.scalar(
        select(func.count(Paper.id)).where(
            Paper.email == email,
            Paper.submitted_at >= month_start,
        )
    )

    if monthly_count >= MONTHLY_SUBMIT_LIMIT:
        return False, (
            f"Monthly limit reached ({MONTHLY_SUBMIT_LIMIT} submissions/month). "
            f"Your quota resets on the 1st of next month."
        )

    return True, ""
