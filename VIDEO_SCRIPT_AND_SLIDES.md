# 7-Minute Video Demonstration Script & Presentation Plan
## S3K Internship 2026 — Case Study 03: Enterprise Request & Approval Platform (BuyOps)

---

### Video Overview & Guidelines
* **Target Duration:** 7 Minutes (approx. 420 seconds)
* **Tone:** Professional, articulate, structured, and engineering-minded.
* **Recording Format:** Split-screen (Webcam + Screen Share).
* **Key Sections to Hit:**
  1. Business Problem & Opportunity (60s)
  2. Discovery Insights & Redesigned Workflow (75s)
  3. Live BuyOps MVP UI Demonstration (105s)
  4. Architecture, Security & UAT Verification (60s)
  5. 60-Second AI Teaching Demonstration for Beginners (60s)
  6. Ownership, AI Disclosure & Closing (60s)

---

### Slide Deck Outline (6 Slides Total)

* **Slide 1: Title & Opportunity:** *FlowSync / BuyOps — Enterprise Request & Approval Platform* (Candidate Name, Candidate ID, Role: Full-Stack FDE / AI Platform Engineer).
* **Slide 2: AS-IS Bottlenecks vs. TO-BE KPIs:** Comparison table showing 5-day cycle time reduced to 18.4 hours, 28% incomplete submissions cut to 3.2%, and 90% status pings deflected.
* **Slide 3: Workflow Architecture & Policy Tiers:** The 3 tiers (≤ ₹25k, ₹25k-₹100k, > ₹100k) with the principle: *AI Assisted – Human Governed*.
* **Slide 4: Live Demo (Screen Share):** Walkthrough of `frontend/index.html` (BuyOps layout, Card 1 review, Budget impact donut, AI Copilot, Requester RLS view).
* **Slide 5: Technical Stack & Security Verification:** Architecture diagram showing Vanilla JS + Tailwind CSS (Neumorphic Soft UI), Python FastAPI, SQLite/PostgreSQL, PBKDF2 + Signed JWT Auth, Sequential State Machine, Verifiable Hash-Chained Audit Ledger, and 100% UAT test results (7 automated tests).
* **Slide 6: AI Teaching Concept & Human Ownership:** Teaching slide (*What is Context Grounding / RAG?*) + Breakdown of Human Engineering vs. AI Tools.

---

### Minute-by-Minute Script & Speaking Notes

#### [00:00 – 01:00] Segment 1: Executive Framing & Product Opportunity
**Screen:** Slide 1 & 2 (Candidate webcam visible in corner).  
**Speaking Notes:**
> "Hello everyone. My name is [Your Name], and today I am excited to present my solution for Case Study 03: The Enterprise Request & Approval Platform, branded as **BuyOps**.
>
> In our fictional 100-person enterprise, handling 90 purchase requests each month through unstructured email chains and spreadsheets creates three severe operational pain points:
> 1. An unacceptable average approval cycle of 5 working days, causing delays in software licenses and equipment.
> 2. An initially incomplete request rate of 28%, resulting in endless back-and-forth between employees and Finance over missing quotes or invalid tax invoices.
> 3. Zero self-service visibility, forcing Finance to field over 100 manual status emails each month.
>
> Our target outcomes are concrete: Reduce median decision turnaround time from 5 days to under 24 hours, push first-time-right submissions above 95% via automated intake checks, and deflect over 90% of status inquiries through transparent tracking."

---

#### [01:00 – 02:15] Segment 2: Discovery Findings & Re-engineered Workflow
**Screen:** Slide 3 (Workflow Diagram & Policy Tiers).  
**Speaking Notes:**
> "To solve this, we formulated key discovery questions for leadership, Finance, and line managers. The most critical takeaway was the need for an automated, tiered delegation-of-authority matrix:
> • **Tier 1 (up to ₹25,000):** Operational low-risk purchases require only the direct Line Manager's sign-off.
> • **Tier 2 (₹25,001 to ₹1,00,000):** Requires sequential approval from both the Line Manager and Finance, with a mandatory check for at least two competitive vendor quotes.
> • **Tier 3 (above ₹1,00,000):** High-value capital expenditure requiring Line Manager, Finance, and Department Head sign-off.
>
> But here is our governing philosophy, aligned with S3K's principle: **AI Assisted – Human Governed.**
>
> AI assists by extracting invoice metadata via OCR, flagging missing quotes, checking duplicate hashes, and calculating budget headroom. However, **AI NEVER independently approves financial requests.** The final sign-off is always held by an authenticated human approver."

---

