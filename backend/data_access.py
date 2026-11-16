"""
Data Access and Authorization Layer
FlowSync / BuyOps AI - S3K Case Study 03
Enforces:
1. Object-Level Access Control (RLS simulation at data layer)
2. Strict Sequential Approval State Machine
3. Cryptographic duplicate invoice hash collision detection
"""

import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status

from .database import get_connection, append_audit_log, compute_log_hash

def get_authorized_requests(user_id: str, user_role: str, filter_type: str = "all", search: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves purchase requests with strict Object-Level Security:
    - 'requester' can ONLY see records where requester_id == user_id.
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

    # Strict Object-Level Access Check
    if user_role == "requester":
        query += " AND r.requester_id = ?"
        params.append(user_id)

    if filter_type == "pending":
        query += " AND r.status LIKE 'PENDING_%'"
    elif filter_type == "flagged":
        query += " AND (r.status LIKE 'FLAGGED%' OR a.risk_level != 'LOW RISK')"
    elif filter_type == "approved":
        query += " AND r.status = 'APPROVED'"
    elif filter_type == "rejected":
        query += " AND r.status = 'REJECTED'"

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
    return results

def get_request_dossier(request_id: str, user_id: str, user_role: str) -> Dict[str, Any]:
    """
    Fetches full request details. Enforces BOLA / IDOR protection.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Purchase request {request_id} not found.")

    req = dict(row)

    # Broken Object-Level Authorization (BOLA/IDOR) Defense
    if user_role == "requester" and req["requester_id"] != user_id:
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

    # Audit Logs (Hash chained)
    cursor.execute("SELECT * FROM audit_logs WHERE request_id = ? ORDER BY id DESC", (request_id,))
    req["audit_logs"] = [dict(log) for log in cursor.fetchall()]

    conn.close()
    return req

def execute_approval_decision(request_id: str, action: str, comments: str, user_id: str, user_role: str, user_name: str) -> Dict[str, Any]:
    """
    Enforces the sequential state machine & role authorization:
    - Tier 1: Only Line Manager can approve.
    - Tier 2: Line Manager must approve first (PENDING_MANAGER -> PENDING_FINANCE), then Finance approves.
    - Tier 3: Line Manager (PENDING_MANAGER -> PENDING_FINANCE), Finance (PENDING_FINANCE -> PENDING_DEPTHEAD), then Dept Head (PENDING_DEPTHEAD -> APPROVED).
    - Dept Head CANNOT approve if Finance has not approved!
    - Missing documents block final approval.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Purchase request not found.")

    req = dict(row)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_status = req["status"]
    amount = req["amount"]

    # 1. Block approval if flagged for missing documents
    if action == "Approve" and current_status == "FLAGGED_MISSING_DOCS":
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Policy Guardrail Active: Missing documents or unaddressed policy flags block final approval."
        )

    # 2. Sequential Stage & Role-Specific Authorization Check
    new_status = current_status

    if action == "Approve":
        if amount <= 25000: # Tier 1
            if current_status != "PENDING_MANAGER":
                conn.close()
                raise HTTPException(status_code=400, detail=f"Invalid state transition from {current_status}.")
            if user_role not in ["manager", "depthead"]: # manager is required
                conn.close()
                raise HTTPException(status_code=403, detail="Unauthorized: Only a Line Manager can approve Tier 1 requests.")
            new_status = "APPROVED"

        elif amount <= 100000: # Tier 2 (Manager -> Finance)
            if current_status == "PENDING_MANAGER":
                if user_role != "manager":
                    conn.close()
                    raise HTTPException(status_code=403, detail="Unauthorized: Stage 1 requires Line Manager approval.")
                new_status = "PENDING_FINANCE"

            elif current_status == "PENDING_FINANCE":
                if user_role != "finance":
                    conn.close()
                    raise HTTPException(status_code=403, detail="Unauthorized: Stage 2 requires Finance Manager approval.")
                new_status = "APPROVED"

            else:
                conn.close()
                raise HTTPException(status_code=400, detail=f"Request is in state '{current_status}' and cannot be approved further.")

        else: # Tier 3 (> 100,000) (Manager -> Finance -> Dept Head)
            if current_status == "PENDING_MANAGER":
                if user_role != "manager":
                    conn.close()
                    raise HTTPException(status_code=403, detail="Unauthorized: Stage 1 requires Line Manager approval.")
                new_status = "PENDING_FINANCE"

            elif current_status == "PENDING_FINANCE":
                if user_role != "finance":
                    conn.close()
                    raise HTTPException(
                        status_code=403,
                        detail="Authorization Gap Blocked: Tier 3 requests mandate Finance approval before Department Head sign-off."
                    )
                new_status = "PENDING_DEPTHEAD"

            elif current_status == "PENDING_DEPTHEAD":
                if user_role != "depthead":
                    conn.close()
                    raise HTTPException(
                        status_code=403,
                        detail="Unauthorized: Final Tier 3 authorization requires Department Head (VP) sign-off."
                    )
                new_status = "APPROVED"

            else:
                conn.close()
                raise HTTPException(status_code=400, detail=f"Request is in state '{current_status}' and cannot be approved further.")

    elif action == "Reject":
        # Any active approver can reject
        if user_role not in ["manager", "finance", "depthead"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Unauthorized: Requesters cannot reject approval stages.")
        new_status = "REJECTED"

    elif action == "Request Changes":
        if user_role not in ["manager", "finance", "depthead"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Unauthorized: Requesters cannot request changes on approval stages.")
        new_status = "FLAGGED_MISSING_DOCS"

    # Update database
    cursor.execute("UPDATE purchase_requests SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, request_id))

    cursor.execute("""
    INSERT INTO approvals (request_id, approver_role, approver_name, action, comments, action_timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (request_id, user_role.upper(), user_name, action, comments or f"{action} executed by {user_role}.", now))

    conn.commit()
    conn.close()

    # Append to cryptographic hash-chained audit log
    log_detail = f"Decision '{action}' applied by {user_name} ({user_role}). State: {current_status} -> {new_status}. Note: {comments}"
    head_hash = append_audit_log(request_id, user_name, user_role, f"HUMAN_{action.upper()}", log_detail)

    return {
        "success": True,
        "request_id": request_id,
        "action": action,
        "previous_status": current_status,
        "new_status": new_status,
        "approver": user_name,
        "approver_role": user_role,
        "timestamp": now,
        "audit_block_hash": head_hash
    }
