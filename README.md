# Curd Rice Business Studio — AI-Powered Business Enquiry Automation System

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal.svg)](https://fastapi.tiangolo.com/)
[![Groq API](https://img.shields.io/badge/Groq-gpt--oss--120b-orange.svg)](https://groq.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-blue.svg)](https://www.postgresql.org/)
[![Pytest](https://img.shields.io/badge/Tests-28%20Passed-brightgreen.svg)](https://pytest.org/)

An enterprise-ready AI enquiry intake, understanding, lead scoring, and response automation system engineered for **Curd Rice Business Studio** (operations, business intelligence, and AI systems consultancy).

The system accepts incoming business enquiries through three channels (Web UI, REST API, or bulk CSV upload), uses Groq LLM API for structured information extraction, scores leads deterministically in pure Python across 5 dimensions, drafts personalized responses adhering to strict guardrails, and provides an operations dashboard for human review and approval.

---

## Key Highlights

- **Zero Overengineering**: No RAG, no vector databases, no LangChain, and no autonomous agents. Uses direct Groq SDK calls and standard Python functions with strict Pydantic v2 validation.
- **Deterministic Lead Scoring**: Final lead scores (0–100) and priorities (High, Medium, Low) are calculated via auditable Python rules, eliminating LLM hallucination and mathematical drift.
- **Mandatory Human-in-the-Loop**: Emails are **never** auto-sent. All generated responses require human review, editing, and approval.
- **Automatic Policy Escalation**: Complaints, job/internship applications, and partnerships are automatically flagged for senior human intervention regardless of numerical score.
- **Modern Responsive Dashboard**: Built with Jinja2, HTML5, and vanilla CSS matching modern SaaS operations interfaces (KPI stat cards, dynamic SVG donut & bar charts, filterable tables, and review queues).
- **100% Test Coverage**: 28 automated tests covering schemas, validation, scoring algorithms, complaint escalation, draft workflows, and CSV uploads.

---

## System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["Ingestion Channels"]
        A1["Manual Form (/enquiries/new)"]
        A2["REST API (POST /api/enquiries)"]
        A3["Bulk CSV Upload (/upload-csv)"]
    end

    subgraph API["FastAPI Routing & Validation"]
        B1["Pydantic Schemas (EnquiryCreate, LeadScore, etc.)"]
        B2["Routers (Dashboard, Enquiries, Drafts)"]
    end

    subgraph Engine["Service & Automation Engine"]
        C1["Pipeline Orchestrator (pipeline.py)"]
        C2["AI Extraction (ai_understanding.py - Groq API)"]
        C3["Deterministic Lead Scorer (lead_scoring.py - Pure Python)"]
        C4["AI Email Drafter (ai_response.py - Groq API)"]
    end

    subgraph Storage["Persistence Layer"]
        D1[("PostgreSQL / SQLite")]
        D2["Enquiry Table (Raw Input)"]
        D3["EnquiryAnalysis Table (Extracted Entities & Score)"]
        D4["ResponseDraft Table (Drafts & Approval Status)"]
    end

    A1 & A2 & A3 --> B1
    B1 --> B2
    B2 --> C1
    C1 --> C2
    C1 --> C3
    C1 --> C4
    C1 --> D2 & D3 & D4
    D2 & D3 & D4 -.-> D1
```

---

## 10-Step Processing Pipeline

Every incoming enquiry passes through a 10-step pipeline:

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / Ingestion
    participant Router as FastAPI Router
    participant Pipe as Pipeline Orchestrator
    participant DB as PostgreSQL Database
    participant LLM1 as Groq LLM (Entity Extraction)
    participant Scorer as Python Rule Scorer
    participant LLM2 as Groq LLM (Response Drafting)
    actor Admin as Operations Reviewer

    Customer->>Router: Submit enquiry
    Router->>Router: Pydantic sanitization & validation
    Router->>Pipe: process_enquiry(payload)
    Pipe->>DB: Save Enquiry (Status = PENDING)
    Pipe->>LLM1: Extract category, requirement, budget, timeline, intent
    LLM1-->>Pipe: Validated structured JSON
    Pipe->>Scorer: calculate_lead_score(extracted_info)
    Scorer-->>Pipe: Score (0-100), Priority, Explainable reasons list
    alt Sensitive Category (Complaint, Internship, Partnership)
        Pipe->>Pipe: Set requires_human_review = True
    end
    Pipe->>DB: Save EnquiryAnalysis record
    Pipe->>LLM2: Generate draft with tone template + business context
    LLM2-->>Pipe: Email Draft (Subject & Body)
    Pipe->>DB: Save ResponseDraft (approval_status = PENDING)
    Pipe->>DB: Update Enquiry (Status = COMPLETED / NEEDS_REVIEW)
    Pipe-->>Router: Return full EnquiryDetail
    Admin->>Router: Review, edit, approve/reject draft via UI
```

---

## Deterministic Lead Scoring Methodology

Lead scoring is decoupled from the LLM to guarantee consistency, predictability, and auditability.

| Scoring Dimension | Max Points | Evaluation Rules |
| :--- | :---: | :--- |
| **1. Business Relevance** | **30 pts** | Core Services (`AI Automation`: 30, `App Dev`: 28, `Web Dev`: 25, `Consulting`: 22). Secondary (`Marketing`: 18, `General`: 10). Non-client (`Partnership`, `Internship`: 8, `Complaint`: 5). |
| **2. Requirement Clarity** | **20 pts** | Specific, detailed scope (>=100 chars: 20 pts; >=60 chars: 15 pts; >=30 chars: 10 pts; <30 chars: 2–5 pts; None: 0 pts). |
| **3. Budget Information** | **15 pts** | Stated numerical or structured budget: 15 pts; generic budget mention: 8 pts; unspecified: 0 pts. |
| **4. Timeline & Urgency** | **15 pts** | Urgent ('immediately', 'asap', 'within 2 weeks'): 15 pts; near-term ('within a month'): 10 pts; flexible: 6 pts; unspecified: 0 pts. |
| **5. Potential Scope** | **20 pts** | High complexity keywords ('ERP', 'pipeline', 'automated workflow', 'scale metrics'): up to 20 pts; moderate: 12 pts; standard: 6 pts. |
| **Total Maximum Score** | **100 pts** | **High Priority: 70–100** \| **Medium: 40–69** \| **Low: 0–39** |

---

## Database Schema (Relational Integrity)

Built with SQLAlchemy 2.0 ORM:

```mermaid
erDiagram
    ENQUIRIES ||--o| ENQUIRY_ANALYSIS : "1 to 1"
    ENQUIRIES ||--o| RESPONSE_DRAFTS : "1 to 1"

    ENQUIRIES {
        int id PK
        string customer_name
        string company_name
        string email
        text message
        string source
        string processing_status
        datetime created_at
    }

    ENQUIRY_ANALYSIS {
        int id PK
        int enquiry_id FK
        string category
        text requirement
        string budget
        string expected_timeline
        string intent
        float confidence
        int lead_score
        string priority
        text scoring_reasons
        boolean requires_human_review
        text review_reason
        datetime created_at
    }

    RESPONSE_DRAFTS {
        int id PK
        int enquiry_id FK
        string subject
        text body
        string approval_status
        datetime created_at
        datetime updated_at
    }
```

---

## API Documentation

FastAPI provides an interactive Swagger interface at `http://localhost:8000/docs`.

### Core Endpoints

| Method | Endpoint | Description |
| :---: | :--- | :--- |
| `GET` | `/` | Main operations dashboard (KPI metrics, SVG donut/bar charts, recent feeds) |
| `GET` | `/enquiries` | Filterable enquiry list (search by message/name, filter by status/priority/category) |
| `GET` | `/enquiries/new` | Manual enquiry web submission form |
| `POST` | `/enquiries/new` | Process manual enquiry submission through AI pipeline |
| `GET` | `/enquiries/{id}` | Enquiry detail page with AI analysis and editable response draft |
| `GET` | `/upload-csv` | CSV batch ingestion web interface |
| `POST` | `/upload-csv` | Upload and batch process CSV files |
| `GET` | `/review` | Human review queue for escalated enquiries and pending drafts |
| `GET` | `/analytics` | Lead analytics and pipeline health reports |
| `POST` | `/drafts/{id}/action` | Form action to approve, reject, flag, or save draft edits |
| `POST` | `/api/enquiries` | REST API endpoint to submit a single enquiry |
| `POST` | `/api/enquiries/upload-csv` | REST API endpoint to upload and process a CSV file |
| `GET` | `/api/enquiries` | Paginated enquiry list with query filters |
| `GET` | `/api/enquiries/{id}` | Full enquiry detail with analysis and draft schema |
| `GET` | `/api/dashboard/stats` | Aggregated metrics (totals, priority, categories, pending reviews) |
| `GET` | `/api/health` | Service health status |

---

## Installation & Local Setup

### Prerequisites
- Python 3.12+
- PostgreSQL (or fallback to local SQLite)
- Groq API Key ([console.groq.com](https://console.groq.com/keys))

### Step-by-Step

1. **Clone the repository**:
   ```bash
   git clone https://github.com/niranjansakthi/AI_enquiry_system.git
   cd AI_enquiry_system
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Create a `.env` file from `.env.example`:
   ```ini
   GROQ_API_KEY=gsk_your_groq_api_key_here
   GROQ_MODEL=openai/gpt-oss-120b
   GROQ_TIMEOUT=30
   GROQ_MAX_RETRIES=2

   # PostgreSQL:
   DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/AI_enquiry_system
   # Or SQLite local fallback:
   # DATABASE_URL=sqlite:///./enquiries.db

   APP_ENV=development
   LOG_LEVEL=INFO
   ```

5. **Start the application**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

6. **Access the Web Interface**:
   - Dashboard: `http://localhost:8000`
   - Review Queue: `http://localhost:8000/review`
   - Swagger API Docs: `http://localhost:8000/docs`

---

## Running the Automated Test Suite

Run the full suite of **28 tests**:
```bash
pytest -v
```

### Test Suite Breakdown
- `tests/test_schemas_and_validation.py` (8 tests): Pydantic input models, string sanitizers, email validators, and category validation.
- `tests/test_lead_scoring.py` (6 tests): Scoring math, priority thresholds, complaint scoring, and empty field resilience.
- `tests/test_api_and_pipeline.py` (6 tests): Pipeline end-to-end integration, auto-escalation, draft approval workflow, and CSV batch processing.
- `tests/test_csv_upload_extended.py` (5 tests): Header aliases (`name`, `enquiry`, `company`), case insensitivity, corrupted emails, and empty files.
- `tests/test_frontend_views.py` (3 tests): HTML view status codes, manual submission flows, and CSV batch results rendering.

---

## Sample Assessment Enquiries

A pre-built sample file containing all 12 assessment test cases is located at:
```
data/sample_enquiries.csv
```
You can upload this directly on the `/upload-csv` page to verify classification across:
- Enterprise AI Automation
- Website Development
- Business Consulting
- Customer Complaints (Auto-escalated)
- Student Internship Applications (Auto-escalated)
- Strategic Partnerships (Auto-escalated)

---

## AI Usage Disclosure & Engineering Practices

- **AI Foundation Models**: Groq API with `openai/gpt-oss-120b` was utilized for structured text extraction and context-constrained email draft generation.
- **Assisted Scaffolding**: Antigravity AI coding assistant assisted with boilerplate scaffolding, schema structures, and test cases.
- **Human Engineering & Governance**: System architecture, database schema, deterministic scoring rules, business guardrails, review workflows, and error handling architectures were designed and verified to ensure full production readiness.
