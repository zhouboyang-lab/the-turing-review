"""邮件通知服务 — 审稿完成后通知作者。"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SITE_URL

logger = logging.getLogger(__name__)

DECISION_LABELS = {
    "accept": "Accepted",
    "minor_revision": "Minor Revision Required",
    "major_revision": "Major Revision Required",
    "reject": "Rejected",
}


def send_decision_email(to_email: str, paper_id: int, paper_title: str, final_decision: str):
    """审稿完成后发送结果通知邮件给作者。"""
    if not to_email or not SMTP_USER:
        logger.info(f"Skipping email: to={to_email}, smtp_user={bool(SMTP_USER)}")
        return

    decision_label = DECISION_LABELS.get(final_decision, final_decision)
    paper_url = f"{SITE_URL}/paper/{paper_id}"

    subject = f"[The Turing Review] Editorial Decision: {paper_title}"

    html_body = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #243b53;">
        <div style="background: #102a43; padding: 24px; text-align: center;">
            <h1 style="color: #f6ad55; margin: 0; font-size: 22px;">The Turing Review</h1>
            <p style="color: #9fb3c8; margin: 4px 0 0; font-size: 12px;">An AI-Operated Academic Journal</p>
        </div>

        <div style="padding: 32px 24px;">
            <p>Dear Author,</p>

            <p>The AI editorial board of <strong>The Turing Review</strong> has completed
            the peer review of your manuscript:</p>

            <div style="background: #f0f4f8; border-left: 4px solid #f6ad55; padding: 16px; margin: 20px 0;">
                <strong>{paper_title}</strong>
            </div>

            <p>Our editorial decision is: <strong style="font-size: 18px;">{decision_label}</strong></p>

            <p>Three independent AI reviewers have evaluated your work, and the AI Editor-in-Chief
            has synthesized their opinions into a final decision. You can view the full reviews,
            scores, and editorial decision letter at:</p>

            <p style="text-align: center; margin: 24px 0;">
                <a href="{paper_url}"
                   style="background: #f6ad55; color: #102a43; padding: 12px 32px;
                          text-decoration: none; border-radius: 8px; font-weight: bold;">
                    View Full Review
                </a>
            </p>

            <p style="color: #627d98; font-size: 13px;">
                All reviews at The Turing Review are conducted entirely by artificial intelligence.
                No humans were involved in the editorial process.
            </p>
        </div>

        <div style="background: #243b53; color: #9fb3c8; padding: 16px; text-align: center; font-size: 12px;">
            The Turing Review &mdash; An AI Experiment
        </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        logger.info(f"Decision email sent to {to_email} for paper #{paper_id}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
