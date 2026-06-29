import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.refrigerator import Refrigerator


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    household_memberships = relationship("HouseholdMember", foreign_keys="HouseholdMember.user_id", back_populates="user")


class Household(Base):
    __tablename__ = "households"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    owner = relationship("User")
    members = relationship("HouseholdMember", back_populates="household", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="household", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="household", cascade="all, delete-orphan")
    refrigerators = relationship("Refrigerator", back_populates="household", cascade="all, delete-orphan")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("owner", "admin", "member", "viewer", name="household_role"), nullable=False, default="member")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    household = relationship("Household", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="household_memberships")
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    inviter = relationship("User", foreign_keys=[invited_by])
    status = Column(String(20), nullable=False, default="active")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(Enum("refrigerator", "freezer", "pantry", "other", name="zone_type"), nullable=False, default="other")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    household = relationship("Household", back_populates="zones")
    inventory_items = relationship("InventoryItem", back_populates="zone", cascade="all, delete-orphan")
    refrigerator_id = Column(UUID(as_uuid=True), ForeignKey("refrigerators.id", ondelete="SET NULL"), nullable=True)
    refrigerator = relationship("Refrigerator")


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=True)
    barcode = Column(String(100), nullable=True, index=True)
    default_unit = Column(String(50), nullable=True)
    image_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    low_stock_threshold = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    household = relationship("Household", back_populates="products")
    inventory_items = relationship("InventoryItem", back_populates="product", cascade="all, delete-orphan")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False, default=1)
    unit = Column(String(50), nullable=True)
    purchase_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)
    opened_date = Column(Date, nullable=True)
    status = Column(Enum("active", "consumed", "discarded", "archived", name="item_status"), nullable=False, default="active")
    priority_score = Column(Numeric(6, 2), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    product = relationship("Product", back_populates="inventory_items")
    zone = relationship("Zone", back_populates="inventory_items")
    alerts = relationship("Alert", back_populates="inventory_item", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=True)
    type = Column(Enum("expiring_today", "expiring_soon", "expired", "low_stock", name="alert_type"), nullable=False)
    severity = Column(Enum("info", "warning", "critical", name="alert_severity"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    priority_score = Column(Numeric(6, 2), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    inventory_item = relationship("InventoryItem", back_populates="alerts")


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String(50), nullable=True)
    checked = Column(Boolean, nullable=False, default=False)
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(Enum("product", "inventory_item", "zone", "household", "shopping_item", "alert", "refrigerator", name="entity_type"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    extra_data = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    actor = relationship("User", foreign_keys=[actor_user_id])


class TokenBlacklist(Base):
    """Server-side JWT revocation list (RF-AUT-004).

    Each row is a revoked JWT identified by its `jti` (UUID minted at token
    creation). `expires_at` mirrors the JWT's `exp` claim so the row can be
    safely dropped once the token would have expired anyway. All read queries
    filter on `expires_at > now()` so old rows never match a live check.
    """
    __tablename__ = "token_blacklist"

    jti = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reason = Column(String(50), nullable=True)  # "logout", "admin_revoke", etc.
