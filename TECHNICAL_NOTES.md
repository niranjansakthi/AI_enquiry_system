Curd Rice Business Studio - Technical Notes & Implementation Decisions

1. Why No LangChain / LangGraph / Autonomous Agents?
For business automation pipelines handling customer enquiries, predictability, latency, and debuggability are paramount.
- Frameworks like LangChain add extensive abstraction layers, fragile prompt templates, and hidden dependencies that complicate simple REST microservices.
- Using the official Groq Python SDK directly with clear, explicit Pydantic schemas provides sub-second execution, transparent error handling, and complete control over prompts and timeouts.

2. Why Pure Python Lead Scoring?
Asking an LLM to generate numerical scores results in non-deterministic hallucinations: identical customer requests could receive vastly different numbers across executions.
- The scoring engine uses pure deterministic Python logic across 5 explicit dimensions (Relevance, Clarity, Budget, Timeline, Scope).
- Every point awarded corresponds to a human-readable reason recorded in `scoring_reasons`.
- This ensures 100% explainability during client presentations and interviews.

3. Resilience & Failure Handling Strategy
A primary vulnerability in AI workflows is external service failure. The system guarantees:
- Original Submission Integrity: The customer enquiry is committed to PostgreSQL as `PENDING` before any external network call is made.
- Safe Degradation: If Groq experiences downtime or rate limits (HTTP 429), the enquiry status transitions to `FAILED` or `NEEDS_REVIEW`. The raw enquiry is never lost.
- Partial Pipeline Recovery: If information extraction succeeds but email draft generation fails, the analysis and lead score are preserved, and the enquiry is marked for manual human drafting.

4. Model Selection & Rate Limit Accommodation
While Llama 3 models are typical, the provisioned Groq account made `openai/gpt-oss-120b` and `openai/gpt-oss-20b` available.
- `openai/gpt-oss-120b` was chosen for its strong reasoning and JSON formatting compliance.
- The system includes automatic exponential backoff retry mechanisms to handle transient 429 rate limit triggers smoothly.

5. Database Storage Decisions
- PostgreSQL 17 was chosen with SQLAlchemy ORM and psycopg2 driver for production-grade reliability.
- SQLite support remains functional as an automatic local development fallback when running in disconnected environments.
- Enums are persisted as strings to ensure straightforward database introspection and zero-downtime migration compatibility.

