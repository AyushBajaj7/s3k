"""
Database schema, initialization, seed data, and cryptographic hash chaining
FlowSync / BuyOps AI - S3K Case Study 03
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
import sys

# Support relative and module execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from backend.auth import hash_password
except ImportError:
    from auth import hash_password

DB_PATH = Path(__file__).parent / "flowsync.db"
GENESIS_HASH = "0" * 64

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")

    # 1. Users table with real credentials & RBAC
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL,          -- 'requester', 'manager', 'finance', 'depthead'
        department TEXT NOT NULL,
        budget_limit REAL DEFAULT 0.0,
        password_hash TEXT NOT NULL
    );
    """)

    # 2. Purchase requests table with invoice_sha256
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_requests (
        id TEXT PRIMARY KEY,
        requester_id TEXT NOT NULL,
        requester_name TEXT NOT NULL,
        department TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        vendor TEXT NOT NULL,
        amount REAL NOT NULL,
        business_justification TEXT NOT NULL,
        tier TEXT NOT NULL,          -- Tier 1 (<= 25000), Tier 2 (25001-100000), Tier 3 (> 100000)
        status TEXT NOT NULL,        -- 'PENDING_MANAGER', 'PENDING_FINANCE', 'PENDING_DEPTHEAD', 'APPROVED', 'REJECTED', 'FLAGGED_MISSING_DOCS'
        priority TEXT DEFAULT 'Medium',
        waiting_days INTEGER DEFAULT 1,
        budget_used REAL DEFAULT 0,
        budget_remaining REAL DEFAULT 0,
        budget_total REAL DEFAULT 0,
        invoice_sha256 TEXT NOT NULL, -- Cryptographic hash of invoice for duplicate detection
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (requester_id) REFERENCES users(id)
    );
    """)

    # 3. Attachments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_size TEXT NOT NULL,
        ocr_extracted_vendor TEXT,
        ocr_extracted_amount REAL,
        ocr_confidence REAL,
        status TEXT NOT NULL,        -- 'Verified', 'Missing', 'Flagged'
        invoice_sha256 TEXT,
        FOREIGN KEY (request_id) REFERENCES purchase_requests(id)
    );
    """)

    # 4. Approvals table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        approver_role TEXT NOT NULL,
        approver_name TEXT NOT NULL,
        action TEXT NOT NULL,        -- 'Approved', 'Rejected', 'Requested Changes', 'Pending'
        comments TEXT,
        action_timestamp TEXT,
        FOREIGN KEY (request_id) REFERENCES purchase_requests(id)
    );
    """)

    # 5. Audit logs table (Verifiable Hash-Chained ledger)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        ip_address TEXT DEFAULT '127.0.0.1',
        prev_hash TEXT NOT NULL,     -- Hash of previous log entry (Blockchain-style chain)
        log_hash TEXT NOT NULL       -- Current entry SHA-256 hash
    );
    """)

    # 6. AI analyses table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT UNIQUE NOT NULL,
        risk_level TEXT NOT NULL,    -- 'LOW RISK', 'MEDIUM RISK', 'CRITICAL RISK'
        summary_json TEXT NOT NULL,
        policy_flags_json TEXT NOT NULL,
        duplicate_match_id TEXT,
        FOREIGN KEY (request_id) REFERENCES purchase_requests(id)
    );
    """)

    conn.commit()
    conn.close()

def compute_log_hash(prev_hash: str, req_id: str, actor: str, role: str, action: str, details: str, timestamp: str) -> str:
    raw = f"{prev_hash}|{req_id}|{actor}|{role}|{action}|{details}|{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def get_latest_audit_hash() -> str:
    """Retrieves the head hash of the audit log chain."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT log_hash FROM audit_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else GENESIS_HASH

