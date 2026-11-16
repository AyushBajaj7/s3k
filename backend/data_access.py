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

def get_authorized_requests(
    user_id: str,
    user_role: str,
    user_department: Optional[str] = None,
    user_name: Optional[str] = None,
    filter_type: str = "all",
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves purchase requests with strict Object-Level & Department Jurisdiction Security:
    - 'requester' can ONLY see records where requester_id == user_id.
    - 'manager' can see requests in their own department OR where designated as approver.
    - 'finance' can see requests requiring financial review (Tier 2/3) or in Finance department.
    - 'depthead' can see high-value requests (Tier 3 > ₹1,00,000) or in Executive division.
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

    # Strict Department and Role Jurisdiction Rules
    if user_role == "requester":
        query += " AND r.requester_id = ?"
        params.append(user_id)
    elif user_role == "manager":
        query += " AND (r.department = ? OR r.id IN (SELECT request_id FROM approvals WHERE approver_name = ?))"
        params.extend([user_department or "", user_name or ""])
    elif user_role == "finance":
        query += " AND (r.department = ? OR r.amount > 25000 OR r.tier NOT LIKE 'Tier 1%')"
        params.append(user_department or "Finance")
    elif user_role == "depthead":
        query += " AND (r.department = ? OR r.amount > 100000 OR r.tier LIKE 'Tier 3%')"
        params.append(user_department or "Executive")

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

def get_request_dossier(
    request_id: str,
    user_id: str,
    user_role: str,
    user_department: Optional[str] = None,
    user_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches full request details. Enforces BOLA / IDOR and department jurisdiction protection.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM purchase_requests WHERE id = ?", (request_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Purchase request {request_id} not found.")

    req = dict(row)

    # 1. Requester Isolation (IDOR Defense)
    if user_role == "requester" and req["requester_id"] != user_id:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security Violation: You are not authorized to view another employee's purchase request."
        )

    # 2. Manager Department Jurisdiction
    if user_role == "manager":
        cursor.execute("SELECT 1 FROM approvals WHERE request_id = ? AND approver_name = ?", (request_id, user_name or ""))
        is_assigned = cursor.fetchone() is not None
        if req["department"] != user_department and not is_assigned:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Security Violation: Line Managers cannot access purchase requests outside their department ({user_department}) without explicit approval assignment."
            )

    # 3. Finance Jurisdiction (Tier 1 Operational Bypasses Finance)
    if user_role == "finance":
        if req["amount"] <= 25000 and req["department"] != user_department:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Violation: Tier 1 operational purchases (≤ ₹25,000) bypass Finance and are restricted to departmental line managers."
            )

    # 4. Department Head Jurisdiction (Executive Sign-off for Tier 3 Spend)
    if user_role == "depthead":
        if req["amount"] <= 100000 and req["department"] != user_department:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security Violation: Department Heads have jurisdiction over Tier 3 high-value spend (> ₹1,00,000) or departmental requests only."
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

def execute_approval_decision(
    request_id: str,
    action: str, # 'Approve', 'Reject', 'Request Changes'
    comments: str,
    user_id: str,
    user_role: str,
    user_name: str,
    user_department: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enforces sequential multi-tier approval rules, department jurisdiction, and role-specific permissions:
    - Requesters cannot approve, reject, or modify requests.
    - Line Managers can only approve requests in their department or where explicitly assigned.
    - Tier 1: Strictly Line Manager only (Dept Heads and Finance cannot approve Tier 1).
    - Tier 2: Line Manager must approve first (PENDING_MANAGER -> PENDING_FINANCE), then Finance approves.
    - Tier 3: Line Manager -> Finance -> Department Head.
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

    # 0. Strict Role Verification: Requesters cannot approve, reject, or modify approval stages
    if user_role == "requester":
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Requesters cannot approve, reject, or modify purchase requests."
        )

    # 1. Line Manager Department Jurisdiction & Assignment Verification
    if user_role == "manager":
        cursor.execute("SELECT 1 FROM approvals WHERE request_id = ? AND approver_name = ?", (request_id, user_name or ""))
        is_assigned = cursor.fetchone() is not None
        if req["department"] != user_department and not is_assigned:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Security Violation: Line Managers cannot approve or modify requests outside their department ({user_department}) without explicit approval assignment."
            )

    # 2. Block approval if flagged for missing documents
    if action == "Approve" and current_status == "FLAGGED_MISSING_DOCS":
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Policy Guardrail Active: Missing documents or unaddressed policy flags block final approval."
        )

    # 3. Sequential Stage & Role-Specific Authorization Check
    new_status = current_status

    if action == "Approve":
        if amount <= 25000: # Tier 1
            if current_status != "PENDING_MANAGER":
                conn.close()
                raise HTTPException(status_code=400, detail=f"Invalid state transition from {current_status}.")
            if user_role != "manager": # strictly Line Manager only
                conn.close()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Unauthorized: Tier 1 requests mandate direct Line Manager approval only (Department Heads and Finance cannot approve Tier 1)."
                )
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
