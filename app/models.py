from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    abstract = Column(Text, nullable=False)
    authors = Column(String(500), default="Anonymous")
    email = Column(String(200), default="")
    keywords = Column(String(500), default="")
    file_path = Column(String(500), default="")
    content_text = Column(Text, default="")
    status = Column(String(50), default="submitted")  # submitted/under_review/accepted/revision/rejected
    publication_number = Column(Integer, nullable=True, unique=True)  # 仅 accepted 时分配，作为 TR-xxxx 发表编号
    submitted_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)

    reviews = relationship("Review", back_populates="paper", lazy="selectin")
    editorial_decision = relationship("EditorialDecision", back_populates="paper", uselist=False, lazy="selectin")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    reviewer_name = Column(String(100), nullable=False)
    model_provider = Column(String(50), nullable=False)  # claude/openai/deepseek
    decision = Column(String(50), default="")  # accept/minor_revision/major_revision/reject
    novelty_score = Column(Integer, default=0)
    soundness_score = Column(Integer, default=0)
    writing_score = Column(Integer, default=0)
    strengths = Column(Text, default="[]")  # JSON list
    weaknesses = Column(Text, default="[]")  # JSON list
    detailed_comments = Column(Text, default="")
    suggestions = Column(Text, default="")
    reviewed_at = Column(DateTime, default=datetime.utcnow)
    raw_response = Column(Text, default="")

    # 社区审稿人关联
    is_guest = Column(Integer, default=0)  # 0=内置审稿人, 1=社区审稿人
    guest_reviewer_id = Column(Integer, ForeignKey("guest_reviewers.id"), nullable=True)
    guest_level = Column(Integer, nullable=True)  # 审稿时的等级快照: 1=Candidate, 2=Associate

    paper = relationship("Paper", back_populates="reviews")


class EditorialDecision(Base):
    __tablename__ = "editorial_decisions"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False, unique=True)
    final_decision = Column(String(50), nullable=False)
    decision_letter = Column(Text, default="")
    editor_model = Column(String(100), default="")
    decided_at = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="editorial_decision")


class GuestReviewer(Base):
    """社区审稿人注册信息。"""
    __tablename__ = "guest_reviewers"

    id = Column(Integer, primary_key=True, index=True)

    # 基本信息
    display_name = Column(String(100), nullable=False, unique=True)
    email = Column(String(200), nullable=False, unique=True)
    personality = Column(Text, default="")
    expertise_areas = Column(String(500), default="")  # 逗号分隔关键词

    # 注册模式: "prompt" 或 "api"
    mode = Column(String(20), nullable=False)

    # Prompt 模式字段
    backend_model = Column(String(20), default="")  # claude / openai / deepseek

    # API 模式字段
    api_base_url = Column(String(500), default="")
    api_key_encrypted = Column(String(500), default="")
    api_model_name = Column(String(200), default="")

    # 等级系统: 0=Applicant, 1=Candidate, 2=Associate
    level = Column(Integer, default=0)
    is_active = Column(Integer, default=1)
    consecutive_errors = Column(Integer, default=0)
    last_active_at = Column(DateTime, nullable=True)
    registered_at = Column(DateTime, default=datetime.utcnow)

    # 校准测试
    calibration_passed = Column(Integer, default=0)
    calibration_error = Column(Text, default="")

    review_records = relationship("GuestReviewRecord", back_populates="reviewer", lazy="selectin")


class GuestReviewRecord(Base):
    """社区审稿质量追踪记录。"""
    __tablename__ = "guest_review_records"

    id = Column(Integer, primary_key=True, index=True)
    guest_reviewer_id = Column(Integer, ForeignKey("guest_reviewers.id"), nullable=False)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)

    # 质量指标
    format_valid = Column(Integer, default=0)
    score_reasonable = Column(Integer, default=0)
    comment_length = Column(Integer, default=0)
    sent_to_editor = Column(Integer, default=0)  # 1=已送达主编（仅 Associate）

    created_at = Column(DateTime, default=datetime.utcnow)

    reviewer = relationship("GuestReviewer", back_populates="review_records")
