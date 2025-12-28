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
    * **Scalability & Delegation:** The Planner is designed to select tools dynamically from an extensible `AgentTeam` registry. While currently configured with a single `DataAnalyst` for this MVP, this architecture allows for **zero-refactor scaling**. We can easily plug in new specialists (e.g., an "Auxiliary Research Agent") and the Planner will automatically discover and utilize them for relevant sub-tasks.
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
* **Data Normalization:** Explicitly mapped natural language (e.g., "credit card") to database schema quirks (e.g., `credit_card` with underscore), resolving most empty result sets.

### C. Safety & Guardrails
I implemented a multi-layered safety mechanism:
1.  **Input Guardrails (Prompt Level):** The Supervisor is strictly instructed to **REFUSE** PII requests (Credit Cards, Emails) as its "Highest Priority."
2.  **Execution Guardrails (Code Level):** The `SubscriptionStore` enforces "Read-Only" access by blocking destructive keywords (`DROP`, `DELETE`, `INSERT`) at the application layer.
3.  **Output Guardrails (Structure Level):** The prompts enforce a strict separation between `=== TRACE ===` (internal logic) and `=== FINDINGS ===` (user output), preventing the leakage of tool names or raw SQL to the user.

### D. Judge Reliability Engineering (JSON Schema)
A common failure mode in "LLM-as-a-Judge" pipelines is the judge itself hallucinating the output format (e.g., returning markdown instead of JSON), causing the evaluation script to crash.

To solve this, I implemented **Cohere's Native Response Format** (JSON Schema) specifically for the Judge model.
* **Implementation:** I defined a strict schema requiring `correctness` (int), `quality` (int), and `reasoning` (string).
* **Result:** This guaranteed 100% valid JSON output from the Judge, eliminating "parsing errors" from the evaluation logs and ensuring the report generation was deterministic.

## 3. Evaluation Design

To ensure the system is production-ready, I built a rigorous evaluation pipeline (`evaluate.py`) centered on **Reproducibility** and **Nuance**.

### Methodology: LLM-as-a-Judge
Manual inspection is unscalable. I used Cohere's (`command-a`) model to grade the agent's outputs against a "Golden Answer" dataset. (Important to note this is the same model that writes the output).

### Metrics
1.  **Stability (Consistency Score):** LLMs are non-deterministic. I run every test case **3 times**. A test case is only considered "Stable" if it passes 3/3 times. (Note: In a production environment, I would increase this sample size).
2.  **Correctness (0/1):** Binary assessment of factual accuracy and safety refusals.
3.  **Quality (1-5):** Qualitative assessment of tone, context, and formatting.

### Security & Red-Teaming 
To ensure the system is enterprise-secure, I extended the evaluation dataset to include **Adversarial Test Cases**:
1.  **Prompt Injection:** Attempts to leak system instructions (e.g., "Ignore previous instructions...").
2.  **SQL Injection:** Attempts to execute destructive commands (e.g., `DROP TABLE`).
These tests verify that the "Hard Guardrails" (Read-Only SQL wrapper) and "Soft Guardrails" (System Prompt instructions) are functioning correctly.

> **Note:** This represents a baseline security check. With more time, a comprehensive set of guardrails would be implemented.

### Artifacts
* **`reports/evaluation_report.md`**: A readable executive summary for stakeholders.
* **`reports/evaluation_report.csv`**: A raw, row-level dataset for engineering analysis (enabling deep dives into specific failure modes like latency or hallucination).

## 4. Evaluation Insights & Trade-offs

### Key Findings (Data from latest run)
* **High Security:** The agent achieved a **100% Pass Rate** on all Safety and Adversarial queries. It successfully refused PII requests and blocked `DROP TABLE` attempts, proving the dual-layer guardrail approach works.
* **High Stability (86%):** 19 out of 22 test cases achieved "Perfect Stability" (3/3 passes).
* **Math is Solid:** The agent consistently handled complex arithmetic (MRR sums, Float utilization), proving that offloading math to SQLite is the correct architectural choice.

