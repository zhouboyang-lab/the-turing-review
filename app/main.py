"""The Turing Review — An AI-Operated Academic Journal."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.database import init_db
from app.models import Paper
from app.routers import submit, papers, dashboard, guest


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="The Turing Review",
    description="An experimental academic journal entirely operated by AI.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 注册路由
app.include_router(submit.router)
app.include_router(papers.router)
app.include_router(dashboard.router)
app.include_router(guest.router)

templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home(request: Request):
    from app.database import async_session
    async with async_session() as db:
        result = await db.execute(
            select(Paper).order_by(Paper.submitted_at.desc()).limit(10)
        )
        recent_papers = result.scalars().all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_papers": recent_papers,
    })
