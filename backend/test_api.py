"""
Comprehensive Automated UAT, Security & Workflow Test Suite
FlowSync / BuyOps AI - S3K Case Study 03
Verifies all core security, workflow, and AI criteria:
1. Real JWT Authentication & Password Hash Verification (Anti-Spoofing & Signature Checks)
2. Department Jurisdiction & Object-Level Access Control (RLS & IDOR Defense)
3. Tier 2 Sequential Approval State Machine (Role Authorization & Premature Approval Defense)
4. Tier 3 Comprehensive Sequential Lifecycle & Role Permission Guards:
   - Department Head cannot approve before Finance
   - Finance cannot approve before Manager
   - Requesters cannot approve or reject
   - Only Department Head can complete Tier 3
5. Policy Gatekeeper: Missing Documents Block Final Approval (HTTP 422)
6. Cryptographic SHA-256 Duplicate Invoice Collision Detection
7. Verifiable Hash-Chained Audit Ledger Integrity
8. Context-Grounded Semantic AI Copilot
"""

import sys
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.database import reset_db, verify_audit_hash_chain

client = TestClient(app)

def setup_module():
    reset_db()

def get_auth_token(username: str = "sarah.chen", password: str = "password123") -> str:
    """Helper to authenticate and obtain verified JWT token."""
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]