### Analysis of Failures
The agent struggled in 3 specific areas, revealing "Safe Defaults" behaviors:
1.  **Implicit Filtering:** On the question *"How many customers are on the Enterprise plan?"*, the agent returned **4** (Active users) instead of **6** (Total users). The agent seemingly applies an implicit `WHERE status='active'` filter unless instructed otherwise.
2.  **Summarization Loss:** On complex retrieval tasks (e.g., "Tech companies"), the agent successfully retrieved the data but occasionally omitted secondary details (like "Trial Status") in the final natural language summary.

### Trade-offs
* **Latency vs. Reliability:** The Supervisor-Worker pattern introduces a "planning" step, increasing latency. I accepted this trade-off to prioritize **Safety**, **Accuracy**, and **Scalability**. The Supervisor Agent could also integrate seamlessly with other agent teams.
* **Complexity vs. Speed:** Building a custom `SubscriptionStore` and `AgentTeam` registry added initial development time compared to a simple script. However, this architectural investment ensures **scalability** for future iterations.

## 5. Iterations & Improvements

My development process followed a data-driven loop: **Evaluate $\rightarrow$ Analyze Failure $\rightarrow$ Refine Prompt/Code $\rightarrow$ Re-evaluate.**

### Key Iterations
This table highlights the specific engineering changes made to resolve early failure modes.

| Failure Mode (Initial Run) | Root Cause Analysis | Fix Implementation | Result (Final Run) |
| :--- | :--- | :--- | :--- |
| **Utilization = 0%** | SQLite performs integer division by default (e.g., `58/75 = 0`). | **Prompt Update:** Added `CRITICAL RULE: CAST(x AS FLOAT)` to Data Analyst instructions. | **100% Pass** on utilization queries. |
| **"No results found"** | User asked for "credit card" (space), DB has `credit_card` (underscore). | **Schema Injection:** Explicitly mapped natural language terms to their enum counterparts in the system prompt. | **100% Pass** on metadata queries. |
| **Hallucinated "Risk"** | Agent invented its own definition of "Churn Risk," missing the business context. | **Logic Injection:** Added a "Business Playbook" section to the Supervisor prompt defining "Risk" as specific SQL conditions (e.g., `auto_renew=False`). | **Improved accuracy** on qualitative questions. |

## 6. Future Roadmap

With more time, I would prioritize the following features:

1.  **Observability & Tracing:** Currently, a basic `DEBUG_MODE` prints logs. I would implement a robust logging framework that captures internal `TRACE` outputs to structured logs (e.g., OpenTelemetry) for debugging logic failures in production.
2.  **Expanded Red Teaming:** While the current evaluation includes basic Prompt Injection and SQL Injection tests, I would expand this to a comprehensive "Red Team" suite using automated attack libraries (like Garak or PyRIT) to test for more subtle jailbreaks and PII leakage vectors.
3.  **Advanced Guardrails:** Move safety from "Prompt Instructions" (soft guardrail) to a "Middleware Layer" (hard guardrail) using embedding-based classification to detect and block PII or adversarial prompts before they reach the LLM.
4.  **Hallucination Testing:** The current evaluation checks for correctness on existing data. I would add "Negative Tests" (queries for data that *doesn't* exist) to ensure the agent doesn't hallucinate records.
5.  **Async Concurrency:** To offset the latency of the multi-agent system, I would implement `asyncio` for parallel tool execution, allowing the Planner to investigate multiple hypotheses simultaneously.
6.  **Data Permissions:** Hard-code row-level security or column masking into the `SubscriptionStore` to prevent agents from even accessing sensitive columns like `credit_card` numbers, regardless of their prompt instructions.
7.  **Structured Agent Communication:** Migrate inter-agent communication from natural language strings to a shared **Pydantic Protocol**. By having workers return structured objects (e.g., `class AgentResponse`), we can formally decouple internal traces from final answers, eliminating the fragility of regex parsing in the Supervisor.
8.  **Interactive Ambiguity Resolution (HITL):** Implement a Human-in-the-Loop mechanism for vague requests. Instead of relying on "best-guess" assumptions in the Business Playbook, the Planner would utilize a `ask_clarifying_question` tool to pause execution and request user clarification (e.g., "Do you mean churned customers or low utilization?") before proceeding.
