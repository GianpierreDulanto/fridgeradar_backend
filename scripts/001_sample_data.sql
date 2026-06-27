-- Seed data for local development
-- Run after migrations: psql -d fridge_inventory -f db/seeds/001_sample_data.sql

INSERT INTO users (id, email, password_hash, full_name) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'alice@example.com', '$2b$12$LJ3m4ys3Lk0TSwHnbfOMiOXPm1Qlq8n5HKhq3X7qG5pYK8x8vz5Kq', 'Alice Johnson');

INSERT INTO households (id, name, timezone, owner_user_id) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'Casa de Alice', 'America/Mexico_City', 'a0000000-0000-0000-0000-000000000001');

INSERT INTO household_members (household_id, user_id, role) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'owner');

INSERT INTO zones (id, household_id, name, type, sort_order) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'Refrigerator', 'refrigerator', 1),
    ('c0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000001', 'Freezer', 'freezer', 2),
    ('c0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000001', 'Pantry', 'pantry', 3);

INSERT INTO products (id, household_id, name, category, default_unit) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'Whole Milk', 'Dairy', 'liter'),
    ('d0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000001', 'Eggs', 'Dairy', 'piece'),
    ('d0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000001', 'Chicken Breast', 'Meat', 'kg');

INSERT INTO inventory_items (id, household_id, product_id, zone_id, quantity, unit, purchase_date, expiry_date, status) VALUES
    ('e0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 2, 'liter', '2026-06-18', '2026-06-25', 'active'),
    ('e0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000001', 12, 'piece', '2026-06-19', '2026-07-03', 'active'),
    ('e0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000002', 0.5, 'kg', '2026-06-15', '2026-06-22', 'active');
