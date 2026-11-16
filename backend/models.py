"""
Pydantic Models and Data Contracts for FlowSync AI
Case Study 03: Enterprise Request & Approval Platform
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class UserAuth(BaseModel):
    username: str
    role: str # 'requester', 'manager', 'finance', 'depthead'

class CreatePurchaseRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    category: str
    vendor: str
    amount: float = Field(..., gt=0)
    business_justification: str = Field(..., min_length=10)
    department: Optional[str] = "Engineering"
    requester_name: Optional[str] = "Sarah Chen"
    has_invoice: Optional[bool] = True
    quotes_count: Optional[int] = 1

class ApprovalDecision(BaseModel):
    request_id: str
    action: str # 'Approve', 'Reject', 'Request Changes'
    comments: Optional[str] = ""

class AIChatQuery(BaseModel):
    query: str
    user_role: Optional[str] = "manager"
    request_id: Optional[str] = None

class SystemMetricsResponse(BaseModel):
    median_tat_hours: float
    incomplete_requests_percent: float
    total_active_requests: int
    pending_approval_value: float
    session_reviewed_percent: float
