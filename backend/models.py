"""
Pydantic Schemas and Contracts
FlowSync / BuyOps AI - S3K Case Study 03
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str
    department: str

class UserProfile(BaseModel):
    id: str
    username: str
    full_name: str
    email: str
    role: str
    department: str
    budget_limit: float

class CreatePurchaseRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    category: str
    vendor: str
    amount: float = Field(..., gt=0)
    business_justification: str = Field(..., min_length=10)
    department: Optional[str] = "Engineering"
    requester_name: Optional[str] = "Sarah Chen"
    invoice_content: Optional[str] = None # text or base64 representation
    invoice_sha256: Optional[str] = None  # direct sha256 hash if computed client-side
    quotes_count: Optional[int] = 1

class ApprovalDecision(BaseModel):
    request_id: str
    action: str = Field(..., pattern="^(Approve|Reject|Request Changes)$")
    comments: Optional[str] = ""

class AIChatQuery(BaseModel):
    query: str = Field(..., min_length=1)
    request_id: Optional[str] = None
