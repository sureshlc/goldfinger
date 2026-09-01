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


class BOMFormulaDB(Base):
    """Cached BOM 'formula' metadata for one assembly item (keyed by NetSuite internal id).

    The recipe (direct components) lives in bom_component. Keyed by item id, NOT sku, so it is
    unaffected by duplicate SKUs (e.g. an Assembly + InvtPart sharing one itemid).
    """
    __tablename__ = "bom_formula"

    assembly_item_id = Column(BigInteger, primary_key=True, autoincrement=False)  # NetSuite internal id
    revision_id = Column(String(64), nullable=True)          # current bomRevision id (native); null for legacy
    source = Column(String(16), nullable=False)              # 'legacy' | 'native'
    has_bom = Column(Boolean, nullable=False, default=False) # False => no BOM (negative cache)
    refreshed_at = Column(DateTime(timezone=True), server_default=func.now())
    last_error = Column(String(512), nullable=True)

    components = relationship(
        "BOMComponentDB", back_populates="formula", cascade="all, delete-orphan"
    )


class BOMComponentDB(Base):
    """One direct child of an assembly's BOM (its recipe, a single level)."""
    __tablename__ = "bom_component"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    assembly_item_id = Column(
        BigInteger,
        ForeignKey("bom_formula.assembly_item_id", ondelete="CASCADE"),
        nullable=False,
    )
    component_item_id = Column(BigInteger, nullable=False)
    component_sku = Column(String(255), nullable=False)
    component_name = Column(String(512), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(32), nullable=True)
    is_phantom = Column(Boolean, nullable=False, default=False)
    is_manufacturing = Column(Boolean, nullable=False, default=False)
    bom_id = Column(String(64), nullable=True)               # NetSuite BOM record id (kept for response parity)
    ordinal = Column(Integer, nullable=False, default=0)

    formula = relationship("BOMFormulaDB", back_populates="components")

    __table_args__ = (
        Index("ix_bom_component_assembly", "assembly_item_id"),
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
    source = Column(String(20), nullable=True)  # 'UI' (web/JWT) or 'REST' (API key)

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


class APIKeyDB(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(512), unique=True, nullable=False)
    key_prefix = Column(String(12), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    creator = relationship("UserDB")

    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
    )
