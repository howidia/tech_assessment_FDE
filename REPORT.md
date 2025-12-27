# Agent Design & Evaluation Report

## 1. Approach and Architecture

### Data Layer Strategy: The `SubscriptionStore` Abstraction
The foundational design decision was the creation of a robust `SubscriptionStore` class. While simpler approaches like Pandas DataFrames or RAG (Retrieval Augmented Generation) were considered, I selected an **Abstracted SQL Layer** using SQLite for three enterprise-critical reasons:

1.  **Enterprise Realism & Scalability:** SQL is the standard interface for business data. Unlike loading CSVs into memory (which fails at scale) or context windows (which is expensive), an SQL-backed store can handle millions of rows efficiently.
2.  **Deterministic Execution:** SQL queries provide exact mathematical answers (`SUM`, `AVG`), mitigating the "calculation hallucination" risks common when LLMs perform arithmetic on raw text.
3.  **Consolidated Interaction Layer:** By wrapping the database connection in a custom class, we control exactly *how* agents interact with data. This abstraction allows for future "hot-swapping" of the backend (e.g., to Snowflake or Postgres) without changing much agent logic.

### Agent Architecture: Supervisor-Worker Pattern
Initial testing with a single monolithic agent revealed reliability issues when handling complex logic chains (e.g., "Find at-risk customers *and* calculate their total revenue"). To resolve this, I implemented a **Supervisor-Worker (Hierarchical) Architecture**:

* **Task Planner (Supervisor):**
    * **Role:** Strategic Orchestrator. It parses vague intent ("Risk", "Upsell") into concrete technical directives.
    * **Responsibility:** Enforces high-level guardrails (PII safety) and determines task completion.
    * **Output Strategy:** It filters the raw "Trace" from workers to provide only user-safe "Findings," ensuring internal logic doesn't leak to the end-user.

* **Data Analyst (Worker):**
    * **Role:** Specialized Execution Unit.
    * **Responsibility:** Restricted strictly to SQL generation. It has no awareness of business strategy, only schema and syntax. This separation of concerns minimizes context pollution.

## 2. Prompt Engineering Strategy

My strategy evolved from generic instruction to **Context-Aware Constraints** and **Logic Injection**.

### A. Task Planner: Business Logic Injection
I injected specific "Business Playbooks" directly into the system prompt. This transforms ambiguous terms into deterministic rules:
* **"Churn Risk"** $\rightarrow$ Defined explicitly as `{auto_renew=False} OR {status='pending_renewal'} OR {utilization < 50%}`.
* **"Upsell Opportunity"** $\rightarrow$ Defined as `{utilization > 90%} OR {tier='Basic'}`.

### B. Data Analyst: Schema & Syntax Constraints
To address specific failure modes (e.g., SQL syntax errors, empty results), I added a "CRITICAL SQL RULES" section:
* **Type Casting:** Enforced `CAST(x AS FLOAT)` to resolve SQLite's integer division behavior (which was returning 0% for utilization queries).
* **Data Normalization:** Explicitly mapped natural language (e.g., "credit card") to database schema quirks (e.g., `credit_card` with underscore), resolving 90% of empty result sets.

### C. Safety & Guardrails
I implemented a multi-layered safety mechanism:
1.  **Input Guardrails (Prompt Level):** The Supervisor is strictly instructed to **REFUSE** PII requests (Credit Cards, Emails) as its "Highest Priority."
2.  **Execution Guardrails (Code Level):** The `SubscriptionStore` enforces "Read-Only" access by blocking destructive keywords (`DROP`, `DELETE`, `INSERT`) at the application layer.
3.  **Output Guardrails (Structure Level):** The prompts enforce a strict separation between `=== TRACE ===` (internal logic) and `=== FINDINGS ===` (user output), preventing the leakage of tool names or raw SQL to the user.

## 3. Evaluation Design

To ensure the system is production-ready, I built a rigorous evaluation pipeline (`evaluate.py`) centered on **Reproducibility** and **Nuance**.

### Methodology: LLM-as-a-Judge
Manual inspection is unscalable. I used Cohere's (`command-r-plus`) model to grade the agent's outputs against a "Golden Answer" dataset. (Important to note this is the same model that writes the output).

### Metrics
1.  **Stability (Consistency Score):** LLMs are non-deterministic. I run every test case **3 times**. A test case is only considered "Stable" if it passes 3/3 times. (Note: In a production environment, I would increase this sample size).
2.  **Correctness (0/1):** Binary assessment of factual accuracy and safety refusals.
3.  **Quality (1-5):** Qualitative assessment of tone, context, and formatting.

### Artifacts
* **`reports/evaluation_report.md`**: A readable executive summary for stakeholders.
* **`reports/evaluation_report.csv`**: A raw, row-level dataset for engineering analysis (enabling deep dives into specific failure modes like latency or hallucination).

## 4. Evaluation Insights & Trade-offs

### Key Findings
* **Gold Standard Bias:** The LLM-as-a-Judge tends to penalize answers that are factually correct but phrased differently than the Golden Answer.
* **Prompt Efficacy:** The single most effective optimization was **Business Logic Injection**. Explicitly defining "Risk" in the prompt improved accuracy on those queries from near-zero to passing.
* **Contextual Limits:** The current agent struggles to "go above and beyond" (adding unrequested context) without explicit instruction. This suggests the need for a future "Enrichment Agent."

### Trade-offs
* **Latency vs. Reliability:** The Supervisor-Worker pattern introduces a "thinking" step, increasing latency compared to a single agent. I accepted this trade-off to prioritize **Safety** and **Accuracy**, which are non-negotiable in enterprise settings.
* **Complexity vs. Speed:** Building a custom `SubscriptionStore` and `AgentTeam` registry added initial development time compared to a simple script. However, this architectural investment ensures **scalability** and **reusability** for future iterations.

## 5. Future Roadmap & Improvements

With more time, I would prioritize the following features:

1.  **Observability & Tracing:** Currently, a basic `DEBUG_MODE` prints logs. I would implement a robust logging framework that captures internal `TRACE` outputs to structured logs (e.g., OpenTelemetry) for debugging logic failures in production.
2.  **Advanced Guardrails:** Move safety from "Prompt Instructions" (soft guardrail) to a "Middleware Layer" (hard guardrail) using embedding-based classification to detect and block PII or adversarial prompts before they reach the LLM.
3.  **Hallucination Testing:** The current evaluation checks for correctness on existing data. I would add "Negative Tests" (queries for data that *doesn't* exist) to ensure the agent doesn't hallucinate records.
4.  **Async Concurrency:** To offset the latency of the multi-agent system, I would implement `asyncio` for parallel tool execution, allowing the Planner to investigate multiple hypotheses simultaneously.
5.  **Data Permissions:** Hard-code row-level security or column masking into the `SubscriptionStore` to prevent agents from even accessing sensitive columns like `credit_card` numbers, regardless of their prompt instructions.
