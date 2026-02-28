"""论文展示路由 — 论文列表、详情页和已发表论文。"""

import json
from collections import OrderedDict
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper, Review

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/paper/{paper_id}")
async def paper_detail(request: Request, paper_id: int, db: AsyncSession = Depends(get_db)):
    paper = await db.get(Paper, paper_id)
    if not paper:
        return HTMLResponse("<h1>Paper not found</h1>", status_code=404)

    # 解析审稿意见中的JSON列表字段
    for review in paper.reviews:
        try:
            review.strengths_list = json.loads(review.strengths) if review.strengths else []
        except json.JSONDecodeError:
            review.strengths_list = [review.strengths] if review.strengths else []
        try:
            review.weaknesses_list = json.loads(review.weaknesses) if review.weaknesses else []
        except json.JSONDecodeError:
            review.weaknesses_list = [review.weaknesses] if review.weaknesses else []

    return templates.TemplateResponse("paper_detail.html", {"request": request, "paper": paper})


@router.get("/papers")
async def paper_list(request: Request, status: str = None, db: AsyncSession = Depends(get_db)):
    # 查询论文
    query = select(Paper).order_by(Paper.submitted_at.desc())
    if status:
        query = query.where(Paper.status == status)
    result = await db.execute(query)
    papers = result.scalars().all()

    # 统计各状态数量
    count_result = await db.execute(
        select(Paper.status, func.count(Paper.id)).group_by(Paper.status)
    )
    status_counts = dict(count_result.all())

    counts = {
        "total": sum(status_counts.values()),
        "accepted": status_counts.get("accepted", 0),
        "under_review": status_counts.get("under_review", 0),
        "revision": status_counts.get("revision", 0),
        "rejected": status_counts.get("rejected", 0),
        "submitted": status_counts.get("submitted", 0),
    }

    return templates.TemplateResponse("papers.html", {
        "request": request,
        "papers": papers,
        "status_filter": status,
        "counts": counts,
    })


@router.get("/published")
async def published_papers(request: Request, db: AsyncSession = Depends(get_db)):
    """已发表论文页面 — 按期号（月份）分组展示。"""
    # 查询所有 accepted 论文
    result = await db.execute(
        select(Paper).where(Paper.status == "accepted").order_by(Paper.decided_at.desc())
    )
    papers = result.scalars().all()

    # 总投稿数（用于计算接受率）
    total_decided = await db.scalar(
        select(func.count(Paper.id)).where(
            Paper.status.in_(["accepted", "rejected", "revision"])
        )
    ) or 0

    # 按月份分组为期号
    issues = OrderedDict()
    for paper in papers:
        dt = paper.decided_at or paper.submitted_at
        key = dt.strftime("%Y-%m")
        if key not in issues:
            issues[key] = {
                "label": dt.strftime("%B %Y"),  # e.g. "March 2026"
                "papers": [],
            }
        issues[key]["papers"].append(paper)

    # 计算 Volume 编号（按月份从早到晚）
    sorted_keys = sorted(issues.keys())
    for i, key in enumerate(sorted_keys, 1):
        issues[key]["volume"] = i

    return templates.TemplateResponse("published.html", {
        "request": request,
        "issues": issues,
        "total_published": len(papers),
        "acceptance_rate": round(len(papers) / total_decided * 100) if total_decided > 0 else 0,
    })
