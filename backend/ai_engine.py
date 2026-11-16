"""
Grounded Semantic Policy AI Engine and Live LLM Hook
FlowSync / BuyOps AI - S3K Case Study 03
"""

import os
import re
import json
import math
import urllib.request
from typing import Dict, Any, List, Tuple, Optional

# Indexed Company Procurement Policy Clauses (RAG Knowledge Base)
POLICY_KNOWLEDGE_BASE = [
    {
        "clause_id": "POL-01-TIERS",
        "title": "Delegation of Authority & Monetary Tiers",
        "keywords": ["tier", "amount", "limit", "threshold", "manager", "finance", "depthead", "head", "vp", "rule", "25000", "100000"],
        "text": (
            "Acme Corp Purchase Authorization Thresholds:\n"
            "• Tier 1 (≤ ₹25,000): Requires direct Line Manager sign-off only. Fast-tracked operational clearance.\n"
            "• Tier 2 (₹25,001 to ₹1,00,000): Requires sequential approval from Line Manager AND Finance Manager.\n"
            "• Tier 3 (> ₹1,00,000): High-value capital expenditure requiring Line Manager, Finance Manager, AND Department Head (VP) sign-offs."
        )
    },
    {
        "clause_id": "POL-02-QUOTES",
        "title": "Competitive Vendor Quotations Requirement",
        "keywords": ["quote", "quotes", "quotation", "comparative", "competitive", "vendor", "vendor quote", "comparison"],
        "text": (
            "For all purchase requests exceeding ₹25,000 (Tier 2 & Tier 3), requesters must attach at least two competitive vendor quotations. "
            "Requests with only one vendor quote are automatically marked FLAGGED_MISSING_DOCS and approval is blocked."
        )
    },
    {
        "clause_id": "POL-03-HUMAN-GOVERNANCE",
        "title": "S3K Core Safety Rule: Human Governance",
        "keywords": ["ai approve", "independently", "autonomous", "safety", "governance", "ai decision", "auto approve"],
        "text": (
            "S3K Principle: AI Assisted – Human Governed.\n"
            "FlowSync AI performs OCR document extraction, budget cross-referencing, duplicate detection, and risk scoring. "
            "AI NEVER independently approves financial requests. All final approval decisions must be made by an authenticated human approver."
        )
    },
    {
        "clause_id": "POL-04-DUPLICATE-FRAUD",
        "title": "Cryptographic Duplicate Invoice Prevention",
        "keywords": ["duplicate", "fraud", "hash", "sha256", "re-bill", "same invoice", "collision"],
        "text": (
            "Every invoice uploaded is hashed using cryptographic SHA-256. Submissions matching historical invoices processed within the last 90 days "
            "are locked under CRITICAL RISK / DUPLICATE INVOICE alert, and automated sign-off is disabled until a manual forensic audit is completed."
        )
    },
    {
        "clause_id": "POL-05-SEQUENTIAL-STAGES",
        "title": "Sequential Approval Progression",
        "keywords": ["sequential", "stage", "order", "skip", "bypass", "premature", "finance before manager", "dept head before finance"],
        "text": (
            "Approval stages must be strictly sequential: Line Manager must approve before Finance can review. "
            "For Tier 3, Finance must approve before Department Head can execute final sign-off. "
            "A Department Head cannot approve a request while it is still pending Finance review."
        )
    }
]

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b[a-z0-9]+\b', text.lower())

def compute_similarity(query_tokens: List[str], doc_tokens: List[str]) -> float:
    """Computes Jaccard/overlap similarity score between query and policy chunk."""
    q_set = set(query_tokens)
    d_set = set(doc_tokens)
    if not q_set or not d_set:
        return 0.0
    intersection = q_set.intersection(d_set)
    return len(intersection) / math.sqrt(len(q_set) * len(d_set))

def retrieve_relevant_policy(query: str) -> Tuple[Dict[str, Any], float]:
    """Retrieves the most semantically relevant policy clause from the knowledge base."""
    q_tokens = tokenize(query)
    q_lower = query.lower()
    best_chunk = POLICY_KNOWLEDGE_BASE[0]
    best_score = -1.0

    for chunk in POLICY_KNOWLEDGE_BASE:
        # Check direct keyword boosts
        keyword_hits = sum(2.0 for kw in chunk["keywords"] if kw in q_lower)
        
        chunk_tokens = tokenize(chunk["title"] + " " + " ".join(chunk["keywords"]) + " " + chunk["text"])
        base_score = compute_similarity(q_tokens, chunk_tokens)
        final_score = base_score + (keyword_hits * 0.15)

        if final_score > best_score:
            best_score = final_score
            best_chunk = chunk

    return best_chunk, round(min(best_score, 1.0), 3)

def query_gemini_api_if_configured(prompt: str, policy_context: str) -> Optional[str]:
    """Calls Gemini REST API if GEMINI_API_KEY is available in the environment."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [{
                    "text": (
                        f"You are the BuyOps Procurement Policy Copilot. Ground your answer strictly in this company policy:\n\n"
                        f"{policy_context}\n\n"
                        f"S3K Principle: AI Assisted - Human Governed. AI never approves financial requests.\n\n"
                        f"User question: {prompt}\n\n"
                        f"Answer concisely in markdown."
                    )
                }]
            }]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode())
            text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return text
    except Exception:
        return None

def answer_policy_query(query: str, request_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Synthesizes a response using Context Grounding (RAG).
    Checks live Gemini API first, falling back to our internal semantic retrieval engine.
    """
    relevant_clause, score = retrieve_relevant_policy(query)
    policy_context = f"[{relevant_clause['clause_id']}] {relevant_clause['title']}:\n{relevant_clause['text']}"

    # Try live Gemini call
    live_llm_response = query_gemini_api_if_configured(query, policy_context)
    if live_llm_response:
        return {
            "reply": live_llm_response,
            "engine": "Google Gemini 1.5 Flash (Live API)",
            "grounded_clause": relevant_clause["clause_id"],
            "confidence": 0.98
        }

    # Internal Semantic Retrieval Engine Synthesis
    reply_lines = []
    q_lower = query.lower()

    if request_context:
        reply_lines.append(f"**Request Dossier: {request_context['id']} ({request_context['title']})**")
        reply_lines.append(f"• **Current Status:** `{request_context['status']}`")
        reply_lines.append(f"• **Tier Threshold:** {request_context['tier']}")
        reply_lines.append(f"• **Requester:** {request_context['requester_name']} ({request_context['department']})")
        reply_lines.append(f"• **Amount:** ₹{request_context['amount']:,.2f}")
        reply_lines.append(f"• **Invoice Hash (SHA-256):** `{request_context['invoice_sha256'][:16]}...`")
        reply_lines.append("")

    reply_lines.append(f"**Policy Guidance ({relevant_clause['title']}):**")
    reply_lines.append(relevant_clause["text"])
    reply_lines.append("")
    reply_lines.append(f"_Grounding: Sourced from `{relevant_clause['clause_id']}` (Semantic match score: {score * 100:.1f}%)_")

    return {
        "reply": "\n".join(reply_lines),
        "engine": "Semantic Policy RAG Engine (Context Grounded)",
        "grounded_clause": relevant_clause["clause_id"],
        "confidence": round(score, 2)
    }
