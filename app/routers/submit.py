"""投稿路由 — 投稿页面和投稿API。"""

import asyncio
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper
from app.config import REQUIRE_EMAIL, DAILY_SUBMIT_LIMIT, MONTHLY_SUBMIT_LIMIT
from app.services.paper_service import save_upload, extract_text
from app.services.review_service import run_review_pipeline
from app.services.rate_limit_service import check_submission_limit

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/submit")
async def submit_page(request: Request):
    return templates.TemplateResponse("submit.html", {
        "request": request,
        "daily_limit": DAILY_SUBMIT_LIMIT,
        "monthly_limit": MONTHLY_SUBMIT_LIMIT,
    })


@router.post("/submit")
async def submit_paper(
    request: Request,
    title: str = Form(...),
    abstract: str = Form(...),
    authors: str = Form("Anonymous"),
    email: str = Form(""),
    keywords: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # 频率限制检查
    if REQUIRE_EMAIL and not email.strip():
        return templates.TemplateResponse("submit.html", {
            "request": request,
            "error": "Email is required to submit a paper.",
            "daily_limit": DAILY_SUBMIT_LIMIT,
            "monthly_limit": MONTHLY_SUBMIT_LIMIT,
        })

    if email.strip():
        allowed, error_msg = await check_submission_limit(email, db)
        if not allowed:
            return templates.TemplateResponse("submit.html", {
                "request": request,
                "error": error_msg,
                "daily_limit": DAILY_SUBMIT_LIMIT,
                "monthly_limit": MONTHLY_SUBMIT_LIMIT,
            })

    # 保存文件
    content = await file.read()
    file_path = save_upload(file.filename, content)

    # 提取文本
    content_text = extract_text(file_path)

    # 如果文本为空且有摘要，用摘要作为内容
    if not content_text.strip() or content_text.startswith("["):
        content_text = f"Title: {title}\n\nAbstract: {abstract}\n\n{content_text}"

    # 创建论文记录
    paper = Paper(
        title=title,
        abstract=abstract,
        authors=authors,
        email=email.strip().lower() if email else "",
        keywords=keywords,
        file_path=file_path,
        content_text=content_text,
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)

    # 后台触发审稿流程（不阻塞响应）
    asyncio.create_task(_background_review(paper.id))

    return RedirectResponse(url=f"/paper/{paper.id}", status_code=303)


async def _background_review(paper_id: int):
    """后台审稿任务。"""
    from app.database import async_session
    async with async_session() as db:
        paper = await db.get(Paper, paper_id)
        if paper:
            await run_review_pipeline(paper, db)
