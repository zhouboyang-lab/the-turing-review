"""审稿调度服务 — 并行触发内置+社区AI审稿人，然后由主编做决定。"""

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, Review, EditorialDecision, GuestReviewRecord
from app.reviewers.base import BaseReviewer, ReviewResult
from app.reviewers.claude_reviewer import ClaudeReviewer
from app.reviewers.openai_reviewer import OpenAIReviewer
from app.reviewers.deepseek_reviewer import DeepSeekReviewer
from app.reviewers.guest_reviewer import build_guest_runner
from app.reviewers.editor import AIEditor
from app.services.email_service import send_decision_email
from app.services.assignment_service import select_guest_reviewers
from app.services.calibration_service import validate_review_format
from app.services.promotion_service import check_promotion_demotion

logger = logging.getLogger(__name__)


def get_active_reviewers() -> list[BaseReviewer]:
    """获取所有可用的内置审稿人实例。"""
    reviewers = []
    from app.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY

    if ANTHROPIC_API_KEY:
        reviewers.append(ClaudeReviewer())
    if OPENAI_API_KEY:
        reviewers.append(OpenAIReviewer())
    if DEEPSEEK_API_KEY:
        reviewers.append(DeepSeekReviewer())

    return reviewers


async def _run_single_review(
    reviewer: BaseReviewer,
    title: str,
    abstract: str,
    keywords: str,
    content: str,
    authors: str = "Anonymous",
) -> tuple[str, str, ReviewResult, str]:
    """运行单个审稿人的审稿。返回 (name, provider, result, raw)。"""
    try:
        result, raw = await reviewer.review(title, abstract, keywords, content, authors=authors)
        return reviewer.name, reviewer.model_provider, result, raw
    except Exception as e:
        logger.error(f"Reviewer {reviewer.name} failed: {e}")
        fallback = ReviewResult(
            decision="major_revision",
            novelty_score=5,
            soundness_score=5,
            writing_score=5,
            strengths=["Review could not be completed"],
            weaknesses=[f"Reviewer error: {str(e)[:200]}"],
            detailed_comments=f"An error occurred during review: {e}",
            suggestions="Please resubmit for re-review.",
        )
        return reviewer.name, reviewer.model_provider, fallback, str(e)


def _scores_reasonable(result: ReviewResult) -> bool:
    """检查分数是否合理（不全是 1 或全是 10）。"""
    scores = [result.novelty_score, result.soundness_score, result.writing_score]
    return not (all(s <= 1 for s in scores) or all(s >= 10 for s in scores))


def _save_review_record(
    paper_id: int,
    name: str,
    provider: str,
    result: ReviewResult,
    raw: str,
    is_guest: int = 0,
    guest_reviewer_id: int = None,
    guest_level: int = None,
) -> Review:
    """构建 Review 数据库记录。"""
    return Review(
        paper_id=paper_id,
        reviewer_name=name,
        model_provider=provider,
        decision=result.decision,
        novelty_score=result.novelty_score,
        soundness_score=result.soundness_score,
        writing_score=result.writing_score,
        strengths=json.dumps(result.strengths, ensure_ascii=False),
        weaknesses=json.dumps(result.weaknesses, ensure_ascii=False),
        detailed_comments=result.detailed_comments,
        suggestions=result.suggestions,
        reviewed_at=datetime.utcnow(),
        raw_response=raw,
        is_guest=is_guest,
        guest_reviewer_id=guest_reviewer_id,
        guest_level=guest_level,
    )


