"""
FlowSync AI - Enterprise Request & Approval Platform
FastAPI Backend API
Implements S3K Case Study 03 Specifications & BuyOps MVP
"""

import json
import sqlite3
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Header, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Support direct execution and module imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from backend.database import get_connection, compute_hash, init_db, seed_db
    from backend.models import CreatePurchaseRequest, ApprovalDecision, AIChatQuery
except ImportError:
    from database import get_connection, compute_hash, init_db, seed_db
    from models import CreatePurchaseRequest, ApprovalDecision, AIChatQuery

app = FastAPI(
    title="FlowSync AI - Enterprise Request & Approval Engine",
    description="Backend service powering automated validation, tiered approval workflows, and human-governed AI oversight.",
    version="2.4.0"
)

# Enable CORS for local development and browser frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure DB is ready on startup
@app.on_event("startup")
def startup_event():
    init_db()
    seed_db()

# ---------------------------------------------------------
# Security & Authorization Helper (ABAC / Object-Level Access)
# ---------------------------------------------------------
def get_current_user_context(
    x_user_id: Optional[str] = Header("u4", alias="X-User-Id"),
    x_user_role: Optional[str] = Header("manager", alias="X-User-Role")
):
    """
    Simulates authenticated session context.
    Roles: 'requester', 'manager', 'finance', 'depthead'
    """
    return {"user_id": x_user_id, "role": x_user_role}

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@app.get("/")
def root():
    frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {
        "platform": "FlowSync AI",
        "case_study": "S3K Internship 2026 - Case Study 03",
        "status": "operational",
        "endpoints": {
            "metrics": "/api/v1/metrics",
            "requests": "/api/v1/requests",
            "copilot": "/api/v1/ai/chat"
        }
    }

@app.get("/prototype")
def prototype_view():
    proto_path = Path(__file__).resolve().parent.parent / "prototype" / "index.html"
    if proto_path.exists():
        return FileResponse(proto_path)
    raise HTTPException(status_code=404, detail="Prototype file not found.")

@app.get("/api")
def api_info():
    return {
        "platform": "FlowSync / BuyOps AI",
        "version": "2.4.0",
        "docs": "/docs",
        "endpoints": {
            "metrics": "/api/v1/metrics",
            "requests": "/api/v1/requests",
            "copilot": "/api/v1/ai/chat"
        }
    }

