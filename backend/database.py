"""
Database schema, initialization, and initial seed data for FlowSync AI
Case Study 03: Enterprise Request & Approval Platform
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "flowsync.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL,          -- 'requester', 'manager', 'finance', 'depthead'
        department TEXT NOT NULL,
        budget_limit REAL DEFAULT 0.0
    );
    """)

    # Purchase requests table
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
        status TEXT NOT NULL,        -- 'PENDING_MANAGER', 'PENDING_FINANCE', 'PENDING_DEPTHEAD', 'APPROVED', 'REJECTED', 'FLAGGED'
        priority TEXT DEFAULT 'Medium',
        waiting_days INTEGER DEFAULT 1,
        budget_used REAL DEFAULT 0,
        budget_remaining REAL DEFAULT 0,
        budget_total REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (requester_id) REFERENCES users(id)
    );
    """)

    # Attachments table with OCR simulation data
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
        FOREIGN KEY (request_id) REFERENCES purchase_requests(id)
    );
    """)

    # Approvals table
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

    # Audit logs table (tamper-evident with SHA-256)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        actor_name TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        ip_address TEXT DEFAULT '10.0.4.12',
        log_hash TEXT NOT NULL
    );
    """)

    # AI analyses table
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

def compute_hash(record_str: str) -> str:
    return hashlib.sha256(record_str.encode("utf-8")).hexdigest()

def seed_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return  # already seeded

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Seed Users
    users = [
        ("u1", "sarah.chen", "Sarah Chen", "sarah.chen@acme.internal", "requester", "IT", 0),
        ("u2", "lisa.park", "Lisa Park", "lisa.park@acme.internal", "requester", "Marketing", 0),
        ("u3", "priya.sharma", "Priya Sharma", "priya.sharma@acme.internal", "requester", "Engineering", 0),
        ("u4", "arun.verma", "Arun Verma", "arun.verma@acme.internal", "manager", "Engineering", 25000),
        ("u5", "neha.gupta", "Neha Gupta", "neha.gupta@acme.internal", "finance", "Finance", 100000),
        ("u6", "rajesh.patel", "Rajesh Patel", "rajesh.patel@acme.internal", "depthead", "Executive", 1000000),
    ]
    cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", users)

    # 2. Seed Requests
    requests = [
        (
            "PR-1042", "u1", "Sarah Chen", "IT",
            "Cloud Server Licenses", "Cloud & Infra", "AWS India",
            12500.0,
            "Current servers reaching capacity. Need additional EC2 compute instances for Q2 scaling.",
            "Tier 1 (≤ ₹25,000)", "PENDING_MANAGER", "High Priority", 2,
            156000.0, 44000.0, 200000.0, now, now
        ),
        (
            "PR-1043", "u2", "Lisa Park", "Marketing",
            "Marketing Analytics Platform (HubSpot)", "Cloud SaaS", "HubSpot Ireland",
            85000.0,
            "Annual seat expansion for campaign lifecycle automation and lead scoring.",
            "Tier 2 (₹25,001 - ₹1,00,000)", "PENDING_FINANCE", "Medium Priority", 1,
            210000.0, 90000.0, 300000.0, now, now
        ),
        (
            "PR-1044", "u3", "Priya Sharma", "Engineering",
            "Datadog Enterprise APM Subscription", "Cloud SaaS", "Datadog Singapore Pte",
            145000.0,
            "Infrastructure latency tracing and automated incident triage for Q4 production release.",
            "Tier 3 (> ₹1,00,000)", "PENDING_DEPTHEAD", "High Priority", 3,
            380000.0, 120000.0, 500000.0, now, now
        ),
        (
            "PR-1045", "u3", "Kunal Mehra", "Design",
            "Ergonomic Studio Chairs (x5)", "Office Equipment", "Featherlite Workspaces",
            42500.0,
            "Ergonomic seating for newly joined product design team members.",
            "Tier 2 (₹25,001 - ₹1,00,000)", "FLAGGED", "Low Priority", 4,
            65000.0, 35000.0, 100000.0, now, now
        ),
        (
            "PR-1046", "u3", "Aman Sen", "Engineering",
            "MacBook Pro M3 Max (32GB) - Priority", "Hardware", "Imagine Apple Reseller",
            245000.0,
            "Replacement laptop for senior build engineer. Previous machine sustained board failure.",
            "Tier 3 (> ₹1,00,000)", "FLAGGED", "High Priority", 1,
            410000.0, 90000.0, 500000.0, now, now
        )
    ]
    cursor.executemany("""
    INSERT INTO purchase_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, requests)

    # 3. Seed Attachments
    attachments = [
        ("PR-1042", "AWS_Invoice_INV-9821.pdf", "1.2 MB", "AWS India", 12500.0, 99.4, "Verified"),
        ("PR-1043", "HubSpot_Quote_Q901.pdf", "1.8 MB", "HubSpot Ireland", 85000.0, 98.7, "Verified"),
        ("PR-1043", "Salesforce_Comparison_Quote.pdf", "2.1 MB", "Salesforce", 92000.0, 97.9, "Verified"),
        ("PR-1044", "Datadog_Annual_OrderForm.pdf", "2.5 MB", "Datadog Singapore Pte", 145000.0, 99.1, "Verified"),
        ("PR-1044", "Dynatrace_Alternative_Quote.pdf", "1.9 MB", "Dynatrace", 160000.0, 98.2, "Verified"),
        ("PR-1045", "Featherlite_Chairs_SingleQuote.pdf", "890 KB", "Featherlite", 42500.0, 96.5, "Verified"),
        ("PR-1046", "Imagine_Invoice_INV-9921_Duplicate.pdf", "3.2 MB", "Imagine Apple Reseller", 245000.0, 99.0, "Flagged"),
    ]
    cursor.executemany("""
    INSERT INTO attachments (request_id, file_name, file_size, ocr_extracted_vendor, ocr_extracted_amount, ocr_confidence, status)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, attachments)

    # 4. Seed Approvals
    approvals = [
        # PR-1042: Step 1 (Team Lead) Approved, Step 2 (Manager) Pending, Step 3 (Finance) N/A (Tier 1)
        ("PR-1042", "Team Lead", "Mark Wilson", "Approved", "Verified IT inventory requirement.", "2025-02-18 10:30:00"),
        ("PR-1042", "Line Manager", "Arun Verma", "Pending", None, None),

        # PR-1043: Manager Approved, Finance Pending
        ("PR-1043", "Line Manager", "Arun Verma", "Approved", "Budget validated under marketing Q1.", "2025-02-17 14:15:00"),
        ("PR-1043", "Finance Manager", "Neha Gupta", "Pending", None, None),

        # PR-1044: Manager Approved, Finance Approved, Dept Head Pending
        ("PR-1044", "Line Manager", "Arun Verma", "Approved", "Mandatory for Q4 release latency monitoring.", "2025-02-15 11:20:00"),
        ("PR-1044", "Finance Manager", "Neha Gupta", "Approved", "Budget code 402 verified. Competitive quotes attached.", "2025-02-15 15:45:00"),
        ("PR-1044", "Department Head", "Rajesh Patel", "Pending", None, None),

        # PR-1045: Blocked on missing second quote
        ("PR-1045", "Line Manager", "Arun Verma", "Requested Changes", "Please attach a second comparative quote as required for purchases > ₹25,000.", "2025-02-16 09:10:00"),

        # PR-1046: Flagged for duplicate invoice
        ("PR-1046", "Line Manager", "Arun Verma", "Pending", "Flagged by AI: Possible duplicate submission of PR-1041.", None),
    ]
    cursor.executemany("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, approvals)

    # 5. Seed AI Analyses
    ai_records = [
        (
            "PR-1042",
            "LOW RISK",
            json.dumps([
                "EC2 compute expansion for IT team; amount ₹12,500 falls strictly under Tier 1 (≤ ₹25,000).",
                "Requires only Line Manager approval; Finance/Dept Head bypassed per policy.",
                "OCR matched vendor invoice with 99.4% confidence."
            ]),
            json.dumps([
                {"rule": "Tier 1 Approval Rule", "pass": True, "note": "≤ ₹25,000 requires only Manager"},
                {"rule": "Budget Availability", "pass": True, "note": "IT budget has ₹44,000 remaining (78% used)"},
                {"rule": "Duplicate Detection", "pass": True, "note": "0 historical matches found"}
            ]),
            None
        ),
        (
            "PR-1043",
            "LOW RISK",
            json.dumps([
                "HubSpot annual license renewal of ₹85,000 falls in Tier 2 (₹25k - ₹1L).",
                "Manager Arun Verma approved; Finance Neha Gupta review active.",
                "Two comparative quotes provided (HubSpot vs Salesforce). 3-way match verified."
            ]),
            json.dumps([
                {"rule": "Tier 2 Approval Rule", "pass": True, "note": "Manager + Finance approval required"},
                {"rule": "Two-Quote Rule", "pass": True, "note": "HubSpot & Salesforce quotes provided"},
                {"rule": "Budget Availability", "pass": True, "note": "Marketing budget has ₹90,000 remaining"}
            ]),
            None
        ),
        (
            "PR-1044",
            "LOW RISK",
            json.dumps([
                "High-value Datadog APM contract (₹1,45,000) exceeds ₹1,00,000 threshold (Tier 3).",
                "Sequential approval pathway: Manager (Done) -> Finance (Done) -> Dept Head (Pending).",
                "Engineering budget capacity confirmed; valid GSTIN and 2 quotes attached."
            ]),
            json.dumps([
                {"rule": "Tier 3 Approval Rule", "pass": True, "note": "Manager + Finance + Dept Head required"},
                {"rule": "Vendor Compliance", "pass": True, "note": "Valid GSTIN 07AABCD1234E1Z8 verified"},
                {"rule": "Two-Quote Rule", "pass": True, "note": "Dynatrace alternate quote attached"}
            ]),
            None
        ),
        (
            "PR-1045",
            "MEDIUM RISK",
            json.dumps([
                "Office furniture request of ₹42,500 requires Tier 2 approval (Manager + Finance).",
                "POLICY VIOLATION: Submissions exceeding ₹25,000 mandate at least two comparative vendor quotes.",
                "Only Featherlite quote was attached. System automatically blocks final approval until resolved."
            ]),
            json.dumps([
                {"rule": "Two-Quote Rule", "pass": False, "note": "MISSING: Only 1 vendor quote provided"},
                {"rule": "Approval Gatekeeper", "pass": False, "note": "Final approval blocked by policy"}
            ]),
            None
        ),
        (
            "PR-1046",
            "CRITICAL RISK",
            json.dumps([
                "CRITICAL FRAUD / DUPLICATE ALERT: Invoice # INV-9921 exactly matches historical PR-1041 processed 28 days ago.",
                "Amount: ₹2,45,000 with identical vendor GSTIN and line-item description.",
                "Automated approval lock engaged. AI strictly forbids automated sign-off; manual audit required."
            ]),
            json.dumps([
                {"rule": "Duplicate Invoice Check", "pass": False, "note": "Hash match detected with PR-1041"},
                {"rule": "AI Safety Rule", "pass": True, "note": "AI refusal to approve; delegated to human fraud review"}
            ]),
            "PR-1041"
        )
    ]
    cursor.executemany("""
    INSERT INTO ai_analyses (request_id, risk_level, summary_json, policy_flags_json, duplicate_match_id)
    VALUES (?, ?, ?, ?, ?)
    """, ai_records)

    # 6. Seed Audit Logs
    audit_entries = [
        ("PR-1042", "Sarah Chen", "requester", "REQUEST_CREATED", "Created request for Cloud Server Licenses (₹12,500)", now),
        ("PR-1042", "System AI", "ai_copilot", "OCR_EXTRACTED", "Verified AWS India invoice #INV-9821 with 99.4% confidence", now),
        ("PR-1042", "Mark Wilson", "manager", "APPROVAL_GRANTED", "Team Lead approval signed off", now),

        ("PR-1043", "Lisa Park", "requester", "REQUEST_CREATED", "Submitted HubSpot procurement request (₹85,000)", now),
        ("PR-1043", "Arun Verma", "manager", "APPROVAL_GRANTED", "Line Manager approved under Marketing Q1 budget", now),

        ("PR-1044", "Priya Sharma", "requester", "REQUEST_CREATED", "Submitted Datadog APM contract request (₹1,45,000)", now),
        ("PR-1044", "Arun Verma", "manager", "APPROVAL_GRANTED", "Line Manager approved (Latency SLA priority)", now),
        ("PR-1044", "Neha Gupta", "finance", "APPROVAL_GRANTED", "Finance approved (Budget verified under code 402)", now),

        ("PR-1045", "Kunal Mehra", "requester", "REQUEST_CREATED", "Submitted furniture request (₹42,500)", now),
        ("PR-1045", "System AI", "ai_copilot", "POLICY_FLAG_RAISED", "Missing second comparative quote for purchase > ₹25,000", now),

        ("PR-1046", "Aman Sen", "requester", "REQUEST_CREATED", "Submitted MacBook Pro replacement (₹2,45,000)", now),
        ("PR-1046", "System AI", "ai_copilot", "DUPLICATE_INVOICE_LOCKED", "Duplicate invoice hash match with PR-1041. Automated block engaged.", now)
    ]

    for req_id, actor, role, act, det, ts in audit_entries:
        rec_hash = compute_hash(f"{req_id}|{actor}|{role}|{act}|{det}|{ts}")
        cursor.execute("""
        INSERT INTO audit_logs (request_id, actor_name, actor_role, action, details, timestamp, log_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (req_id, actor, role, act, det, ts, rec_hash))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_db()
    print("FlowSync database initialized and seeded successfully at:", DB_PATH)
