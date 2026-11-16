"""
Comprehensive Automated UAT & Security Test Suite
FlowSync / BuyOps AI - S3K Case Study 03
Verifies all 6 critical criteria:
1. JWT Authentication & Password Hash Verification (Anti-Spoofing)
2. Object-Level Access Control (IDOR / BOLA Prevention)
3. Strict Sequential Approval State Machine (Role Authorization & Premature Approval Defense)
4. Policy Gatekeeper: Missing Documents Block Final Approval
5. Cryptographic SHA-256 Duplicate Invoice Collision Detection
6. Verifiable Hash-Chained Audit Ledger Integrity
7. Context-Grounded Semantic AI Copilot
"""

import sys
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

def test_2_object_level_authorization_idor():
    """
    CRITERION 2: Object-Level Authorization (IDOR Defense).
    Requester B (Lisa Park / u2) attempts to query Requester A's request (PR-1042 belonging to Sarah Chen / u1).
    Expected: HTTP 403 Forbidden with security violation message.
    """
    lisa_token = get_auth_token("lisa.park", "password123")
    headers = {"Authorization": f"Bearer {lisa_token}"}

    response = client.get("/api/v1/requests/PR-1042", headers=headers)
    assert response.status_code == 403
    assert "Security Violation" in response.json()["detail"]
    print("✓ Test 2 Passed: IDOR attack blocked. User cannot view another employee's request.")

def test_3_sequential_approval_state_machine():
    """
    CRITERION 3: Strict Sequential Approvals & Role Authorization.
    - PR-1043 is in PENDING_FINANCE (Stage 2).
    - Department Head (Rajesh Patel) attempts to approve prematurely.
    - Expected: HTTP 403 Forbidden.
    - Finance Manager (Neha Gupta) approves -> transitions to APPROVED.
    """
    depthead_token = get_auth_token("rajesh.patel", "password123")
    finance_token = get_auth_token("neha.gupta", "password123")

    # 1. Dept Head attempts premature approval of Stage 2 (bypassing Finance)
    dh_headers = {"Authorization": f"Bearer {depthead_token}"}
    res_premature = client.post(
        "/api/v1/requests/PR-1043/decision",
        json={"request_id": "PR-1043", "action": "Approve", "comments": "Attempting premature sign-off"},
        headers=dh_headers
    )
    assert res_premature.status_code == 403
    assert "Stage 2 requires Finance Manager approval" in res_premature.json()["detail"]

    # 2. Finance approves authorized stage
    fin_headers = {"Authorization": f"Bearer {finance_token}"}
    res_fin = client.post(
        "/api/v1/requests/PR-1043/decision",
        json={"request_id": "PR-1043", "action": "Approve", "comments": "Budget code confirmed."},
        headers=fin_headers
    )
    assert res_fin.status_code == 200
    assert res_fin.json()["new_status"] == "APPROVED"
    print("✓ Test 3 Passed: Sequential approval gates strictly enforced. No stage bypassing permitted.")

def test_4_missing_documents_gatekeeper():
    """
    CRITERION 4: Missing Documents Block Final Approval.
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
    print("✓ Test 4 Passed: Missing documents gatekeeper successfully blocks approval.")

def test_5_cryptographic_duplicate_invoice_detection():
    """
    CRITERION 5: Real Cryptographic Duplicate Invoice Detection.
    Submitting an invoice with the exact SHA-256 hash of a historical invoice triggers CRITICAL RISK.
    """
    import hashlib
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
    print("✓ Test 5 Passed: Cryptographic SHA-256 duplicate collision detected and blocked.")

def test_6_verifiable_hash_chain_integrity():
    """
    CRITERION 6: Verifiable Hash-Chained Audit Ledger.
    Validates that every audit row is linked via SHA-256 hash pointer to the previous block.
    """
    verification = verify_audit_hash_chain()
    assert verification["chain_valid"] is True
    assert verification["tamper_detected"] is False
    assert verification["total_blocks"] >= 12
    print(f"✓ Test 6 Passed: Audit ledger hash-chain 100% verified across {verification['total_blocks']} blocks.")

def test_7_context_grounded_ai_copilot():
    """
    CRITERION 7: Context-Grounded Semantic AI Copilot.
    Verifies that AI copilot answers are semantically grounded in company procurement policies.
    """
    sarah_token = get_auth_token("sarah.chen", "password123")
    headers = {"Authorization": f"Bearer {sarah_token}"}

    query = {"query": "What are the rules for Tier 3 purchases above 100000?"}
    res = client.post("/api/v1/ai/chat", json=query, headers=headers)
    assert res.status_code == 200
    data = res.json()
    print("AI Copilot Response Data:", data)
    assert "Tier 3" in data["reply"]
    assert "Department Head" in data["reply"] or "Dept Head" in data["reply"] or "Head" in data["reply"]
    assert "POL-01-TIERS" in data["grounded_clause"]
    print(f"✓ Test 7 Passed: AI Copilot grounded via clause {data['grounded_clause']} ({data['engine']}).")

if __name__ == "__main__":
    reset_db()
    test_1_jwt_authentication_and_tamper_defense()
    test_2_object_level_authorization_idor()
    test_3_sequential_approval_state_machine()
    test_4_missing_documents_gatekeeper()
    test_5_cryptographic_duplicate_invoice_detection()
    test_6_verifiable_hash_chain_integrity()
    test_7_context_grounded_ai_copilot()
    print("\n🎉 ALL 7 INTEGRATION & SECURITY TESTS PASSED WITH 100% VERIFICATION!")