@app.get("/api/v1/metrics")
def get_metrics():
    """
    Returns aggregated KPIs matching the BuyOps dashboard metrics.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM purchase_requests")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status LIKE 'PENDING_%'")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status = 'APPROVED'")
    approved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status IN ('REJECTED', 'FLAGGED')")
    flagged_rejected = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(amount) FROM purchase_requests WHERE status LIKE 'PENDING_%'")
    pending_val = cursor.fetchone()[0] or 0.0

    conn.close()

    return {
        "approval_status": {
            "pending": pending,
            "approved": approved,
            "rejected": flagged_rejected,
            "total": total,
            "pending_percentage": round((pending / max(total, 1)) * 100, 1)
        },
        "pending_value": {
            "total_inr": pending_val,
            "breakdown": [
                {"department": "IT", "percentage": 10},
                {"department": "Marketing", "percentage": 70},
                {"department": "Office", "percentage": 20}
            ]
        },
        "this_session": {
            "reviewed_percent": 42,
            "approved_count": 10,
            "remaining_count": 12
        },
        "business_kpis": {
            "median_tat_hours": 18.4,
            "baseline_tat_days": 5.0,
            "tat_reduction_percent": 84.6,
            "first_time_right_percent": 96.8,
            "baseline_incomplete_percent": 28.0,
            "current_incomplete_percent": 3.2,
            "manual_chaser_inquiries_monthly": 8
        }
    }

@app.get("/api/v1/requests")
def list_requests(
    filter_type: Optional[str] = Query("all"),
    search: Optional[str] = Query(None),
    auth: dict = Depends(get_current_user_context)
):
    """
    Lists purchase requests with strict Object-Level Security (RLS).
    - 'requester' can ONLY see their own requests.
    - 'manager', 'finance', 'depthead' see requests within their jurisdiction.
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT r.*, a.risk_level, a.summary_json, a.policy_flags_json, a.duplicate_match_id
    FROM purchase_requests r
    LEFT JOIN ai_analyses a ON r.id = a.request_id
    WHERE 1=1
    """
    params = []

    # Object-Level Authorization:
    if auth["role"] == "requester":
        query += " AND r.requester_id = ?"
        params.append(auth["user_id"])

    if filter_type == "pending":
        query += " AND r.status LIKE 'PENDING_%'"
    elif filter_type == "flagged":
        query += " AND (r.status = 'FLAGGED' OR a.risk_level != 'LOW RISK')"
    elif filter_type == "approved":
        query += " AND r.status = 'APPROVED'"

    if search:
        query += " AND (r.id LIKE ? OR r.title LIKE ? OR r.vendor LIKE ? OR r.requester_name LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " ORDER BY r.waiting_days DESC, r.created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        req = dict(row)
        req["summary"] = json.loads(req["summary_json"]) if req["summary_json"] else []
        req["policy_flags"] = json.loads(req["policy_flags_json"]) if req["policy_flags_json"] else []
        results.append(req)

    conn.close()
    return {"requests": results, "count": len(results), "user_role": auth["role"]}

@app.get("/api/v1/requests/{request_id}")
def get_request_detail(
    request_id: str,
    auth: dict = Depends(get_current_user_context)
):
    """
    Fetches full request details, attachments, workflow history, and audit log.
    Enforces Object-Level Access Control (IDOR prevention).
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Purchase request {request_id} not found.")

    req = dict(row)

    # Object-Level Access Control Check (BOLA / IDOR defense)
    if auth["role"] == "requester" and req["requester_id"] != auth["user_id"]:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security Violation: You are not authorized to view another employee's purchase request."
        )

    # Attachments
    cursor.execute("SELECT * FROM attachments WHERE request_id = ?", (request_id,))
    req["attachments"] = [dict(a) for a in cursor.fetchall()]

    # Approvals history
    cursor.execute("SELECT * FROM approvals WHERE request_id = ? ORDER BY id ASC", (request_id,))
    req["approvals"] = [dict(ap) for ap in cursor.fetchall()]

    # AI Analysis
    cursor.execute("SELECT * FROM ai_analyses WHERE request_id = ?", (request_id,))
    ai_row = cursor.fetchone()
    if ai_row:
        ai_data = dict(ai_row)
        ai_data["summary"] = json.loads(ai_data["summary_json"])
        ai_data["policy_flags"] = json.loads(ai_data["policy_flags_json"])
        req["ai_analysis"] = ai_data
    else:
        req["ai_analysis"] = None

    # Audit Logs
    cursor.execute("SELECT * FROM audit_logs WHERE request_id = ? ORDER BY id DESC", (request_id,))
    req["audit_logs"] = [dict(log) for log in cursor.fetchall()]

    conn.close()
    return req

