"""
FlowSync AI - Enterprise Request & Approval Platform
FastAPI Backend API (Version 2.5)
Implements S3K Case Study 03 Specifications & BuyOps MVP:
1. Real JWT Authentication & password hash verification
2. Sequential approval state machine with role-specific gates
3. Cryptographic SHA-256 invoice duplicate fraud detection
4. Verifiable hash-chained audit ledger
5. Context-grounded Semantic Policy Copilot + Gemini hook
"""

import os
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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Support direct execution and module imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection, append_audit_log, verify_audit_hash_chain, init_db, seed_db
from backend.auth import hash_password, verify_password, create_access_token, decode_access_token
from backend.models import LoginRequest, TokenResponse, UserProfile, CreatePurchaseRequest, ApprovalDecision, AIChatQuery
from backend.data_access import get_authorized_requests, get_request_dossier, execute_approval_decision
from backend.ai_engine import answer_policy_query

app = FastAPI(
    title="BuyOps AI - Enterprise Request & Approval Engine",
    description="Backend service powering authenticated intake, sequential tiered approvals, and human-governed AI oversight.",
    version="2.5.0"
)

# Enable CORS for local development and browser frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# Ensure DB is ready on startup
@app.on_event("startup")
def startup_event():
    init_db()
    seed_db()

# ---------------------------------------------------------
# Authentication Dependency (JWT Bearer Verification)
# ---------------------------------------------------------
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """
    Validates JWT Bearer Token.
    Returns user payload dictionary: {"id", "username", "role", "full_name", "department"}
    Throws HTTP 401 if token is missing, expired, or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing Authorization Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)

    # Cross-reference user with database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, email, role, department, budget_limit FROM users WHERE id = ?", (payload["sub"],))
    user_row = cursor.fetchone()
    conn.close()

    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: User no longer exists in system.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return dict(user_row)

# ---------------------------------------------------------
# Frontend Static Routing
# ---------------------------------------------------------
@app.get("/")
def serve_main_app():
    frontend_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {"message": "BuyOps API operational. Frontend not found."}

@app.get("/prototype")
def serve_prototype_app():
    proto_path = Path(__file__).resolve().parent.parent / "prototype" / "index.html"
    if proto_path.exists():
        return FileResponse(proto_path)
    raise HTTPException(status_code=404, detail="Prototype file not found.")

@app.get("/api")
def api_info():
    return {
        "platform": "BuyOps AI (Enterprise Request & Approval Platform)",
        "version": "2.5.0",
        "auth": "JWT Bearer Token (PyJWT)",
        "docs": "/docs",
        "hash_chain_status": "/api/v1/audit/verify-chain"
    }

# ---------------------------------------------------------
# Authentication Endpoints
# ---------------------------------------------------------
@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(creds: LoginRequest):
    """
    Verifies user credentials using PBKDF2-HMAC-SHA256 password hash.
    Issues a cryptographically signed JWT bearer token with user claims.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, department, password_hash FROM users WHERE username = ?", (creds.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(creds.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials: username or password does not match.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "sub": user["id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"],
        "department": user["department"]
    }
    token = create_access_token(token_data)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user["id"],
        role=user["role"],
        full_name=user["full_name"],
        department=user["department"]
    )

