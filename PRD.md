# Product Requirement Document (PRD)
## AI Data Agent: Agentic Data Intelligence & ETL Platform

### 1. Overview & Vision
The **AI Data Agent** is an enterprise-grade agentic data intelligence system designed to empower business analysts, data scientists, and engineers to interact with structured databases and diverse data pipelines through natural language. Built on LangGraph, PostgreSQL, and modern LLMs, the platform bridges natural language understanding with deterministic, safe execution through a built-in **Human-in-the-Loop (HITL)** security gate.

The platform automatically classifies incoming requests into either:
1. **SQL Database Operations**: Natural language to PostgreSQL queries, schema inspection, safety auditing, human approval gate, and synthesis of results.
2. **ETL Data Operations**: API extraction, structured ingestion (CSV, JSON, Parquet), and automated data transformations with sandboxed execution.

---

### 2. Target Audience & Personas
- **Business & Data Analysts**: Need immediate answers from complex database schemas without manual SQL authoring.
- **Data Engineers**: Require automated ingestion from disparate APIs into standardized local or warehouse storage without repetitive boilerplate.
- **Database Administrators & SecOps**: Require strict safety boundaries, preventing accidental mutations (`DROP`, `DELETE`, `UPDATE`, `TRUNCATE`) through automated LLM safety auditing and mandatory human sign-off for critical operations.

---

### 3. Core Features & Capabilities

#### 3.1 Intelligent Router Agent
- Automatically classifies user intents as either `sql` or `etl`.
- Handles ambiguous queries by requesting clarification or guiding user interaction.

#### 3.2 SQL Analyst Agent
- **Schema Contextualization**: Dynamically inspects tables, columns, data types, foreign keys, and sample records from PostgreSQL.
- **SQL Generation**: Generates standard PostgreSQL queries aligned with schema constraints and user-defined row limits.
- **Safety Judge & Auditing**: An autonomous LLM security layer evaluates generated SQL against destructive patterns.
- **Human-in-the-Loop (HITL) Gate**: Interrupts graph execution before executing SQL, surfacing the query, explanation, and risk level to the human operator for approval, edit, or rejection.
- **Insight Synthesis**: Translates raw database tuples into natural language narratives and tabular views.

#### 3.3 ETL Analyst Agent
- **API Extraction**: Extracts data from REST endpoints with format serialization (CSV, JSON, Parquet).
- **Code Generation & Transformation**: Generates reproducible Pandas transformation logic based on user questions and sampled data schemas.
- **Human Confirmation Gate**: Prompts for human sign-off before running dynamically generated transformation scripts.
- **Sandboxed Execution**: Executes Pandas scripts with captured stdout/stderr and error reporting.

#### 3.4 Full-Stack Interactive Control Center
- **Modern Glassmorphic Web Dashboard**: Real-time chat interface, visual agent execution timeline, and live status badges.
- **Interactive HITL Modal**: Real-time review card showing generated SQL/code, allowing operators to "Approve & Run", "Edit", or "Decline".
- **PostgreSQL Database Explorer**: Live inspection of tables, record counts, and sample records.
- **RESTful API**: Fast, async FastAPI backend supporting chat sessions, approval endpoints, and database health metrics.

---

### 4. Functional Requirements

| ID | Module | Requirement Description | Priority |
| :--- | :--- | :--- | :--- |
| **FR-01** | Router | Classify incoming messages into `sql` or `etl` with structured JSON output. | P0 |
| **FR-02** | SQL Analyst | Inspect PostgreSQL catalog (`information_schema`) without holding open connections. | P0 |
| **FR-03** | SQL Safety | Filter out mutating statements (`DROP`, `ALTER`, `TRUNCATE`, `DELETE`, `INSERT`, `UPDATE`). | P0 |
| **FR-04** | HITL Gate | Pause agent execution prior to SQL execution or code execution using LangGraph breakpoints. | P0 |
| **FR-05** | HITL Resume | Accept human feedback (`approve`, `modify`, `reject`) and resume execution state seamlessly. | P0 |
| **FR-06** | ETL Pipeline | Ingest REST API responses and output clean files into `data/extract/`. | P1 |
| **FR-07** | ETL Transform | Generate and run Pandas transformation scripts saving to `data/transform/`. | P1 |
| **FR-08** | Multi-LLM | Dynamically support OpenRouter, Gemini, OpenAI, or Claude with automated fallback. | P0 |
| **FR-09** | Web UI | Provide web-based interface with chat history, approval prompts, and DB catalog viewer. | P0 |
| **FR-10** | Database Seeding | Seed PostgreSQL with sample ridesharing schema and records cleanly via automated script. | P1 |

---

### 5. Non-Functional Requirements

- **Security**: Zero unvetted SQL queries executed against the production database; all dynamic queries must pass the safety judge and HITL gate. Credentials stored securely in environment variables.
- **Reliability & Connection Resilience**: Connection pooling with auto-reconnect and proper resource teardown (`cursor.close()`, `conn.close()`).
- **Performance**: Schema caching and query execution timeout of 15 seconds.
- **Portability**: Pure Python backend runnable on Windows/Linux/macOS with standard PostgreSQL instance.

---

### 6. System Requirements & Technology Stack

- **Runtime**: Python 3.12+ (tested on Python 3.14)
- **Agent Orchestration**: LangGraph 1.2+, LangChain Core 1.2+
- **Database**: PostgreSQL 14+ with `psycopg2-binary`
- **Data Manipulation**: Pandas 3.0+
- **API Framework**: FastAPI, Uvicorn
- **Frontend**: Responsive Vanilla HTML5/CSS3/JavaScript (Glassmorphic design, zero build dependencies)
- **LLM Providers**: OpenRouter (GPT-4o, Claude 3.5), Google Gemini 2.5 Flash, Anthropic, OpenAI