def append_audit_log(request_id: str, actor_name: str, actor_role: str, action: str, details: str) -> str:
    """Appends an entry to the audit log, maintaining the cryptographic hash chain."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT log_hash FROM audit_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_hash = row[0] if row else GENESIS_HASH

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_hash = compute_log_hash(prev_hash, request_id, actor_name, actor_role, action, details, now)

    cursor.execute("""
    INSERT INTO audit_logs (request_id, actor_name, actor_role, action, details, timestamp, ip_address, prev_hash, log_hash)
    VALUES (?, ?, ?, ?, ?, ?, '127.0.0.1', ?, ?)
    """, (request_id, actor_name, actor_role, action, details, now, prev_hash, current_hash))

    conn.commit()
    conn.close()
    return current_hash

def verify_audit_hash_chain() -> dict:
    """
    Traverses the audit log from genesis record to head, recomputing every hash.
    Verifies 100% cryptographic integrity and detects any manual SQL tampering.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, request_id, actor_name, actor_role, action, details, timestamp, prev_hash, log_hash FROM audit_logs ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"chain_valid": True, "total_blocks": 0, "tamper_detected": False}

    expected_prev = GENESIS_HASH
    for r in rows:
        # 1. Check link to previous hash
        if r["prev_hash"] != expected_prev:
            return {
                "chain_valid": False,
                "tamper_detected": True,
                "broken_at_id": r["id"],
                "reason": f"Hash chain broken at ID {r['id']}: expected prev_hash {expected_prev}, found {r['prev_hash']}"
            }

        # 2. Recompute current hash
        recomputed = compute_log_hash(
            r["prev_hash"], r["request_id"], r["actor_name"], r["actor_role"],
            r["action"], r["details"], r["timestamp"]
        )
        if recomputed != r["log_hash"]:
            return {
                "chain_valid": False,
                "tamper_detected": True,
                "broken_at_id": r["id"],
                "reason": f"Content tampering at ID {r['id']}: computed hash {recomputed} does not match stored {r['log_hash']}"
            }

        expected_prev = r["log_hash"]

    return {
        "chain_valid": True,
        "total_blocks": len(rows),
        "tamper_detected": False,
        "head_hash": expected_prev
    }

