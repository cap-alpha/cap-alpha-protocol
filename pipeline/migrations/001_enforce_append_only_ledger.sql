-- Migration: 001_enforce_append_only_ledger
-- Description: Establishes Regulatory-Grade RBAC for the Cryptographic Ledger

-- 1. Create Dedicated Roles
-- These must be run by an Admin on the MotherDuck cloud console.
CREATE ROLE IF NOT EXISTS ledger_writer_role;
CREATE ROLE IF NOT EXISTS application_read_role;

-- 2. Revoke Implicit Write Access
-- By default, MotherDuck/DuckDB might allow public inserts on newly created tables depending on schema grants.
REVOKE ALL PRIVILEGES ON TABLE gold_layer.audit_ledger_entries FROM PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE gold_layer.audit_ledger_blocks FROM PUBLIC;

-- 3. Grant Read-Only Application Access
-- The frontend / web app uses a token assigned to this role.
GRANT SELECT ON TABLE gold_layer.audit_ledger_entries TO application_read_role;
GRANT SELECT ON TABLE gold_layer.audit_ledger_blocks TO application_read_role;

-- 4. Grant Append-Only Pipeline Access
-- The ML Flywheel uses a token assigned to this role.
-- Note: We explicitly DO NOT grant UPDATE or DELETE.
GRANT SELECT, INSERT ON TABLE gold_layer.audit_ledger_entries TO ledger_writer_role;
GRANT SELECT, INSERT ON TABLE gold_layer.audit_ledger_blocks TO ledger_writer_role;

-- Verification
-- Any attempt by ledger_writer_role to run `UPDATE gold_layer.audit_ledger_entries` 
-- will result in a Permission Denied error, enforcing cryptographic append-only immutability.