async def run_review_pipeline(paper: Paper, db: AsyncSession):
    """
    完整审稿流程：
    1. 更新论文状态
    2. 并行调用内置审稿人
    3. 并行调用社区审稿人
    4. 保存所有审稿结果
    5. AI主编综合意见做最终决定
    6. 更新论文状态 + 发送通知
    """
    # 1. 更新状态
    paper.status = "under_review"
    await db.commit()

    # 2. 并行审稿 — 内置审稿人
    builtin_reviewers = get_active_reviewers()
    if not builtin_reviewers:
        logger.error("No reviewers available! Check API keys.")
        paper.status = "submitted"
        await db.commit()
        return

    builtin_tasks = [
        _run_single_review(r, paper.title, paper.abstract, paper.keywords, paper.content_text, authors=paper.authors)
        for r in builtin_reviewers
    ]
    builtin_results = await asyncio.gather(*builtin_tasks)

    # 3. 并行审稿 — 社区审稿人
    guest_reviewers_db = await select_guest_reviewers(paper.keywords or "", paper.id, db)
    guest_results = []
    if guest_reviewers_db:
        guest_runners = [build_guest_runner(gr) for gr in guest_reviewers_db]
        guest_tasks = [
            _run_single_review(r, paper.title, paper.abstract, paper.keywords, paper.content_text, authors=paper.authors)
            for r in guest_runners
        ]
        guest_results = await asyncio.gather(*guest_tasks, return_exceptions=True)

    # 4. 保存内置审稿人结果
    editor_reviews: list[tuple[str, ReviewResult]] = []
    for name, provider, result, raw in builtin_results:
        review = _save_review_record(paper.id, name, provider, result, raw)
        db.add(review)
        editor_reviews.append((name, result))

    # 5. 保存社区审稿人结果
    for i, gr_db in enumerate(guest_reviewers_db):
        gr_result = guest_results[i]

        # 异常处理
        if isinstance(gr_result, Exception):
            logger.error(f"Guest reviewer {gr_db.display_name} failed: {gr_result}")
            gr_db.consecutive_errors += 1
            # 记录失败的 GuestReviewRecord
            db.add(GuestReviewRecord(
                guest_reviewer_id=gr_db.id,
                paper_id=paper.id,
                format_valid=0,
                score_reasonable=0,
                comment_length=0,
                sent_to_editor=0,
            ))
            continue

        name, provider, result, raw = gr_result

        # 格式验证
        format_errors = validate_review_format(result)
        format_ok = len(format_errors) == 0
        reasonable = _scores_reasonable(result)

        # 构建审稿人显示名
        level_tag = "Associate" if gr_db.level == 2 else "Candidate"
        display_name = f"{gr_db.display_name} [{level_tag}]"

        review = _save_review_record(
            paper.id, display_name, provider, result, raw,
            is_guest=1, guest_reviewer_id=gr_db.id, guest_level=gr_db.level,
        )
        db.add(review)
        await db.flush()  # 获取 review.id

        # 质量追踪记录
        sent_to_editor = 1 if (gr_db.level == 2 and format_ok) else 0
        db.add(GuestReviewRecord(
            guest_reviewer_id=gr_db.id,
            review_id=review.id,
            paper_id=paper.id,
            format_valid=1 if format_ok else 0,
            score_reasonable=1 if reasonable else 0,
            comment_length=len(result.detailed_comments),
            sent_to_editor=sent_to_editor,
        ))

        # 更新连续错误计数
        if format_ok:
            gr_db.consecutive_errors = 0
            gr_db.last_active_at = datetime.utcnow()
        else:
            gr_db.consecutive_errors += 1

        # 仅 Associate + 格式合格 → 送入主编
        if gr_db.level == 2 and format_ok:
            editor_reviews.append((f"[Associate Reviewer] {gr_db.display_name}", result))

    await db.commit()

    # 6. 升级/降级检查
    for gr_db in guest_reviewers_db:
        await check_promotion_demotion(gr_db, db)

    # 7. AI主编做决定
    try:
        editor = AIEditor()
        final_decision, decision_letter = await editor.make_decision(
            paper.title, paper.abstract, editor_reviews
        )
    except Exception as e:
        logger.error(f"Editor decision failed: {e}")
        final_decision = "major_revision"
        decision_letter = f"Editorial decision could not be generated due to an error: {e}"

    ed = EditorialDecision(
        paper_id=paper.id,
        final_decision=final_decision,
        decision_letter=decision_letter,
        editor_model="claude-editor",
        decided_at=datetime.utcnow(),
    )
    db.add(ed)

    # 8. 更新论文状态
    status_map = {
        "accept": "accepted",
        "minor_revision": "revision",
        "major_revision": "revision",
        "reject": "rejected",
    }
    paper.status = status_map.get(final_decision, "revision")
    paper.decided_at = datetime.utcnow()
    await db.commit()

    logger.info(f"Paper #{paper.id} '{paper.title}' — decision: {final_decision}")

    # 9. 发送邮件通知作者
    if paper.email:
        try:
            send_decision_email(paper.email, paper.id, paper.title, final_decision)
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