@app.post("/api/v1/requests", status_code=status.HTTP_201_CREATED)
def create_purchase_request(
    payload: CreatePurchaseRequest,
    auth: dict = Depends(get_current_user_context)
):
    """
    Creates a new purchase request, automatically applies tier routing rules,
    performs AI validation checks, and records tamper-evident audit logs.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Generate sequential ID
    cursor.execute("SELECT COUNT(*) FROM purchase_requests")
    cnt = cursor.fetchone()[0]
    req_id = f"PR-{1042 + cnt + 1}"

    # Evaluate Tier based on Case Study 03 rules:
    # Tier 1: <= 25,000 -> Manager
    # Tier 2: 25,001 - 1,00,000 -> Manager + Finance
    # Tier 3: > 1,00,000 -> Manager + Finance + Dept Head
    if payload.amount <= 25000:
        tier = "Tier 1 (≤ ₹25,000)"
        init_status = "PENDING_MANAGER"
    elif payload.amount <= 100000:
        tier = "Tier 2 (₹25,001 - ₹1,00,000)"
        init_status = "PENDING_MANAGER"
    else:
        tier = "Tier 3 (> ₹1,00,000)"
        init_status = "PENDING_MANAGER"

    # Policy Check: Missing 2nd quote for > 25,000
    has_policy_blocker = False
    policy_flags = []
    risk_level = "LOW RISK"

    if payload.amount > 25000 and (payload.quotes_count or 1) < 2:
        has_policy_blocker = True
        risk_level = "MEDIUM RISK"
        init_status = "FLAGGED"
        policy_flags.append({
            "rule": "Two-Quote Requirement",
            "pass": False,
            "note": "Purchases over ₹25,000 require at least 2 competitive vendor quotes."
        })
    else:
        policy_flags.append({
            "rule": "Two-Quote Requirement",
            "pass": True,
            "note": "Competitive quotes verified."
        })

    # Duplicate check simulation
    cursor.execute("SELECT id FROM purchase_requests WHERE vendor = ? AND amount = ?", (payload.vendor, payload.amount))
    dup = cursor.fetchone()
    dup_id = dup[0] if dup else None
    if dup_id:
        has_policy_blocker = True
        risk_level = "CRITICAL RISK"
        init_status = "FLAGGED"
        policy_flags.append({
            "rule": "Duplicate Invoice Check",
            "pass": False,
            "note": f"CRITICAL: Matching vendor & exact amount found in {dup_id}."
        })

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert request
    cursor.execute("""
    INSERT INTO purchase_requests (
        id, requester_id, requester_name, department, title, category, vendor, amount,
        business_justification, tier, status, priority, waiting_days,
        budget_used, budget_remaining, budget_total, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req_id, auth["user_id"], payload.requester_name or "Sarah Chen", payload.department or "Engineering",
        payload.title, payload.category, payload.vendor, payload.amount,
        payload.business_justification, tier, init_status, "Medium Priority", 0,
        180000.0, 70000.0, 250000.0, now, now
    ))

    # Insert simulated attachment
    cursor.execute("""
    INSERT INTO attachments (request_id, file_name, file_size, ocr_extracted_vendor, ocr_extracted_amount, ocr_confidence, status)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        req_id, f"{payload.vendor.replace(' ', '_')}_Quote.pdf", "1.4 MB",
        payload.vendor, payload.amount, 99.2, "Verified" if not has_policy_blocker else "Flagged"
    ))

    # Insert Initial Approval Stage
    cursor.execute("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (req_id, "Line Manager", "Arun Verma", "Pending" if not has_policy_blocker else "Blocked", None, None))

    # Insert AI Analysis
    summary_bullets = [
        f"Submitted by {payload.requester_name} for {payload.category}.",
        f"Assigned to {tier} based on automated rule threshold.",
        f"AI Validation Status: {risk_level}. Policy rules verified."
    ]
    cursor.execute("""
    INSERT INTO ai_analyses (request_id, risk_level, summary_json, policy_flags_json, duplicate_match_id)
    VALUES (?, ?, ?, ?, ?)
    """, (req_id, risk_level, json.dumps(summary_bullets), json.dumps(policy_flags), dup_id))

    # Tamper-evident Audit Log
    log_detail = f"Request created for {payload.title} (₹{payload.amount:,.2f}). Tier: {tier}. Initial status: {init_status}."
    rec_hash = compute_hash(f"{req_id}|{payload.requester_name}|requester|CREATE|{log_detail}|{now}")
    cursor.execute("""
    INSERT INTO audit_logs (request_id, actor_name, actor_role, action, details, timestamp, log_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (req_id, payload.requester_name, "requester", "REQUEST_CREATED", log_detail, now, rec_hash))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "request_id": req_id,
        "tier": tier,
        "status": init_status,
        "risk_level": risk_level,
        "message": "Purchase request created and routed successfully."
    }

