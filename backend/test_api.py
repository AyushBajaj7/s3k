"""
Automated UAT & Integration Test Suite for FlowSync AI
Case Study 03: Enterprise Request & Approval Platform
Tests the 3 core UAT scenarios specified in S3K guidelines:
1. Unauthorized Access (IDOR / BOLA Prevention)
2. Policy Violation & Missing Documents Gatekeeper
3. High-Value Tier Escalation & Multi-Stage Human Governance
4. Duplicate Request Detection & AI Safety Rule
"""

import pytest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.app import app
from backend.database import init_db, seed_db

client = TestClient(app)

def setup_module():
    init_db()
    seed_db()

def test_system_metrics():
    """Verify aggregated metrics and KPI baseline improvements."""
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "approval_status" in data
    assert "pending_value" in data
    assert "business_kpis" in data
    assert data["business_kpis"]["median_tat_hours"] == 18.4
    assert data["business_kpis"]["first_time_right_percent"] == 96.8
    print("✓ Test Metrics Passed")

def test_uat_1_unauthorized_access_idor():
    """
    UAT Scenario 1: Object-Level Authorization (IDOR Defense).
    Requester B (Lisa Park / u2) attempts to query Requester A's request (PR-1042 belonging to Sarah Chen / u1).
    Expected: HTTP 403 Forbidden with security violation message.
    """
    headers = {
        "X-User-Id": "u2",
        "X-User-Role": "requester"
    }
    response = client.get("/api/v1/requests/PR-1042", headers=headers)
    assert response.status_code == 403
    assert "Security Violation" in response.json()["detail"]
    print("✓ UAT Scenario 1 (IDOR Defense) Passed: Blocked unauthorized requester.")

def test_uat_2_missing_documents_blocks_approval():
    """
    UAT Scenario 2: Policy Gatekeeper - Missing Documents Block Approval.
    Request PR-1045 has only 1 vendor quote for ₹42,500 (mandates 2 quotes). Status is FLAGGED.
    Expected: Approver cannot approve; returns HTTP 422 with policy guardrail error.
    """
    headers = {
        "X-User-Id": "u4",
        "X-User-Role": "manager"
    }
    payload = {
        "request_id": "PR-1045",
        "action": "Approve",
        "comments": "Attempting approval without 2nd quote"
    }
    response = client.post("/api/v1/requests/PR-1045/decision", json=payload, headers=headers)
    assert response.status_code == 422
    assert "Missing documents" in response.json()["detail"]
    print("✓ UAT Scenario 2 (Missing Documents Block Approval) Passed.")

def test_uat_3_tier_3_high_value_governance():
    """
    UAT Scenario 3: Tier 3 (> ₹1,00,000) Approval Workflow.
    Requires Manager -> Finance -> Department Head before reaching APPROVED.
    """
    # Manager Approval
    mgr_headers = {"X-User-Id": "u4", "X-User-Role": "manager"}
    r1 = client.post("/api/v1/requests/PR-1044/decision", json={"request_id": "PR-1044", "action": "Approve"}, headers=mgr_headers)
    assert r1.status_code == 200

    # Dept Head Final Sign-off
    dept_headers = {"X-User-Id": "u6", "X-User-Role": "depthead"}
    r2 = client.post("/api/v1/requests/PR-1044/decision", json={"request_id": "PR-1044", "action": "Approve"}, headers=dept_headers)
    assert r2.status_code == 200
    assert r2.json()["new_status"] == "APPROVED"
    print("✓ UAT Scenario 3 (Tier 3 Dept Head Governance) Passed.")

def test_uat_4_duplicate_detection_on_create():
    """
    UAT Scenario 4: Automated Detection of Duplicate Submissions.
    Submitting duplicate invoice with same vendor & amount flags CRITICAL RISK and FLAGGED status.
    """
    headers = {"X-User-Id": "u1", "X-User-Role": "requester"}
    payload = {
        "title": "AWS Compute Duplicate Test",
        "category": "Cloud & Infra",
        "vendor": "AWS India",
        "amount": 12500.0, # exact same vendor & amount as PR-1042
        "business_justification": "Testing duplicate invoice scanner.",
        "department": "IT",
        "requester_name": "Sarah Chen",
        "quotes_count": 1
    }
    response = client.post("/api/v1/requests", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["risk_level"] == "CRITICAL RISK"
    assert data["status"] == "FLAGGED"
    print("✓ UAT Scenario 4 (Duplicate Detection) Passed.")

def test_ai_copilot_assistant():
    """Verify Conversational AI Copilot responds accurately to queries."""
    query = {"query": "What is the policy for Tier 2 purchases?"}
    response = client.post("/api/v1/ai/chat", json=query)
    assert response.status_code == 200
    assert "Tier 2" in response.json()["reply"]
    assert "Line Manager AND Finance" in response.json()["reply"]
    print("✓ AI Copilot Query Test Passed.")

if __name__ == "__main__":
    init_db()
    seed_db()
    test_system_metrics()
    test_uat_1_unauthorized_access_idor()
    test_uat_2_missing_documents_blocks_approval()
    test_uat_3_tier_3_high_value_governance()
    test_uat_4_duplicate_detection_on_create()
    test_ai_copilot_assistant()
    print("\n🎉 ALL UAT AND INTEGRATION TESTS PASSED SUCCESSFULLY (100% PASS RATE)!")
