"""
SQLAlchemy ORM Models for PostgreSQL tables.
"""
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, Float, DateTime, Text,
    ForeignKey, Index, func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=False)
    hashed_password = Column(String(512), nullable=False)
    role = Column(String(50), nullable=False, default="user")
    disabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    sessions = relationship("SessionDB", back_populates="user")
    request_logs = relationship("RequestLogDB", back_populates="user")


class ItemDB(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=False)  # NetSuite internal ID
    sku = Column(String(255), nullable=False)
    name = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_items_sku", "sku", unique=True),
    )


class SessionDB(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    login_time = Column(DateTime(timezone=True), server_default=func.now())
    logout_time = Column(DateTime(timezone=True), nullable=True)
    session_duration_mins = Column(Float, nullable=True)
    total_requests = Column(Integer, default=0)
    status = Column(String(50), default="active")

    user = relationship("UserDB", back_populates="sessions")


class RequestLogDB(Base):
    __tablename__ = "request_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    request_id = Column(String(255), nullable=True)
    session_id = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    item_sku = Column(String(255), nullable=True, index=True)
    desired_quantity = Column(String(50), nullable=True)
    max_producible = Column(String(50), nullable=True)
    can_produce = Column(String(50), nullable=True)
    limiting_component = Column(Text, nullable=True)
    shortages_count = Column(String(50), nullable=True)
    response_time_ms = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    error_type = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    cache_hit = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)

    user = relationship("UserDB", back_populates="request_logs")

    __table_args__ = (
        Index("ix_request_logs_timestamp", "timestamp"),
        Index("ix_request_logs_user_id", "user_id"),
    )


class AuditEventDB(Base):
    __tablename__ = "audit_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)

    user = relationship("UserDB")

    __table_args__ = (
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_action", "action"),
    )
