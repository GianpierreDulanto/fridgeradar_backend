-- Initial Schema for Fridge Inventory App
-- Based on domain model defined in 00-master-brief.md Section 12

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- Households
CREATE TABLE households (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    owner_user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_households_owner ON households(owner_user_id);

-- Household members (join table with role)
CREATE TYPE household_role AS ENUM ('owner', 'admin', 'member', 'viewer');

CREATE TABLE household_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role household_role NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(household_id, user_id)
);

CREATE INDEX idx_hm_household ON household_members(household_id);
CREATE INDEX idx_hm_user ON household_members(user_id);

-- Zones (storage areas like fridge, freezer, pantry)
CREATE TYPE zone_type AS ENUM ('refrigerator', 'freezer', 'pantry', 'other');

CREATE TABLE zones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type zone_type NOT NULL DEFAULT 'other',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_zones_household ON zones(household_id);

-- Products (canonical product definitions)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    barcode VARCHAR(100),
    default_unit VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_products_household ON products(household_id);
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_barcode ON products(barcode);

-- Inventory items (physical stored quantity)
CREATE TYPE item_status AS ENUM ('active', 'consumed', 'discarded', 'archived');

CREATE TABLE inventory_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    zone_id UUID NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1,
    unit VARCHAR(50),
    purchase_date DATE,
    expiry_date DATE,
    opened_date DATE,
    status item_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inventory_household ON inventory_items(household_id);
CREATE INDEX idx_inventory_product ON inventory_items(product_id);
CREATE INDEX idx_inventory_zone ON inventory_items(zone_id);
CREATE INDEX idx_inventory_expiry ON inventory_items(expiry_date);
CREATE INDEX idx_inventory_status ON inventory_items(status);

-- Alerts
CREATE TYPE alert_type AS ENUM ('expiring_today', 'expiring_soon', 'expired', 'low_stock');
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    inventory_item_id UUID REFERENCES inventory_items(id) ON DELETE CASCADE,
    type alert_type NOT NULL,
    severity alert_severity NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    due_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_household ON alerts(household_id);
CREATE INDEX idx_alerts_item ON alerts(inventory_item_id);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_due ON alerts(due_at);

-- Shopping list items
CREATE TABLE shopping_list_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    quantity DECIMAL(10,2),
    unit VARCHAR(50),
    checked BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shopping_household ON shopping_list_items(household_id);

-- Activity log
CREATE TYPE entity_type AS ENUM ('product', 'inventory_item', 'zone', 'household', 'shopping_item', 'alert');

CREATE TABLE activity_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_type entity_type NOT NULL,
    entity_id UUID,
    action VARCHAR(100) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_activity_household ON activity_log(household_id);
CREATE INDEX idx_activity_actor ON activity_log(actor_user_id);
CREATE INDEX idx_activity_created ON activity_log(created_at DESC);
CREATE INDEX idx_activity_entity ON activity_log(entity_type, entity_id);