#### [02:15 – 04:00] Segment 3: Live BuyOps MVP Demonstration
**Screen:** Switch to live browser window showing `frontend/index.html`.  
**Speaking Notes:**
> "Let's look at the working BuyOps MVP.
>
> In the top header, we immediately see our high-level health metrics: Approval Status showing 73% pending, total pending value of ₹2,42,500, and our session velocity.
>
> Looking at the request cards, let's examine **PR-1042: Cloud Server Licenses** submitted by Sarah Chen for ₹12,500.
> Notice the approval stepper: Team Lead Mark Wilson has already approved. Step 2 is active for the Manager. Because this is a Tier 1 expense under ₹25,000, Step 3 (Finance) is cleanly bypassed per policy.
>
> Directly on the card, the manager sees the **Engineering Budget Impact**: 78% utilized, ₹44,000 remaining. They don't have to open a separate budget spreadsheet!
>
> Clicking *'View AI Risk Analysis'* opens our dossier: AI OCR extracted the AWS invoice with 99.4% confidence, confirmed zero duplicate matches, and verified budget headroom.
>
> When the manager clicks **'Approve'**, notice what happens behind the scenes: The frontend makes an asynchronous API `fetch()` call carrying a signed JWT Bearer token to `POST /api/v1/requests/PR-1042/decision`. The FastAPI backend verifies manager credentials, executes the sequential state transition, updates the database, appends a cryptographically linked block to our audit hash chain, and returns an instant response displayed in our custom soft-UI toast.
>
> Now, observe what happens when we switch persona in the bottom-left to **Sarah Chen (Requester)**. Switching personas triggers a real `POST /api/v1/auth/login` to obtain Sarah's personal JWT token. Thanks to Object-Level Security at the data layer, Sarah's dashboard re-fetches and shows *only* her own requests. She cannot see other employees' sensitive software or equipment requests, completely eliminating IDOR privacy vulnerabilities.
>
> Lastly, employees can open the **AI Policy & Status Copilot** in the bottom corner. Typing *'What are the rules for Tier 3 purchases above 100000?'* runs our semantic policy RAG engine, matching against indexed procurement clauses with 100% confidence, giving immediate policy guidance without burdening Finance."

---

#### [04:00 – 05:00] Segment 4: Engineering Architecture & UAT Testing
**Screen:** Slide 5 (Architecture & Test Results).  
**Speaking Notes:**
> "Now let's think like an engineer.
>
> Our architecture combines a responsive, zero-build Vanilla JavaScript and Tailwind CSS frontend styled with tactile Neumorphic Soft UI, communicating via authenticated JSON APIs with a high-performance **Python FastAPI** backend and SQLite/PostgreSQL database.
>
> To ensure enterprise-grade security and reliability, I authored and verified an automated test suite in `backend/test_api.py` covering seven critical integration and security scenarios:
> 1. **Authentication & Tamper Defense:** Real PBKDF2-HMAC-SHA256 password hashing and cryptographically signed JWT Bearer tokens; tampered or missing tokens are strictly rejected with HTTP 401.
> 2. **Object-Level Authorization (IDOR Defense):** Verified that a user querying another employee's request ID receives an immediate HTTP 403 Forbidden.
> 3. **Strict Sequential Approval State Machine:** Verified that Department Heads cannot prematurely approve Tier 3 requests while Finance approval is pending; the system blocks premature sign-offs with HTTP 403.
> 4. **Missing Document Gatekeeper:** Tested request PR-1045 with missing competitive quotes; the API returns HTTP 422, locking approval until compliance documents are attached.
> 5. **Cryptographic Duplicate Invoice Collision Detection:** Proved that submitting an invoice with an identical SHA-256 hash automatically flags the request as CRITICAL RISK.
> 6. **Verifiable Hash-Chained Audit Ledger:** Validated blockchain-style cryptographic linkage (`prev_hash` to `log_hash`) across all ledger blocks via `/api/v1/audit/verify-chain`.
> 7. **Context-Grounded Semantic AI Copilot:** Verified that AI answers are mathematically grounded in company procurement policy clauses.
>
> All 7 automated tests pass with 100% verification."

---

#### [05:00 – 06:00] Segment 5: 60-Second AI Teaching Demonstration
**Screen:** Slide 6 (Teaching Visual: The Eager Intern vs. The Company Rulebook).  
**Speaking Notes:**
> *"Now, for our 60-second teaching demonstration: Let's explain **'Context Grounding and RAG'** to a complete beginner.*
>
> *Imagine you hire a brilliant college intern. They know general math and language, but on day one, they know absolutely nothing about your company's internal travel or expense policies. If you ask them, 'Can I expense a ₹15,000 dinner?', they might guess or hallucinate.*
>
> *That is how standard AI models work. They have general knowledge, but no company context.*
>
> ***Context Grounding—or Retrieval-Augmented Generation (RAG)—**is like handing that intern your exact one-page company handbook before they speak. When you ask the question, the system first retrieves the exact rule: 'Dinners above ₹5,000 require VP pre-approval.' It feeds this rule directly to the AI, and tells the AI: 'Answer strictly based on this rule.'*
>
> *The result? Reliable, hallucination-free, enterprise-safe AI responses every single time."*

---

#### [06:00 – 07:00] Segment 6: Personal Contribution, AI Tool Disclosure & Conclusion
**Screen:** Candidate on webcam with concluding summary slide.  
**Speaking Notes:**
> "To conclude, S3K values personal ownership, critical verification, and architectural decisions over unverified AI generation.
>
> **Where I used AI:** I leveraged AI assistants for CSS layout scaffolding and synthesizing mock invoice data.
>
> **My personal engineering ownership:**
> • I designed and implemented the real PBKDF2 password hashing and signed JWT Bearer authentication system.
> • I engineered the strict sequential approval state machine to eliminate authorization gaps and stage skipping.
> • I architected the Object-Level Security (RLS) model at the data-access layer to prevent IDOR leaks.
> • I designed the cryptographic SHA-256 hash-chained audit ledger with on-demand mathematical verification.
> • I implemented the context-grounded semantic policy RAG retrieval engine and live Gemini API hook.
> • And I authored and verified the 7-scenario automated test suite in FastAPI.
>
> FlowSync demonstrates that when AI is paired with strict human governance, enterprise workflows become faster, transparent, and completely audit-proof.
>
> Thank you, and I look forward to the next round."

---
*Recording Tip: Keep `frontend/index.html` open in Chrome and test clicking Approve, opening the detail modal, and typing in the Copilot before recording to ensure a seamless demonstration!*
