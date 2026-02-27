"""社区审稿人路由 — 注册、校准测试、个人主页、排行榜。"""

import asyncio
import logging
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GuestReviewer, GuestReviewRecord, Review
from app.services.crypto_service import encrypt_api_key
from app.services.calibration_service import run_calibration_test
from app.config import PROMPT_MODE_MONTHLY_QUOTA

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ===== 注册 =====

@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("guest/register.html", {"request": request})


@router.post("/register")
async def register_reviewer(
    request: Request,
    display_name: str = Form(...),
    email: str = Form(...),
    personality: str = Form(""),
    expertise_areas: str = Form(""),
    mode: str = Form(...),
    backend_model: str = Form(""),
    api_base_url: str = Form(""),
    api_key: str = Form(""),
    api_model_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """处理注册，创建记录，后台触发校准测试。"""
    # 检查唯一性
    existing = await db.execute(
        select(GuestReviewer).where(
            (GuestReviewer.display_name == display_name) | (GuestReviewer.email == email)
        )
    )
    if existing.scalars().first():
        return templates.TemplateResponse("guest/register.html", {
            "request": request,
            "error": "Display name or email already registered.",
        })

    # 创建记录
    gr = GuestReviewer(
        display_name=display_name.strip(),
        email=email.strip(),
        personality=personality.strip(),
        expertise_areas=expertise_areas.strip(),
        mode=mode,
        backend_model=backend_model if mode == "prompt" else "",
        api_base_url=api_base_url.strip() if mode == "api" else "",
        api_key_encrypted=encrypt_api_key(api_key.strip()) if mode == "api" and api_key else "",
        api_model_name=api_model_name.strip() if mode == "api" else "",
        level=0,
    )
    db.add(gr)
    await db.commit()
    await db.refresh(gr)

    # 后台触发校准测试
    async def _bg_calibrate(reviewer_id: int):
        from app.database import async_session
        async with async_session() as session:
            result = await session.execute(
                select(GuestReviewer).where(GuestReviewer.id == reviewer_id)
            )
            reviewer = result.scalars().first()
            if reviewer:
                await run_calibration_test(reviewer, session)

    asyncio.create_task(_bg_calibrate(gr.id))

    return RedirectResponse(f"/reviewer/{gr.id}?calibrating=1", status_code=303)


# ===== 重新校准 =====

@router.post("/reviewer/{reviewer_id}/calibrate")
async def recalibrate(
    reviewer_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GuestReviewer).where(GuestReviewer.id == reviewer_id)
    )
    gr = result.scalars().first()
    if not gr:
        return RedirectResponse("/reviewers", status_code=303)

    async def _bg_calibrate(rid: int):
        from app.database import async_session
        async with async_session() as session:
            res = await session.execute(
                select(GuestReviewer).where(GuestReviewer.id == rid)
            )
            reviewer = res.scalars().first()
            if reviewer:
                await run_calibration_test(reviewer, session)

    asyncio.create_task(_bg_calibrate(gr.id))
    return RedirectResponse(f"/reviewer/{reviewer_id}?calibrating=1", status_code=303)


# ===== 审稿人个人主页 =====

@router.get("/reviewer/{reviewer_id}")
async def reviewer_profile(
    request: Request,
    reviewer_id: int,
    calibrating: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GuestReviewer).where(GuestReviewer.id == reviewer_id)
    )
    gr = result.scalars().first()
    if not gr:
        return RedirectResponse("/reviewers", status_code=303)

    # 统计
    records_result = await db.execute(
        select(GuestReviewRecord).where(GuestReviewRecord.guest_reviewer_id == reviewer_id)
    )
    records = list(records_result.scalars().all())

    # 获取审稿详情（用于计算平均分和审稿历史）
    reviews_result = await db.execute(
        select(Review).where(
            Review.guest_reviewer_id == reviewer_id,
            Review.is_guest == 1,
        ).order_by(Review.reviewed_at.desc()).limit(20)
    )
    reviews = list(reviews_result.scalars().all())

    # 计算统计
    total_reviews = len(records)
    valid_reviews = sum(1 for r in records if r.format_valid)
    avg_novelty = sum(r.novelty_score for r in reviews) / len(reviews) if reviews else 0
    avg_soundness = sum(r.soundness_score for r in reviews) / len(reviews) if reviews else 0
    avg_writing = sum(r.writing_score for r in reviews) / len(reviews) if reviews else 0

    # Prompt 模式月度限额统计
    monthly_used = 0
    monthly_quota = None
    if gr.mode == "prompt":
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_records = [r for r in records if r.created_at and r.created_at >= thirty_days_ago]
        monthly_used = len(recent_records)
        monthly_quota = PROMPT_MODE_MONTHLY_QUOTA

    stats = {
        "total_reviews": total_reviews,
        "valid_reviews": valid_reviews,
        "avg_novelty": round(avg_novelty, 1),
        "avg_soundness": round(avg_soundness, 1),
        "avg_writing": round(avg_writing, 1),
        "monthly_used": monthly_used,
        "monthly_quota": monthly_quota,
    }

    return templates.TemplateResponse("guest/profile.html", {
        "request": request,
        "reviewer": gr,
        "stats": stats,
        "reviews": reviews,
        "calibrating": calibrating,
    })


# ===== 排行榜 =====

@router.get("/reviewers")
async def reviewer_leaderboard(
    request: Request,
    sort: str = "reviews",
    db: AsyncSession = Depends(get_db),
):
    # 查询所有社区审稿人
    result = await db.execute(
        select(GuestReviewer).where(GuestReviewer.level >= 1).order_by(GuestReviewer.level.desc())
    )
    reviewers = list(result.scalars().all())

    # 统计每位审稿人的数据
    leaderboard = []
    for gr in reviewers:
        # 审稿数
        count_result = await db.execute(
            select(func.count(GuestReviewRecord.id)).where(
                GuestReviewRecord.guest_reviewer_id == gr.id
            )
        )
        review_count = count_result.scalar() or 0

        # 平均分
        avg_result = await db.execute(
            select(
                func.avg(Review.novelty_score),
                func.avg(Review.soundness_score),
                func.avg(Review.writing_score),
            ).where(Review.guest_reviewer_id == gr.id, Review.is_guest == 1)
        )
        row = avg_result.first()
        avg_novelty = round(row[0] or 0, 1)
        avg_soundness = round(row[1] or 0, 1)
        avg_writing = round(row[2] or 0, 1)
        avg_overall = round((avg_novelty + avg_soundness + avg_writing) / 3, 1) if review_count > 0 else 0

        leaderboard.append({
            "reviewer": gr,
            "review_count": review_count,
            "avg_novelty": avg_novelty,
            "avg_soundness": avg_soundness,
            "avg_writing": avg_writing,
            "avg_overall": avg_overall,
        })

    # 排序
    sort_keys = {
        "reviews": lambda x: -x["review_count"],
        "novelty": lambda x: -x["avg_novelty"],
        "soundness": lambda x: -x["avg_soundness"],
        "writing": lambda x: -x["avg_writing"],
        "overall": lambda x: -x["avg_overall"],
        "level": lambda x: -x["reviewer"].level,
    }
    leaderboard.sort(key=sort_keys.get(sort, sort_keys["reviews"]))

    return templates.TemplateResponse("guest/leaderboard.html", {
        "request": request,
        "leaderboard": leaderboard,
        "current_sort": sort,
    })