def test_1_jwt_authentication_and_tamper_defense():
    """
    CRITERION 1: Real Authentication & Anti-Spoofing.
    - Valid credentials return signed JWT.
    - Bad credentials return HTTP 401.
    - Missing token returns HTTP 401.
    - Tampered token returns HTTP 401.
    """
    # 1. Valid login
    res = client.post("/api/v1/auth/login", json={"username": "sarah.chen", "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    assert len(token) > 20

    # 2. Invalid password
    res_bad = client.post("/api/v1/auth/login", json={"username": "sarah.chen", "password": "wrongpassword"})
    assert res_bad.status_code == 401
    assert "Invalid credentials" in res_bad.json()["detail"]

    # 3. Missing Authorization header
    res_unauth = client.get("/api/v1/requests")
    assert res_unauth.status_code == 401
    assert "Authentication required" in res_unauth.json()["detail"]

    # 4. Tampered token
    tampered_headers = {"Authorization": f"Bearer {token[:-5]}XXXXX"}
    res_tampered = client.get("/api/v1/requests", headers=tampered_headers)
    assert res_tampered.status_code == 401
    assert "Invalid token signature" in res_tampered.json()["detail"]

    print("✓ Test 1 Passed: Real JWT Authentication & Signature Verification active.")

def test_2_department_and_object_level_access_control():
    """
    CRITERION 2: Object-Level Authorization & Department Jurisdiction (RLS/IDOR Defense).
    - Requester B (Lisa Park / Marketing) cannot query Requester A's request (PR-1042 / IT) -> HTTP 403.
    - Finance cannot inspect Tier 1 operational spend of another department (bypasses Finance) -> HTTP 403.
    - Dept Head cannot inspect non-Tier 3 requests of another department -> HTTP 403.
    """
    lisa_token = get_auth_token("lisa.park", "password123")
    finance_token = get_auth_token("neha.gupta", "password123")
    depthead_token = get_auth_token("rajesh.patel", "password123")

    # 1. Requester Isolation (IDOR Defense)
    res_lisa = client.get("/api/v1/requests/PR-1042", headers={"Authorization": f"Bearer {lisa_token}"})
    assert res_lisa.status_code == 403
    assert "Security Violation" in res_lisa.json()["detail"]

    # 2. Finance Jurisdiction (Tier 1 operational spend <= 25,000 bypasses Finance)
    res_fin = client.get("/api/v1/requests/PR-1042", headers={"Authorization": f"Bearer {finance_token}"})
    assert res_fin.status_code == 403
    assert "Tier 1 operational purchases (≤ ₹25,000) bypass Finance" in res_fin.json()["detail"]

    # 3. Dept Head Jurisdiction (Non-Tier-3 requests of other departments excluded)
    res_dh = client.get("/api/v1/requests/PR-1043", headers={"Authorization": f"Bearer {depthead_token}"})
    assert res_dh.status_code == 403
    assert "Department Heads have jurisdiction over Tier 3 high-value spend" in res_dh.json()["detail"]

    # 4. Out-of-Department Manager Approval Guard
    # Lisa Park (Marketing) creates a departmental Tier 1 purchase
    mkt_payload = {
        "title": "Marketing Design Templates",
        "category": "Marketing",
        "vendor": "Canva Enterprise",
        "amount": 15000.0,
        "business_justification": "Social media creative design assets.",
        "department": "Marketing",
        "requester_name": "Lisa Park",
        "invoice_sha256": hashlib.sha256(b"CANVA_MARKETING_INV_111").hexdigest(),
        "quotes_count": 1
    }
    create_res = client.post("/api/v1/requests", json=mkt_payload, headers={"Authorization": f"Bearer {lisa_token}"})
    assert create_res.status_code == 201
    mkt_id = create_res.json()["request_id"]

    # Arun Verma (Engineering Manager) attempts to approve Marketing request -> HTTP 403
    manager_token = get_auth_token("arun.verma", "password123")
    res_unauthorized_mgr = client.post(
        f"/api/v1/requests/{mkt_id}/decision",
        json={"request_id": mkt_id, "action": "Approve", "comments": "Engineering manager approving Marketing"},
        headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert res_unauthorized_mgr.status_code == 403
    assert "Line Managers cannot approve or modify requests outside their department" in res_unauthorized_mgr.json()["detail"]

    # 5. Tier 1 Line Manager Exclusivity (Dept Heads cannot approve Tier 1)
    res_dh_tier1 = client.post(
        f"/api/v1/requests/{mkt_id}/decision",
        json={"request_id": mkt_id, "action": "Approve", "comments": "Dept Head attempting Tier 1 sign-off"},
        headers={"Authorization": f"Bearer {depthead_token}"}
    )
    assert res_dh_tier1.status_code == 403
    assert "Tier 1 requests mandate direct Line Manager approval only" in res_dh_tier1.json()["detail"]

    print("✓ Test 2 Passed: Department jurisdiction, out-of-dept manager lock, and Tier 1 Line Manager exclusivity verified.")

def test_3_tier_2_sequential_approval_state_machine():
    """
    CRITERION 3: Tier 2 Sequential Approvals & Role Authorization.
    - PR-1043 is in PENDING_FINANCE (Stage 2).
    - Department Head attempts premature approval of Stage 2 -> HTTP 403 Forbidden.
    - Finance Manager approves Stage 2 -> Transitions to APPROVED.
    """
    depthead_token = get_auth_token("rajesh.patel", "password123")
    finance_token = get_auth_token("neha.gupta", "password123")

    # 1. Dept Head attempts premature approval of Stage 2 (bypassing Finance)
    res_premature = client.post(
        "/api/v1/requests/PR-1043/decision",
        json={"request_id": "PR-1043", "action": "Approve", "comments": "Attempting premature sign-off"},
        headers={"Authorization": f"Bearer {depthead_token}"}
    )
    assert res_premature.status_code == 403
    assert "Stage 2 requires Finance Manager approval" in res_premature.json()["detail"]

    # 2. Finance approves authorized stage
    res_fin = client.post(
        "/api/v1/requests/PR-1043/decision",
        json={"request_id": "PR-1043", "action": "Approve", "comments": "Budget code confirmed."},
        headers={"Authorization": f"Bearer {finance_token}"}
    )
    assert res_fin.status_code == 200
    assert res_fin.json()["new_status"] == "APPROVED"
    print("✓ Test 3 Passed: Tier 2 sequential approval gates strictly enforced.")

def test_4_tier_3_comprehensive_approval_lifecycle_and_role_guards():
    """
    CRITERION 4: Tier 3 Sequential Lifecycle & Role Permission Guards.
    Proves all 4 mandatory conditions:
    1. Finance cannot approve before Manager (Stage 1).
    2. Department Head cannot approve before Finance (Stage 1 & Stage 2).
    3. Requesters cannot approve or reject.
    4. Only Department Head can complete Tier 3 (Stage 3).
    """
    requester_token = get_auth_token("sarah.chen", "password123")
    manager_token = get_auth_token("arun.verma", "password123")
    finance_token = get_auth_token("neha.gupta", "password123")
    depthead_token = get_auth_token("rajesh.patel", "password123")

    # Step A: Create a brand new Tier 3 request (> ₹1,00,000, 2 competitive quotes)
    dummy_invoice_hash = hashlib.sha256(b"ORACLE_CLOUD_DATABASE_PO_9999_2025_INR").hexdigest()
    create_payload = {
        "title": "Oracle Exadata Cloud Migration",
        "category": "Cloud & Infra",
        "vendor": "Oracle India",
        "amount": 350000.0,
        "business_justification": "Core database capacity scaling for enterprise ERP.",
        "department": "Engineering",
        "requester_name": "Priya Sharma",
        "invoice_sha256": dummy_invoice_hash,
        "quotes_count": 2
    }
    create_res = client.post("/api/v1/requests", json=create_payload, headers={"Authorization": f"Bearer {requester_token}"})
    assert create_res.status_code == 201
    tier3_id = create_res.json()["request_id"]
    assert create_res.json()["status"] == "PENDING_MANAGER"

    # Guard 1: Finance CANNOT approve before Manager
    res_fin_early = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Finance jumping ahead"},
        headers={"Authorization": f"Bearer {finance_token}"}
    )
    assert res_fin_early.status_code == 403
    assert "Stage 1 requires Line Manager approval" in res_fin_early.json()["detail"]

    # Guard 2: Department Head CANNOT approve before Finance & Manager
    res_dh_early = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Dept Head jumping ahead"},
        headers={"Authorization": f"Bearer {depthead_token}"}
    )
    assert res_dh_early.status_code == 403
    assert "Stage 1 requires Line Manager approval" in res_dh_early.json()["detail"]

    # Guard 3: Requesters CANNOT approve or reject
    res_req_approve = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Self-approving"},
        headers={"Authorization": f"Bearer {requester_token}"}
    )
    assert res_req_approve.status_code == 403
    assert "Requesters cannot approve, reject, or modify" in res_req_approve.json()["detail"]

    res_req_reject = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Reject", "comments": "Self-rejecting"},
        headers={"Authorization": f"Bearer {requester_token}"}
    )
    assert res_req_reject.status_code == 403
    assert "Requesters cannot approve, reject, or modify" in res_req_reject.json()["detail"]

    # Stage 1: Line Manager approves properly
    res_mgr = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Line Manager verified architecture."},
        headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert res_mgr.status_code == 200
    assert res_mgr.json()["new_status"] == "PENDING_FINANCE"

    # Guard 4: Department Head CANNOT approve at Stage 2 before Finance
    res_dh_stage2 = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Dept Head bypassing Finance"},
        headers={"Authorization": f"Bearer {depthead_token}"}
    )
    assert res_dh_stage2.status_code == 403
    assert "Tier 3 requests mandate Finance approval before Department Head sign-off" in res_dh_stage2.json()["detail"]

    # Stage 2: Finance approves properly
    res_fin = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Finance verified Q3 budget allocation."},
        headers={"Authorization": f"Bearer {finance_token}"}
    )
    assert res_fin.status_code == 200
    assert res_fin.json()["new_status"] == "PENDING_DEPTHEAD"

    # Guard 5: Line Manager or Finance CANNOT complete Stage 3
    res_mgr_stage3 = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Manager trying to finalize Tier 3"},
        headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert res_mgr_stage3.status_code == 403
    assert "Final Tier 3 authorization requires Department Head (VP) sign-off" in res_mgr_stage3.json()["detail"]

    res_fin_stage3 = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "Finance trying to finalize Tier 3"},
        headers={"Authorization": f"Bearer {finance_token}"}
    )
    assert res_fin_stage3.status_code == 403
    assert "Final Tier 3 authorization requires Department Head (VP) sign-off" in res_fin_stage3.json()["detail"]

    # Guard 6: ONLY Department Head can complete Tier 3
    res_dh_final = client.post(
        f"/api/v1/requests/{tier3_id}/decision",
        json={"request_id": tier3_id, "action": "Approve", "comments": "VP Engineering final executive sign-off."},
        headers={"Authorization": f"Bearer {depthead_token}"}
    )
    assert res_dh_final.status_code == 200
    assert res_dh_final.json()["new_status"] == "APPROVED"

    print("✓ Test 4 Passed: Tier 3 sequential lifecycle and all 4 role permission guards verified.")

