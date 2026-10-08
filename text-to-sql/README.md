<div align="center">

# 🛡️ Text-to-SQL Interface with Guardrails and Hallucination Detection

**A production-grade natural language to SQL system that translates plain English questions into SQL queries, executes them safely against a PostgreSQL database, and validates results with a multi-signal hallucination detection system.**

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?logo=openai&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)

</div>

---

## 📑 Table of Contents

- [Evaluation Results](#-evaluation-results)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [API Endpoints](#-api-endpoints)
- [Running Evaluations](#-running-evaluations)
- [Key Design Decisions](#-key-design-decisions)

---

## 📊 Evaluation Results

| Metric | Score |
|--------|-------|
| Overall Accuracy | **91.7%** |
| Guardrail Effectiveness | **100%** |
| Ambiguity Detection | **100%** |
| Query Execution Accuracy | **100%** |
| Avg Confidence Score | **0.786** |
| Test Cases | **60** |

> ✅ **Zero unsafe queries executed across all test cases.**

---

## 🏗️ Architecture

```text
                 User Question
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Ambiguity Handler                  │
   │  Catches vague questions before     │
   │  any LLM call                       │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Schema Filter                      │
   │  Sends only relevant tables to      │
   │  the prompt                         │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Prompt Builder                     │
   │  Formats schema + few-shot examples │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  OpenAI GPT-4o-mini                 │
   │  Generates structured SQL +         │
   │  explanation                        │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Guardrail Middleware               │
   │  Blocks DDL/DML, enforces row limits│
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Query Executor                     │
   │  Read-only transaction +            │
   │  read-only DB user                  │
   └─────────────────────────────────────┘
                       │
                       ▼
   ┌─────────────────────────────────────┐
   │  Hallucination Detection            │
   │  • Back-translation verification    │
   │  • Result sanity checking           │
   │  • Multi-query validation           │
   │  • Confidence scoring               │
   └─────────────────────────────────────┘
                       │
                       ▼
          Result + Confidence Score → User
```

---

## 📁 Project Structure

```text
text-to-sql/
├── app/
│   ├── main.py                # FastAPI endpoints
│   ├── schema_extractor.py    # SQLAlchemy schema introspection
│   ├── prompt_builder.py      # Dynamic prompt construction
│   ├── schema_filter.py       # Keyword-based schema filtering
│   ├── ambiguity_handler.py   # Pre-LLM ambiguity detection
│   ├── sql_generator.py       # OpenAI structured output
│   ├── guardrails.py          # Safety middleware
│   ├── query_executor.py      # Read-only query execution
│   ├── executor.py            # Full pipeline orchestration
│   ├── hallucination.py       # Hallucination detection system
│   └── logger.py              # Centralized logging
├── frontend/
│   └── app.py                 # Streamlit UI
├── evals/
│   ├── golden_queries.json    # 60 test cases
│   ├── run_evals.py           # Automated eval runner
│   └── feedback.json          # User feedback storage
├── scripts/
│   └── seed.sql               # Database seed data
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repo
git clone <your-repo-url>
cd text-to-sql

# Add your OpenAI API key
echo "OPENAI_API_KEY=your_key_here" > .env

# Start everything
docker-compose up

# Open the UI
open http://localhost:8501
```

### Option 2: Local Development

**1. Install dependencies**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Set up PostgreSQL**

```bash
createdb ecommerce_db
psql ecommerce_db < scripts/seed.sql
```

**3. Add environment variables**

```bash
cp .env.example .env
# Edit .env with your OPENAI_API_KEY
```

**4. Start FastAPI**

```bash
cd app
uvicorn main:app --reload --port 8000
```

**5. Start Streamlit** (in a new terminal)

```bash
cd frontend
streamlit run app.py
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | `GET` | Health check |
| `/v1/query` | `POST` | Process natural language question |
| `/v1/schema` | `GET` | Get database schema |
| `/v1/history` | `GET` | Get query history |
| `/v1/feedback` | `POST` | Submit result feedback |

### Example Request

```bash
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which customers have spent the most money?"}'
```

### Example Response

```json
{
  "success": true,
  "sql": "SELECT c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.name ORDER BY total_spent DESC LIMIT 100",
  "explanation": "This query joins customers with orders and sums total amount per customer",
  "confidence": {
    "final_score": 0.85,
    "confidence_label": "HIGH",
    "recommendation": "Results look reliable. Proceed with confidence."
  },
  "data": [{"name": "Alice Johnson", "total_spent": 1379.97}],
  "row_count": 8
}
```

---

## 🧪 Running Evaluations

Make sure FastAPI is running first.

```bash
cd text-to-sql
python3 evals/run_evals.py
```

---

## 🧠 Key Design Decisions

<details>
<summary><b>Why keyword-based schema filtering instead of embeddings?</b></summary>

<br>

For a known schema with stable table names, keyword matching is faster, free, and just as accurate. Embeddings would add latency and cost without meaningful accuracy improvement for this scale.

</details>

<details>
<summary><b>Why back-translation for hallucination detection?</b></summary>

<br>

A query can be syntactically valid, pass all guardrails, and return results — but still answer the wrong question. Back-translation catches semantic mismatches that structural checks miss.

</details>

<details>
<summary><b>Why three independent safety layers?</b></summary>

<br>

Defense in depth. A bug in one layer doesn't compromise the system. All three layers would need to fail simultaneously for any database damage to occur.

</details>

<details>
<summary><b>Why hardcoded ambiguity terms instead of LLM-based detection?</b></summary>

<br>

Known domain-specific terms where we understand the ambiguity better than a general model. Faster, free, and completely predictable behavior.

</details>