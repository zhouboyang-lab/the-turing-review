"""统计面板路由。"""

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper, Review

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    # 各状态论文数量
    count_result = await db.execute(
        select(Paper.status, func.count(Paper.id)).group_by(Paper.status)
    )
    status_counts = dict(count_result.all())

    total = sum(status_counts.values())
    accepted = status_counts.get("accepted", 0)
    rejected = status_counts.get("rejected", 0)
    revision = status_counts.get("revision", 0)
    decided = accepted + rejected + revision

    # 总审稿数
    review_count_result = await db.execute(select(func.count(Review.id)))
    total_reviews = review_count_result.scalar() or 0

    stats = {
        "total": total,
        "accepted": accepted,
        "rejected": rejected,
        "revision": revision,
        "submitted": status_counts.get("submitted", 0),
        "under_review": status_counts.get("under_review", 0),
        "decided": decided,
        "acceptance_rate": (accepted / decided * 100) if decided > 0 else 0,
        "total_reviews": total_reviews,
    }

    # 各审稿人平均评分
    reviewer_result = await db.execute(
        select(
            Review.reviewer_name,
            func.count(Review.id).label("count"),
            func.avg(Review.novelty_score).label("avg_novelty"),
            func.avg(Review.soundness_score).label("avg_soundness"),
            func.avg(Review.writing_score).label("avg_writing"),
        ).group_by(Review.reviewer_name)
    )

    reviewer_stats = []
    for row in reviewer_result.all():
        avg_n = float(row.avg_novelty or 0)
        avg_s = float(row.avg_soundness or 0)
        avg_w = float(row.avg_writing or 0)
        reviewer_stats.append({
            "name": row.reviewer_name,
            "count": row.count,
            "avg_novelty": avg_n,
            "avg_soundness": avg_s,
            "avg_writing": avg_w,
            "avg_overall": (avg_n + avg_s + avg_w) / 3,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "reviewer_stats": reviewer_stats,
    })
