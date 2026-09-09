# StandardSense

## AI-Powered Tender Specification & Indian Standards Compliance System

StandardSense is an AI-powered system developed for **Smart India Hackathon 2026 Problem Statement 26108**. It analyzes tender specification PDFs, extracts important technical requirements, finds relevant Indian Standards using semantic search, checks compliance, ranks the recommended standards, and generates human-readable explanations using Retrieval-Augmented Generation (RAG) with Groq.

## Project Pipeline

```text
Tender PDF
    ↓
NLP Specification Extraction
    ↓
Semantic Search
    ↓
Indian Standards Matching
    ↓
Compliance Checking
    ↓
Recommendation Ranking
    ↓
RAG Explanation
    ↓
Results
```

## Tech Stack

* **Python**
* **FastAPI** – Backend REST API
* **React.js** – Frontend
* **Sentence-BERT** – Semantic embeddings
* **FAISS** – Vector similarity search
* **PostgreSQL** – Database
* **Groq LLM** – RAG-based explanations

## Main Features

* Upload tender specification PDFs
* Extract product and technical parameters
* Identify relevant Indian Standards
* Perform semantic similarity search
* Check specification compliance
* Rank recommended standards
* Generate human-readable compliance explanations
* REST API through FastAPI

## Project Structure

```text
standard-sense/
│
├── backend/
│   └── app/
│       └── main.py
│
├── nlp_extraction/
│   ├── extractor.py
│   ├── models.py
│   └── parser.py
│
├── semantic_search/
│   ├── search.py
│   ├── build_index.py
│   ├── is_index.faiss
│   └── is_metadata.json
│
├── compliance_ranking/
│   └── ranking_engine.py
│
├── rag_feedback/
│   └── rag/
│       ├── rag_engine.py
│       ├── llm.py
│       └── prompt.py
│
├── frontend/
│
├── demo-samples/
│
├── requirements.txt
├── .env.example
└── README.md
```

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/mj-creates/standard-sense.git
cd standard-sense
git checkout dev
```

### 2. Create a virtual environment

#### Windows

```cmd
python -m venv venv
venv\Scripts\activate
```

#### macOS/Linux

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If a dependency is missing, install it using:

```bash
pip install <package-name>
```

### 4. Configure environment variables

Create a `.env` file in the project root.

Add your Groq API key:

```env
GROQ_API_KEY=your_groq_api_key_here
```

**Never commit your actual API key to GitHub.**

### 5. Start the backend

From the project root:

```cmd
uvicorn backend.app.main:app --reload --port 8000
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

### 6. Test the backend

Open:

```text
http://127.0.0.1:8000/
```

Expected response:

```json
{
  "status": "ok",
  "message": "StandardSense backend is running"
}
```

### 7. Open API documentation

FastAPI provides interactive API documentation at:

```text
http://127.0.0.1:8000/docs
```

Use the `/process-tender` endpoint to upload a PDF and test the complete pipeline.

## Processing a Tender

The main endpoint is:

```text
POST /process-tender
```

It accepts a PDF tender specification and processes it through the complete StandardSense pipeline.

Example using cURL:

```bash
curl -X POST "http://127.0.0.1:8000/process-tender" ^
  -H "accept: application/json" ^
  -H "Content-Type: multipart/form-data" ^
  -F "file=@sample_tender_standardsense.pdf;type=application/pdf"
```

The response contains:

* Extracted specification
* Technical parameters
* Semantic search results
* Compliance status
* Ranked recommendations
* RAG-generated explanations

## Demo

Sample tender PDFs for demonstrations will be stored in:

```text
demo-samples/
```

Recommended demo categories include:

* LED Street Lights
* Electrical Cables
* Plugs and Socket-Outlets
* Electrical Appliances

## Important Notes

* The Groq API key must be configured through environment variables.
* Do not upload or commit `.env` containing real API credentials.
* FAISS and the Sentence-BERT model may take some time to load during the first backend startup.
* The Hugging Face unauthenticated-request warning does not prevent the semantic search system from running.

## SIH 2026

**Problem Statement:** SIH 26108

**Project:** StandardSense

StandardSense aims to reduce the manual effort involved in identifying applicable Indian Standards and evaluating tender specifications by combining NLP, semantic search, compliance analysis, ranking, and RAG-based explanations.
