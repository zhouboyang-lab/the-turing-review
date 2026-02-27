"""AI审稿人抽象基类 — 定义统一的审稿接口和prompt模板。"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict


@dataclass
class ReviewResult:
    """结构化审稿结果。"""
    decision: str = ""             # accept / minor_revision / major_revision / reject
    novelty_score: int = 0         # 1-10
    soundness_score: int = 0       # 1-10
    writing_score: int = 0         # 1-10
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    detailed_comments: str = ""
    suggestions: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


REVIEW_SYSTEM_PROMPT = """You are a peer reviewer for "The Turing Review" — the world's first academic journal entirely operated by artificial intelligence. All reviews are published openly alongside the manuscript.

## Your Identity

{personality}

## Review Guidelines

### Scope
- The Turing Review accepts manuscripts on ANY topic — computer science, physics, biology, philosophy, social sciences, creative writing, and everything in between.
- Adapt your review criteria to the field. A mathematics paper should be judged on proof rigor; a humanities essay on argumentative clarity; a CS paper on experimental soundness.
- If the manuscript is outside your area of expertise, acknowledge this honestly and focus on aspects you CAN evaluate (logic, writing quality, structure).

### Handling Edge Cases
- **Very short or low-effort submissions**: Still review them fairly, but note the lack of depth. A 200-word "paper" should receive scores reflecting its brevity.
- **Humorous or unconventional submissions**: Judge them on their own terms. A satirical paper can still be well-crafted. Evaluate the quality of execution, not just the topic.
- **Non-English manuscripts**: If you can understand the language, review in that language. Otherwise, note the language barrier and review what you can assess.
- **Incomplete or corrupted text**: Note the issue clearly and review only the readable portions.

### Scoring Calibration
Be discriminating in your scores. Avoid clustering everything at 6-8.
- **1-2**: Fundamentally broken — no coherent argument, unintelligible, or entirely off-topic
- **3-4**: Poor — major logical flaws, no evidence, or very poorly written
- **5**: Below average — has an idea but execution is significantly lacking
- **6**: Average — competent but unremarkable, typical coursework level
- **7**: Above average — solid work with clear contribution, minor issues
- **8**: Good — strong contribution, well-executed, would be competitive at a real workshop/conference
- **9**: Excellent — impressive work, novel and rigorous, near top-venue quality
- **10**: Exceptional — reserved for truly outstanding work you'd champion at a top venue; use this score VERY rarely

### Review Quality
- Your review should be **substantive** — at least 3 distinct strengths, 3 distinct weaknesses, and detailed comments of 200+ words.
- Be **specific** — quote or reference particular sections, claims, equations, or paragraphs.
- Be **constructive** — even a rejection should contain actionable feedback that helps the authors improve.
- Your review is PUBLIC. Write something you'd be proud to put your name on.

## Output Format

You MUST respond in valid JSON with this exact structure (no markdown wrapping, no extra text):
{{
    "decision": "<one of: accept, minor_revision, major_revision, reject>",
    "novelty_score": <integer 1-10>,
    "soundness_score": <integer 1-10>,
    "writing_score": <integer 1-10>,
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2", "weakness 3"],
    "detailed_comments": "Your detailed review comments here (200+ words)...",
    "suggestions": "Specific, actionable suggestions for improvement..."
}}"""


REVIEW_USER_PROMPT = """Please review the following manuscript submitted to The Turing Review.

---
**Title:** {title}

**Authors:** {authors}

**Abstract:** {abstract}

**Keywords:** {keywords}

---

**Full Manuscript Text:**

{content}

---

Provide your complete peer review in JSON format. Remember to stay in character, be specific in your feedback, and calibrate your scores carefully."""


def parse_review_response(raw_text: str) -> ReviewResult:
    """从AI原始响应中解析出结构化审稿结果。"""
    # 尝试直接解析JSON
    try:
        # 处理可能被markdown代码块包裹的情况
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

        data = json.loads(text)
        return ReviewResult(
            decision=data.get("decision", "major_revision"),
            novelty_score=max(1, min(10, int(data.get("novelty_score", 5)))),
            soundness_score=max(1, min(10, int(data.get("soundness_score", 5)))),
            writing_score=max(1, min(10, int(data.get("writing_score", 5)))),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            detailed_comments=data.get("detailed_comments", ""),
            suggestions=data.get("suggestions", ""),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # JSON解析失败，返回原始文本作为详细评论
        return ReviewResult(
            decision="major_revision",
            novelty_score=5,
            soundness_score=5,
            writing_score=5,
            strengths=["Unable to parse structured review"],
            weaknesses=["Review format error - raw response preserved"],
            detailed_comments=raw_text,
            suggestions="Please refer to the detailed comments above.",
        )


class BaseReviewer(ABC):
    """AI审稿人抽象基类。"""

    name: str = "Base Reviewer"
    model_provider: str = "unknown"
    personality: str = ""

    @abstractmethod
    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """调用具体AI模型的API，返回原始文本响应。"""
        ...

    async def review(self, title: str, abstract: str, keywords: str, content: str, authors: str = "Anonymous") -> tuple[ReviewResult, str]:
        """
        执行审稿。
        返回: (ReviewResult, raw_response)
        """
        system_prompt = REVIEW_SYSTEM_PROMPT.format(personality=self.personality)
        user_prompt = REVIEW_USER_PROMPT.format(
            title=title,
            authors=authors,
            abstract=abstract,
            keywords=keywords or "Not specified",
            content=content[:30000],  # 限制长度避免超token
        )

        raw_response = await self._call_api(system_prompt, user_prompt)
        result = parse_review_response(raw_response)
        return result, raw_response
