import os
import sqlite3
from pathlib import Path
from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('patient','doctor','diagnostic','insurance')),
    full_name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patients (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    patient_code TEXT NOT NULL UNIQUE,
    date_of_birth TEXT DEFAULT '',
    gender TEXT DEFAULT '',
    address TEXT DEFAULT '',
    emergency_contact TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS doctors (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    specialization TEXT DEFAULT '',
    registration_number TEXT DEFAULT '',
    workplace TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS diagnostic_centers (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    center_name TEXT DEFAULT '',
    address TEXT DEFAULT '',
    license_number TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS insurance_providers (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT DEFAULT '',
    address TEXT DEFAULT '',
    support_phone TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS doctor_patient_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doctor_id, patient_id)
);

CREATE TABLE IF NOT EXISTS medical_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    stored_name TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    diagnosis TEXT NOT NULL,
    treatment_notes TEXT DEFAULT '',
    medication_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS diagnostic_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    center_id INTEGER NOT NULL REFERENCES users(id),
    test_name TEXT NOT NULL,
    test_date TEXT DEFAULT '',
    findings TEXT DEFAULT '',
    record_id INTEGER REFERENCES medical_records(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS insurance_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES users(id),
    policy_number TEXT NOT NULL,
    coverage_details TEXT DEFAULT '',
    valid_until TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_id, policy_number)
);

CREATE TABLE IF NOT EXISTS insurance_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_ref TEXT NOT NULL UNIQUE,
    patient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES users(id),
    policy_number TEXT NOT NULL,
    claim_amount REAL NOT NULL CHECK(claim_amount > 0),
    hospital_name TEXT NOT NULL,
    treatment_details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Submitted'
        CHECK(status IN ('Submitted','Under Review','Approved','Rejected')),
    remarks TEXT DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id),
    submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claim_documents (
    claim_id INTEGER NOT NULL REFERENCES insurance_claims(id) ON DELETE CASCADE,
    record_id INTEGER NOT NULL REFERENCES medical_records(id) ON DELETE CASCADE,
    PRIMARY KEY(claim_id, record_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_records_patient ON medical_records(patient_id);
CREATE INDEX IF NOT EXISTS idx_claims_patient ON insurance_claims(patient_id);
CREATE INDEX IF NOT EXISTS idx_claims_provider ON insurance_claims(provider_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
"""

def get_db():
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()

def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