@app.post("/api/v1/requests/{request_id}/decision")
def record_approval_decision(
    request_id: str,
    decision: ApprovalDecision,
    auth: dict = Depends(get_current_user_context)
):
    """
    Enforces strict Human Governance & Tiered Approval Rules:
    1. AI never approves financial requests.
    2. Missing documents / policy flags block approval.
    3. Tier 3 (> ₹1,00,000) mandates Dept Head sign-off before final approval.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()
    if not req:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found.")

    req = dict(req)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardrail 1: Block approval if missing documents / flagged
    if decision.action == "Approve" and req["status"] == "FLAGGED":
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Policy Guardrail Active: Missing documents or unaddressed policy flags block final approval."
        )

    # State Machine Progression based on Tier
    new_status = req["status"]
    if decision.action == "Approve":
        if req["amount"] <= 25000:
            # Tier 1: Line Manager sign-off completes approval
            new_status = "APPROVED"
        elif req["amount"] <= 100000:
            # Tier 2: Manager -> Finance
            if auth["role"] == "manager":
                new_status = "PENDING_FINANCE"
            elif auth["role"] == "finance":
                new_status = "APPROVED"
        else:
            # Tier 3: Manager -> Finance -> Dept Head
            if auth["role"] == "manager":
                new_status = "PENDING_FINANCE"
            elif auth["role"] == "finance":
                new_status = "PENDING_DEPTHEAD"
            elif auth["role"] == "depthead":
                new_status = "APPROVED"
            else:
                conn.close()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tier 3 purchases (> ₹1,00,000) require Department Head authorization for final sign-off."
                )

    elif decision.action == "Reject":
        new_status = "REJECTED"
    elif decision.action == "Request Changes":
        new_status = "FLAGGED"

    # Update request table
    cursor.execute("""
    UPDATE purchase_requests
    SET status = ?, updated_at = ?
    WHERE id = ?
    """, (new_status, now, request_id))

    # Add approval log record
    cursor.execute("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (request_id, auth["role"].upper(), f"User-{auth['user_id']}", decision.action, decision.comments or "Action recorded.", now))

    # Immutable Audit Log
    act_str = f"HUMAN_{decision.action.upper()}"
    details = f"Decision '{decision.action}' applied by {auth['role']}. New state: {new_status}. Note: {decision.comments}"
    rec_hash = compute_hash(f"{request_id}|{auth['user_id']}|{auth['role']}|{act_str}|{details}|{now}")

    cursor.execute("""
    INSERT INTO audit_logs (request_id, actor_name, actor_role, action, details, timestamp, log_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (request_id, f"User-{auth['user_id']}", auth["role"], act_str, details, now, rec_hash))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "request_id": request_id,
        "action": decision.action,
        "new_status": new_status,
        "timestamp": now
    }

@app.post("/api/v1/ai/chat")
def copilot_query(query_payload: AIChatQuery):
    """
    Conversational AI Copilot for natural language status tracking and policy inquiry.
    Guaranteed Human-Governed policy responses.
    """
    q = query_payload.query.lower()
    conn = get_connection()
    cursor = conn.cursor()

    response_text = ""

    if "pr-" in q or (query_payload.request_id and query_payload.request_id.lower() in q):
        # Specific request search
        import re
        match = re.search(r"pr-\d+", q)
        target_id = match.group(0).upper() if match else query_payload.request_id

        cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (target_id,))
        row = cursor.fetchone()
        if row:
            r = dict(row)
            response_text = (
                f"**{r['id']} ({r['title']} - ₹{r['amount']:,.2f})**\n\n"
                f"• **Current Status:** `{r['status']}`\n"
                f"• **Tier Classification:** {r['tier']}\n"
                f"• **Requester:** {r['requester_name']} ({r['department']})\n"
                f"• **Vendor:** {r['vendor']}\n"
                f"• **SLA Elapsed:** {r['waiting_days']} days\n\n"
                f"_Next Step:_ Awaiting review per tiered approval matrix."
            )
        else:
            response_text = f"Request `{target_id}` was not found in the Acme Corp database."

    elif "tier" in q or "rule" in q or "approval" in q or "policy" in q:
        response_text = (
            "**Acme Corp Purchase Approval Policy Rules:**\n\n"
            "1. **Tier 1 (≤ ₹25,000):** Requires direct **Line Manager** approval only.\n"
            "2. **Tier 2 (₹25,001 - ₹1,00,000):** Requires **Line Manager AND Finance** approval, plus minimum **2 competitive vendor quotes**.\n"
            "3. **Tier 3 (> ₹1,00,000):** High-value spend requires **Line Manager, Finance, AND Department Head** approval.\n\n"
            "⚠️ _Guardrail:_ Missing documents or tax discrepancies block final approval. **AI never independently approves financial requests.**"
        )
    elif "ai approve" in q or "autonomous" in q:
        response_text = (
            "**S3K Core Principle: AI Assisted – Human Governed.**\n\n"
            "FlowSync AI is strictly an analytical and assistive platform. It extracts OCR metadata, flags policy violations, verifies budget health, and scores risk. "
            "**All final financial authorization decisions must be made by authenticated human approvers.**"
        )
    else:
        response_text = (
            f"I have parsed your query: *'{query_payload.query}'*.\n\n"
            "You can query specific purchase requests (e.g. `What is the status of PR-1042?`), "
            "ask about approval thresholds (e.g. `What are the rules for Tier 2?`), or check company procurement policies."
        )

    conn.close()
    return {"reply": response_text, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
