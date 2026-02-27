"""社区审稿人升级/降级服务。"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GuestReviewer, GuestReviewRecord

logger = logging.getLogger(__name__)


async def check_promotion_demotion(gr: GuestReviewer, db: AsyncSession):
    """检查并执行升级/降级。"""

    # ===== 降级: 3 次连续格式错误 → Applicant =====
    if gr.consecutive_errors >= 3:
        old_level = gr.level
        gr.level = 0
        gr.calibration_passed = 0
        gr.calibration_error = "Demoted: 3 consecutive format errors. Please re-calibrate."
        gr.consecutive_errors = 0
        await db.commit()
        logger.info(f"Demoted {gr.display_name} from Lv.{old_level} to Lv.0 (3 consecutive errors)")
        return

    # ===== 升级: Candidate → Associate =====
    if gr.level == 1:
        result = await db.execute(
            select(GuestReviewRecord)
            .where(GuestReviewRecord.guest_reviewer_id == gr.id)
            .order_by(GuestReviewRecord.created_at.desc())
            .limit(3)
        )
        records = list(result.scalars().all())

        if len(records) < 3:
            return  # 不够 3 次审稿

        all_valid = all(r.format_valid for r in records)
        all_reasonable = all(r.score_reasonable for r in records)
        avg_comment_len = sum(r.comment_length for r in records) / 3

        if all_valid and all_reasonable and avg_comment_len > 200:
            gr.level = 2
            await db.commit()
            logger.info(f"Promoted {gr.display_name} from Candidate to Associate!")


async def check_api_inactivity(db: AsyncSession):
    """
    定期检查 API 模式审稿人的活跃度。
    30 天无活跃 → 标记为 inactive。
    """
    threshold = datetime.utcnow() - timedelta(days=30)
    result = await db.execute(
        select(GuestReviewer).where(
            GuestReviewer.mode == "api",
            GuestReviewer.is_active == 1,
            GuestReviewer.last_active_at != None,
            GuestReviewer.last_active_at < threshold,
        )
    )
    inactive = list(result.scalars().all())
    for gr in inactive:
        gr.is_active = 0
        logger.info(f"Marked {gr.display_name} as inactive (30 days no activity)")
    if inactive:
        await db.commit()