def seed_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return  # already seeded

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Common password for all seeded users: "password123"
    default_pwd_hash = hash_password("password123")

    # 1. Seed Users with verified passwords
    users = [
        ("u1", "sarah.chen", "Sarah Chen", "sarah.chen@acme.internal", "requester", "IT", 0, default_pwd_hash),
        ("u2", "lisa.park", "Lisa Park", "lisa.park@acme.internal", "requester", "Marketing", 0, default_pwd_hash),
        ("u3", "priya.sharma", "Priya Sharma", "priya.sharma@acme.internal", "requester", "Engineering", 0, default_pwd_hash),
        ("u4", "arun.verma", "Arun Verma", "arun.verma@acme.internal", "manager", "Engineering", 25000, default_pwd_hash),
        ("u5", "neha.gupta", "Neha Gupta", "neha.gupta@acme.internal", "finance", "Finance", 100000, default_pwd_hash),
        ("u6", "rajesh.patel", "Rajesh Patel", "rajesh.patel@acme.internal", "depthead", "Executive", 1000000, default_pwd_hash),
    ]
    cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", users)

    # Known sample invoice hashes
    hash_aws = hashlib.sha256(b"AWS_INVOICE_INV9821_20250218_12500_INR").hexdigest()
    hash_hubspot = hashlib.sha256(b"HUBSPOT_QUOTE_Q901_20250217_85000_INR").hexdigest()
    hash_datadog = hashlib.sha256(b"DATADOG_ANNUAL_ORDER_20250215_145000_INR").hexdigest()
    hash_featherlite = hashlib.sha256(b"FEATHERLITE_CHAIRS_20250214_42500_INR").hexdigest()
    # Historical invoice PR-1041 hash (used to detect duplicate fraud for PR-1046)
    hash_duplicate_target = hashlib.sha256(b"IMAGINE_APPLE_INV9921_HISTORICAL_245000_INR").hexdigest()

    # 2. Seed Requests
    requests = [
        (
            "PR-1042", "u1", "Sarah Chen", "IT",
            "Cloud Server Licenses", "Cloud & Infra", "AWS India",
            12500.0,
            "Current servers reaching capacity. Need additional EC2 compute instances for Q2 scaling.",
            "Tier 1 (≤ ₹25,000)", "PENDING_MANAGER", "High Priority", 2,
            156000.0, 44000.0, 200000.0, hash_aws, now, now
        ),
        (
            "PR-1043", "u2", "Lisa Park", "Marketing",
            "Marketing Analytics Platform (HubSpot)", "Cloud SaaS", "HubSpot Ireland",
            85000.0,
            "Annual seat expansion for campaign lifecycle automation and lead scoring.",
            "Tier 2 (₹25,001 - ₹1,00,000)", "PENDING_FINANCE", "Medium Priority", 1,
            210000.0, 90000.0, 300000.0, hash_hubspot, now, now
        ),
        (
            "PR-1044", "u3", "Priya Sharma", "Engineering",
            "Datadog Enterprise APM Subscription", "Cloud SaaS", "Datadog Singapore Pte",
            145000.0,
            "Infrastructure latency tracing and automated incident triage for Q4 production release.",
            "Tier 3 (> ₹1,00,000)", "PENDING_DEPTHEAD", "High Priority", 3,
            380000.0, 120000.0, 500000.0, hash_datadog, now, now
        ),
        (
            "PR-1045", "u3", "Kunal Mehra", "Design",
            "Ergonomic Studio Chairs (x5)", "Office Equipment", "Featherlite Workspaces",
            42500.0,
            "Ergonomic seating for newly joined product design team members.",
            "Tier 2 (₹25,001 - ₹1,00,000)", "FLAGGED_MISSING_DOCS", "Low Priority", 4,
            65000.0, 35000.0, 100000.0, hash_featherlite, now, now
        ),
        (
            "PR-1046", "u3", "Aman Sen", "Engineering",
            "MacBook Pro M3 Max (32GB) - Priority", "Hardware", "Imagine Apple Reseller",
            245000.0,
            "Replacement laptop for senior build engineer. Previous machine sustained board failure.",
            "Tier 3 (> ₹1,00,000)", "REJECTED", "High Priority", 1,
            410000.0, 90000.0, 500000.0, hash_duplicate_target, now, now
        )
    ]
    cursor.executemany("""
    INSERT INTO purchase_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, requests)

    # 3. Seed Attachments
    attachments = [
        ("PR-1042", "AWS_Invoice_INV-9821.pdf", "1.2 MB", "AWS India", 12500.0, 99.4, "Verified", hash_aws),
        ("PR-1043", "HubSpot_Quote_Q901.pdf", "1.8 MB", "HubSpot Ireland", 85000.0, 98.7, "Verified", hash_hubspot),
        ("PR-1044", "Datadog_Annual_OrderForm.pdf", "2.5 MB", "Datadog Singapore Pte", 145000.0, 99.1, "Verified", hash_datadog),
        ("PR-1045", "Featherlite_Chairs_SingleQuote.pdf", "890 KB", "Featherlite", 42500.0, 96.5, "Verified", hash_featherlite),
        ("PR-1046", "Imagine_Invoice_INV-9921_Duplicate.pdf", "3.2 MB", "Imagine Apple Reseller", 245000.0, 99.0, "Flagged", hash_duplicate_target),
    ]
    cursor.executemany("""
    INSERT INTO attachments (request_id, file_name, file_size, ocr_extracted_vendor, ocr_extracted_amount, ocr_confidence, status, invoice_sha256)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, attachments)

    # 4. Seed Approvals
    approvals = [
        ("PR-1042", "Team Lead", "Mark Wilson", "Approved", "Verified IT inventory requirement.", "2025-02-18 10:30:00"),
        ("PR-1042", "Line Manager", "Arun Verma", "Pending", None, None),

        ("PR-1043", "Line Manager", "Arun Verma", "Approved", "Budget validated under marketing Q1.", "2025-02-17 14:15:00"),
        ("PR-1043", "Finance Manager", "Neha Gupta", "Pending", None, None),

        ("PR-1044", "Line Manager", "Arun Verma", "Approved", "Mandatory for latency SLA.", "2025-02-15 11:20:00"),
        ("PR-1044", "Finance Manager", "Neha Gupta", "Approved", "Budget code 402 verified. 2 quotes attached.", "2025-02-15 15:45:00"),
        ("PR-1044", "Department Head", "Rajesh Patel", "Pending", None, None),

        ("PR-1045", "Line Manager", "Arun Verma", "Requested Changes", "Please attach a second comparative quote for spend > ₹25k.", "2025-02-16 09:10:00"),
        ("PR-1046", "Line Manager", "Arun Verma", "Rejected", "Rejected: Cryptographic duplicate hash matched historical PR-1041.", "2025-02-17 09:00:00"),
    ]
    cursor.executemany("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, approvals)

    # 5. Seed AI Analyses
    ai_records = [
        (
            "PR-1042", "LOW RISK",
            json.dumps([
                "Tier 1 (≤ ₹25,000) threshold confirmed: requires only Line Manager approval.",
                "Finance and Dept Head bypassed per company policy.",
                "OCR matched vendor invoice with 99.4% confidence."
            ]),
            json.dumps([
                {"rule": "Tier 1 Approval Rule", "pass": True, "note": "≤ ₹25,000 requires only Manager"},
                {"rule": "Budget Availability", "pass": True, "note": "IT budget has ₹44,000 remaining"},
                {"rule": "Cryptographic Hash Duplicate Check", "pass": True, "note": "0 historical SHA-256 collisions"}
            ]),
            None
        ),
        (
            "PR-1043", "LOW RISK",
            json.dumps([
                "Tier 2 (₹25k - ₹1L): Requires Line Manager AND Finance approval.",
                "Manager Arun Verma approved; Finance Neha Gupta review active.",
                "Two comparative quotes provided. Budget capacity verified."
            ]),
            json.dumps([
                {"rule": "Tier 2 Approval Rule", "pass": True, "note": "Manager + Finance approval required"},
                {"rule": "Two-Quote Rule", "pass": True, "note": "HubSpot & Salesforce quotes provided"}
            ]),
            None
        ),
        (
            "PR-1044", "LOW RISK",
            json.dumps([
                "Tier 3 (> ₹1,00,000): High-value spend requires Manager, Finance, and Dept Head sign-offs.",
                "Sequential approval pathway: Manager (Done) -> Finance (Done) -> Dept Head (Pending).",
                "Department Head cannot sign off until Finance approval is recorded."
            ]),
            json.dumps([
                {"rule": "Tier 3 Approval Rule", "pass": True, "note": "Manager + Finance + Dept Head required"},
                {"rule": "Sequential Gate", "pass": True, "note": "Finance approved, ready for Dept Head"}
            ]),
            None
        ),
        (
            "PR-1045", "MEDIUM RISK",
            json.dumps([
                "POLICY VIOLATION: Submissions exceeding ₹25,000 mandate at least two comparative vendor quotes.",
                "Only Featherlite quote was attached. System automatically blocks final approval."
            ]),
            json.dumps([
                {"rule": "Two-Quote Rule", "pass": False, "note": "MISSING: Only 1 vendor quote provided"},
                {"rule": "Approval Gatekeeper", "pass": False, "note": "Final approval blocked by policy"}
            ]),
            None
        ),
        (
            "PR-1046", "CRITICAL RISK",
            json.dumps([
                "CRITICAL FRAUD / DUPLICATE ALERT: Cryptographic SHA-256 hash exactly matches historical PR-1041.",
                "Identical invoice content and vendor GSTIN detected.",
                "Automated approval lock engaged. AI strictly forbids automated sign-off; manual audit required."
            ]),
            json.dumps([
                {"rule": "Cryptographic Hash Collision", "pass": False, "note": "Exact SHA-256 match with PR-1041"},
                {"rule": "AI Safety Rule", "pass": True, "note": "AI refusal to approve; routed to human fraud review"}
            ]),
            "PR-1041"
        )
    ]
    cursor.executemany("""
    INSERT INTO ai_analyses (request_id, risk_level, summary_json, policy_flags_json, duplicate_match_id)
    VALUES (?, ?, ?, ?, ?)
    """, ai_records)

    # 6. Seed Hash-Chained Audit Logs
    audit_entries = [
        ("PR-1042", "Sarah Chen", "requester", "REQUEST_CREATED", "Created request for Cloud Server Licenses (₹12,500)"),
        ("PR-1042", "System AI", "ai_copilot", "OCR_EXTRACTED", "Verified AWS India invoice #INV-9821 with 99.4% confidence"),
        ("PR-1042", "Mark Wilson", "manager", "APPROVAL_GRANTED", "Team Lead approval signed off"),

        ("PR-1043", "Lisa Park", "requester", "REQUEST_CREATED", "Submitted HubSpot procurement request (₹85,000)"),
        ("PR-1043", "Arun Verma", "manager", "APPROVAL_GRANTED", "Line Manager approved under Marketing Q1 budget"),

        ("PR-1044", "Priya Sharma", "requester", "REQUEST_CREATED", "Submitted Datadog APM contract request (₹1,45,000)"),
        ("PR-1044", "Arun Verma", "manager", "APPROVAL_GRANTED", "Line Manager approved (Latency SLA priority)"),
        ("PR-1044", "Neha Gupta", "finance", "APPROVAL_GRANTED", "Finance approved (Budget verified under code 402)"),

        ("PR-1045", "Kunal Mehra", "requester", "REQUEST_CREATED", "Submitted furniture request (₹42,500)"),
        ("PR-1045", "System AI", "ai_copilot", "POLICY_FLAG_RAISED", "Missing second comparative quote for purchase > ₹25,000"),

        ("PR-1046", "Aman Sen", "requester", "REQUEST_CREATED", "Submitted MacBook Pro replacement (₹2,45,000)"),
        ("PR-1046", "System AI", "ai_copilot", "DUPLICATE_INVOICE_LOCKED", "Cryptographic SHA-256 collision with PR-1041. Automated block engaged.")
    ]

    current_prev = GENESIS_HASH
    for req_id, actor, role, act, det in audit_entries:
        ts = now
        entry_hash = compute_log_hash(current_prev, req_id, actor, role, act, det, ts)
        cursor.execute("""
        INSERT INTO audit_logs (request_id, actor_name, actor_role, action, details, timestamp, ip_address, prev_hash, log_hash)
        VALUES (?, ?, ?, ?, ?, ?, '127.0.0.1', ?, ?)
        """, (req_id, actor, role, act, det, ts, current_prev, entry_hash))
        current_prev = entry_hash

    conn.commit()
    conn.close()

def reset_db():
    """Drops and reinitializes database for clean test execution."""
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except Exception:
            pass
    init_db()
    seed_db()

if __name__ == "__main__":
    reset_db()
    chain_status = verify_audit_hash_chain()
    print("FlowSync database re-seeded successfully.")
    print("Audit Log Cryptographic Hash-Chain Verification:", chain_status)
