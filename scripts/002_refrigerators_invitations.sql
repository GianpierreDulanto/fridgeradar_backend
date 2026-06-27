-- Refrigerators (physical appliances)
CREATE TABLE refrigerators (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(20) NOT NULL DEFAULT 'other' CHECK (type IN ('refrigerator', 'freezer', 'pantry', 'other')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refrigerators_household ON refrigerators(household_id);

-- Add refrigerator_id to zones (nullable, zones become compartments)
ALTER TABLE zones ADD COLUMN refrigerator_id UUID REFERENCES refrigerators(id) ON DELETE SET NULL;

-- Add invitation status to household_members
ALTER TABLE household_members ADD COLUMN invited_by UUID REFERENCES users(id);
ALTER TABLE household_members ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('pending', 'active', 'rejected'));

-- Add refrigerator to entity_type enum
ALTER TYPE entity_type ADD VALUE 'refrigerator';