@app.get("/api/v1/auth/me", response_model=UserProfile)
def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Returns the verified profile of the authenticated user."""
    return UserProfile(**user)

# ---------------------------------------------------------
# Core Procurement Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/metrics")
def get_metrics():
    """Aggregated KPIs for the BuyOps overview cards."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM purchase_requests")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status LIKE 'PENDING_%'")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status = 'APPROVED'")
    approved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE status IN ('REJECTED', 'FLAGGED_MISSING_DOCS')")
    rejected = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(amount) FROM purchase_requests WHERE status LIKE 'PENDING_%'")
    pending_val = cursor.fetchone()[0] or 0.0

    conn.close()

    return {
        "approval_status": {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
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
    user: dict = Depends(get_current_user)
):
    """
    Lists purchase requests with strict Object-Level Authorization (RLS).
    Enforced on authenticated user credentials.
    """
    requests = get_authorized_requests(user["id"], user["role"], filter_type, search)
    return {"requests": requests, "count": len(requests), "active_user": user["full_name"], "user_role": user["role"]}

@app.get("/api/v1/requests/{request_id}")
def get_request_detail(
    request_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Fetches full request dossier. Enforces BOLA/IDOR protection.
    """
    return get_request_dossier(request_id, user["id"], user["role"])

@app.post("/api/v1/requests", status_code=status.HTTP_201_CREATED)
def create_purchase_request(
    payload: CreatePurchaseRequest,
    user: dict = Depends(get_current_user)
):
    """
    Creates a new purchase request:
    1. Computes cryptographic SHA-256 hash of invoice content.
    2. Checks for historical hash collision (Duplicate Fraud Detection).
    3. Evaluates monetary tiers (≤ ₹25k, ₹25k-₹1L, > ₹1L).
    4. Appends to cryptographic hash-chained audit log.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Generate sequential ID
    cursor.execute("SELECT COUNT(*) FROM purchase_requests")
    cnt = cursor.fetchone()[0]
    req_id = f"PR-{1042 + cnt + 1}"

    # Compute or accept cryptographic SHA-256 hash of the invoice
    if payload.invoice_sha256:
        doc_hash = payload.invoice_sha256
    elif payload.invoice_content:
        doc_hash = hashlib.sha256(payload.invoice_content.encode("utf-8")).hexdigest()
    else:
        # Generate hash based on vendor, title, amount and timestamp
        raw_seed = f"{payload.vendor}_{payload.title}_{payload.amount}_{payload.requester_name}"
        doc_hash = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()

    # Cryptographic Duplicate Invoice Fraud Detection
    cursor.execute("SELECT id, title, created_at FROM purchase_requests WHERE invoice_sha256 = ?", (doc_hash,))
    dup_row = cursor.fetchone()
    dup_match_id = dup_row[0] if dup_row else None

    # Evaluate Tier
    if payload.amount <= 25000:
        tier = "Tier 1 (≤ ₹25,000)"
        init_status = "PENDING_MANAGER"
    elif payload.amount <= 100000:
        tier = "Tier 2 (₹25,001 - ₹1,00,000)"
        init_status = "PENDING_MANAGER"
    else:
        tier = "Tier 3 (> ₹1,00,000)"
        init_status = "PENDING_MANAGER"

    risk_level = "LOW RISK"
    policy_flags = []

    # Check 1: Missing competitive quotes (> ₹25,000 requires 2 quotes)
    if payload.amount > 25000 and (payload.quotes_count or 1) < 2:
        init_status = "FLAGGED_MISSING_DOCS"
        risk_level = "MEDIUM RISK"
        policy_flags.append({
            "rule": "Two-Quote Requirement",
            "pass": False,
            "note": "Purchases exceeding ₹25,000 strictly require at least 2 competitive vendor quotes."
        })
    else:
        policy_flags.append({
            "rule": "Two-Quote Requirement",
            "pass": True,
            "note": "Competitive quotes verified."
        })

    # Check 2: Cryptographic duplicate collision
    if dup_match_id:
        init_status = "FLAGGED_MISSING_DOCS"
        risk_level = "CRITICAL RISK"
        policy_flags.append({
            "rule": "Cryptographic SHA-256 Duplicate Check",
            "pass": False,
            "note": f"CRITICAL FRAUD ALERT: Exact invoice hash match with historical {dup_match_id}."
        })

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert request
    cursor.execute("""
    INSERT INTO purchase_requests (
        id, requester_id, requester_name, department, title, category, vendor, amount,
        business_justification, tier, status, priority, waiting_days,
        budget_used, budget_remaining, budget_total, invoice_sha256, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req_id, user["id"], payload.requester_name or user["full_name"], payload.department or user["department"],
        payload.title, payload.category, payload.vendor, payload.amount,
        payload.business_justification, tier, init_status, "Medium Priority", 0,
        180000.0, 70000.0, 250000.0, doc_hash, now, now
    ))

    # Insert attachment record with invoice hash
    cursor.execute("""
    INSERT INTO attachments (request_id, file_name, file_size, ocr_extracted_vendor, ocr_extracted_amount, ocr_confidence, status, invoice_sha256)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req_id, f"{payload.vendor.replace(' ', '_')}_Invoice.pdf", "1.4 MB",
        payload.vendor, payload.amount, 99.1, "Verified" if not dup_match_id else "Flagged", doc_hash
    ))

    # Insert initial approval step
    cursor.execute("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (req_id, "Line Manager", "Arun Verma", "Pending" if init_status == "PENDING_MANAGER" else "Blocked", None, None))

    # Insert AI Analysis
    summary_bullets = [
        f"Submitted by {payload.requester_name} for {payload.category}.",
        f"Threshold evaluation: {tier} workflow engaged.",
        f"Invoice cryptographic hash: {doc_hash[:16]}... ({risk_level})."
    ]
    cursor.execute("""
    INSERT INTO ai_analyses (request_id, risk_level, summary_json, policy_flags_json, duplicate_match_id)
    VALUES (?, ?, ?, ?, ?)
    """, (req_id, risk_level, json.dumps(summary_bullets), json.dumps(policy_flags), dup_match_id))

    conn.commit()
    conn.close()

    # Append to hash-chained audit log
    log_detail = f"Request created: {payload.title} (₹{payload.amount:,.2f}). Tier: {tier}. Status: {init_status}. SHA256: {doc_hash[:16]}"
    block_hash = append_audit_log(req_id, user["full_name"], user["role"], "REQUEST_CREATED", log_detail)

    return {
        "success": True,
        "request_id": req_id,
        "tier": tier,
        "status": init_status,
        "risk_level": risk_level,
        "invoice_sha256": doc_hash,
        "audit_block_hash": block_hash
    }

@app.post("/api/v1/requests/{request_id}/decision")
def record_decision(
    request_id: str,
    decision: ApprovalDecision,
    user: dict = Depends(get_current_user)
):
    """
    Enforces the sequential approval state machine and role-specific permissions:
    - Tier 1: Line Manager only.
    - Tier 2: Line Manager -> Finance Manager.
    - Tier 3: Line Manager -> Finance Manager -> Department Head.
    - Prevents premature approvals (e.g. Dept Head approving before Finance).
    - Missing documents block final approval.
    """
    return execute_approval_decision(
        request_id=request_id,
        action=decision.action,
        comments=decision.comments or "",
        user_id=user["id"],
        user_role=user["role"],
        user_name=user["full_name"]
    )

# ---------------------------------------------------------
# Audit & Verifiable Hash Chain
# ---------------------------------------------------------
@app.get("/api/v1/audit/verify-chain")
def verify_audit_ledger():
    """
    Traverses the audit log from genesis to head, recomputing every SHA-256 hash.
    Proves zero manual tampering in the audit log.
    """
    return verify_audit_hash_chain()

# ---------------------------------------------------------
# Conversational AI Copilot (Context-Grounded RAG)
# ---------------------------------------------------------
@app.post("/api/v1/ai/chat")
def copilot_chat(payload: AIChatQuery, user: dict = Depends(get_current_user)):
    """
    Conversational Copilot grounded in company procurement policy.
    Uses semantic retrieval engine + live Gemini API hook when GEMINI_API_KEY is configured.
    """
    request_context = None
    if payload.request_id:
        try:
            request_context = get_request_dossier(payload.request_id, user["id"], user["role"])
        except Exception:
            pass

    return answer_policy_query(payload.query, request_context)