def test_5_missing_documents_gatekeeper():
    """
    CRITERION 5: Missing Documents Block Final Approval.
    Request PR-1045 has status FLAGGED_MISSING_DOCS (missing second vendor quote).
    Expected: HTTP 422 Unprocessable Entity.
    """
    manager_token = get_auth_token("arun.verma", "password123")
    headers = {"Authorization": f"Bearer {manager_token}"}

    res = client.post(
        "/api/v1/requests/PR-1045/decision",
        json={"request_id": "PR-1045", "action": "Approve", "comments": "Trying to bypass missing docs"},
        headers=headers
    )
    assert res.status_code == 422
    assert "Missing documents" in res.json()["detail"]
    print("✓ Test 5 Passed: Missing documents gatekeeper successfully blocks approval.")

def test_6_cryptographic_duplicate_invoice_detection():
    """
    CRITERION 6: Real Cryptographic Duplicate Invoice Detection.
    Submitting an invoice with the exact SHA-256 hash of a historical invoice triggers CRITICAL RISK.
    """
    known_hash = hashlib.sha256(b"AWS_INVOICE_INV9821_20250218_12500_INR").hexdigest()

    sarah_token = get_auth_token("sarah.chen", "password123")
    headers = {"Authorization": f"Bearer {sarah_token}"}

    payload = {
        "title": "AWS Compute Duplicate Fraud Test",
        "category": "Cloud & Infra",
        "vendor": "AWS India",
        "amount": 12500.0,
        "business_justification": "Testing cryptographic hash collision scanner.",
        "department": "IT",
        "requester_name": "Sarah Chen",
        "invoice_sha256": known_hash, # exact collision
        "quotes_count": 1
    }

    res = client.post("/api/v1/requests", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["risk_level"] == "CRITICAL RISK"
    assert data["status"] == "FLAGGED_MISSING_DOCS"
    print("✓ Test 6 Passed: Cryptographic SHA-256 duplicate collision detected and blocked.")

def test_7_verifiable_hash_chain_integrity():
    """
    CRITERION 7: Verifiable Hash-Chained Audit Ledger.
    Validates that every audit row is linked via SHA-256 hash pointer to the previous block.
    """
    verification = verify_audit_hash_chain()
    assert verification["chain_valid"] is True
    assert verification["tamper_detected"] is False
    assert verification["total_blocks"] >= 12
    print(f"✓ Test 7 Passed: Audit ledger hash-chain 100% verified across {verification['total_blocks']} blocks.")

def test_8_context_grounded_ai_copilot():
    """
    CRITERION 8: Context-Grounded Semantic AI Copilot.
    Verifies that AI copilot answers are semantically grounded in company procurement policies.
    """
    sarah_token = get_auth_token("sarah.chen", "password123")
    headers = {"Authorization": f"Bearer {sarah_token}"}

    query = {"query": "What are the rules for Tier 3 purchases above 100000?"}
    res = client.post("/api/v1/ai/chat", json=query, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "Tier 3" in data["reply"]
    assert "Department Head" in data["reply"] or "Dept Head" in data["reply"] or "Head" in data["reply"]
    assert "POL-01-TIERS" in data["grounded_clause"]
    print(f"✓ Test 8 Passed: AI Copilot grounded via clause {data['grounded_clause']} ({data['engine']}).")

if __name__ == "__main__":
    reset_db()
    test_1_jwt_authentication_and_tamper_defense()
    test_2_department_and_object_level_access_control()
    test_3_tier_2_sequential_approval_state_machine()
    test_4_tier_3_comprehensive_approval_lifecycle_and_role_guards()
    test_5_missing_documents_gatekeeper()
    test_6_cryptographic_duplicate_invoice_detection()
    test_7_verifiable_hash_chain_integrity()
    test_8_context_grounded_ai_copilot()
    print("\n🎉 ALL 8 INTEGRATION & SECURITY TESTS PASSED WITH 100% VERIFICATION!")
