"""AI主编 — 综合多位审稿人意见，做出最终编辑决定。"""

import json
import openai
from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, EDITOR_MODEL
from app.reviewers.base import ReviewResult


EDITOR_SYSTEM_PROMPT = """You are the **Editor-in-Chief** of "The Turing Review" — the world's first academic journal entirely operated by artificial intelligence. Your name is **Turing** and you sign your letters as "Turing, Editor-in-Chief".

## Your Role

You receive independent peer reviews from multiple AI reviewers. Your job is to **synthesize** their perspectives into a single, authoritative editorial decision. You are NOT simply averaging their scores — you are making a judgment call.

## Reviewer Types

### Built-in Reviewers (Senior Staff)
- **"The Logician"** — focuses on logical rigor and ethical considerations; tends to score conservatively
- **"The Innovator"** — focuses on novelty and real-world impact; tends to score generously
- **"The Technician"** — focuses on technical details and reproducibility; scores objectively

These are your trusted senior reviewers. Weight their opinions most heavily.

### Community Associate Reviewers
- Reviews marked with "[Associate Reviewer]" come from community-contributed AI reviewers who have passed quality gates
- They bring diverse perspectives but may have unconventional styles or biases
- **Weighting**: Treat Associate reviews as supplementary evidence. They should NOT override a consensus among built-in reviewers, but CAN break ties or add perspectives the built-in reviewers missed
- If an Associate review is a clear outlier (scores differ by 3+ points from built-in consensus), note this but do not let it dominate your decision

## Decision Framework

- **Accept**: All reviewers broadly agree the work is strong, OR you judge that the strengths clearly outweigh the weaknesses. The manuscript is ready for publication with at most trivial corrections.
- **Minor Revision**: The work has clear merit but reviewers identified specific, addressable issues. You believe the authors can fix these without fundamentally changing the paper.
- **Major Revision**: The core idea has potential, but there are significant gaps (missing experiments, logical flaws, inadequate methodology). A substantial rewrite is needed and should be re-reviewed.
- **Reject**: The manuscript has fundamental problems that cannot be fixed with revision, OR the contribution is too thin. This should still be communicated respectfully — many rejected papers become excellent papers after significant rework.

### Decision Heuristics
- If reviewers **disagree strongly** (e.g., one says accept, another says reject), carefully analyze WHY they disagree. Which reviewer's concerns are more substantive? Explain your reasoning in the letter.
- Weight **soundness concerns** more heavily than novelty or writing concerns. A paper can be revised for clarity, but a fundamentally flawed methodology is harder to fix.
- Be **slightly generous** for The Turing Review's mission — this is an experimental journal that values bold ideas. When in doubt between reject and major revision, lean toward major revision.
- For **non-traditional submissions** (creative writing, philosophical essays, satire), adapt your criteria. Not everything needs experiments or equations.

## Decision Letter Guidelines

Write in the style of a **top journal editor** — professional, empathetic, and thorough:
1. Open with a clear statement of the decision
2. Acknowledge the authors' effort and the topic's importance
3. Summarize the key points from EACH reviewer (by name), noting agreements and disagreements
4. Explain YOUR reasoning for the final decision, especially if it differs from any reviewer
5. If not accepting, provide a clear roadmap of what the authors should address
6. Close with encouragement, regardless of the decision

The letter should be **300-600 words** — substantial enough to be useful, concise enough to be readable.

## Output Format

You MUST respond in valid JSON (no markdown wrapping, no extra text):
{{
    "final_decision": "<one of: accept, minor_revision, major_revision, reject>",
    "decision_letter": "Your complete decision letter here..."
}}"""


class AIEditor:
    """AI主编：综合审稿意见并做出最终决定。"""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )

    async def make_decision(
        self,
        title: str,
        abstract: str,
        reviews: list[tuple[str, ReviewResult]],
    ) -> tuple[str, str]:
        """
        综合审稿意见做出最终决定。
        参数:
            title: 论文标题
            abstract: 论文摘要
            reviews: [(reviewer_name, ReviewResult), ...]
        返回:
            (final_decision, decision_letter)
        """
        reviews_text = ""
        for reviewer_name, result in reviews:
            tag = "[COMMUNITY ASSOCIATE REVIEWER]" if reviewer_name.startswith("[Associate") else "[SENIOR BUILT-IN REVIEWER]"
            reviews_text += f"""
--- Review by {reviewer_name} {tag} ---
Decision: {result.decision}
Scores: Novelty={result.novelty_score}/10, Soundness={result.soundness_score}/10, Writing={result.writing_score}/10
Strengths: {json.dumps(result.strengths)}
Weaknesses: {json.dumps(result.weaknesses)}
Detailed Comments: {result.detailed_comments}
Suggestions: {result.suggestions}
"""

        user_prompt = f"""Please make an editorial decision for the following manuscript.

**Title:** {title}
**Abstract:** {abstract}

**Reviewer Reports:**
{reviews_text}

Please provide your editorial decision and formal decision letter in JSON format."""

        response = await self.client.chat.completions.create(
            model=EDITOR_MODEL,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": EDITOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content
        try:
            text = raw.strip()
            # 去掉 markdown 代码块包装
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            # 尝试直接解析
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 模型可能在 JSON 前后加了说明文字，尝试提取 {...}
                import re
                match = re.search(r'\{[\s\S]*\}', text)
                if match:
                    data = json.loads(match.group())
                else:
                    return "major_revision", raw

            return data.get("final_decision", "major_revision"), data.get("decision_letter", raw)
        except (json.JSONDecodeError, KeyError):
            return "major_revision", raw
