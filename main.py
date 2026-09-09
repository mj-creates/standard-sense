import os
import sqlite3
import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import pipeline engine
from pipeline import ComplianceEngine

app = FastAPI(
    title="BIS Procurement Compliance Engine API", 
    description="Backend API for AI-powered tender compliance validation.",
    version="1.0.0"
)

# Strict CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global initialization
engine = None
try:
    engine = ComplianceEngine()
except Exception as e:
    print(f"Warning: Engine initialization failed. Error: {e}")

AUDIT_DB_PATH = "compliance_audit.db"

def init_audit_db():
    try:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS audit_log
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, reference TEXT, clause TEXT, standard TEXT, verdict TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to initialize audit DB: {e}")

init_audit_db()

# --- Pydantic Models ---
class TenderPayload(BaseModel):
    reference_id: str = Field(..., example="NHAI/2026/CIVIL-049")
    tender_text: str = Field(..., min_length=10, example="M25 grade concrete mix with max 0.45 w/c ratio.")

class AuditLogItem(BaseModel):
    timestamp: str
    reference: str
    clause: str
    standard: str
    verdict: str

class ParameterCard(BaseModel):
    clause: str
    standard_code: str
    field_name: str
    field_type: str
    benchmark_threshold: str
    tender_value: str
    verdict: str

class TraceabilityItem(BaseModel):
    clause: str
    is_code: str
    title: str
    score: float

class ValidationResponse(BaseModel):
    executive_summary: dict
    traceability_table: List[TraceabilityItem]
    granular_parameter_cards: List[ParameterCard]

class HealthStatus(BaseModel):
    status: str
    faiss_index: str
    sqlite_db: str
    groq_api: str

# --- Endpoints ---

@app.get("/health", response_model=HealthStatus)
def health_check():
    faiss_status = "OK" if engine and hasattr(engine, 'index') and engine.index else "Missing/Uninitialized"
    sqlite_status = "OK" if engine and os.path.exists(engine.db_path) else "Missing"
    groq_status = "OK" if os.getenv("GROQ_API_KEY") else "Missing API Key"
    
    overall_status = "Healthy" if all(s == "OK" for s in [faiss_status, sqlite_status, groq_status]) else "Degraded"
    
    return HealthStatus(
        status=overall_status,
        faiss_index=faiss_status,
        sqlite_db=sqlite_status,
        groq_api=groq_status
    )

@app.post("/api/validate-tender", response_model=ValidationResponse)
def validate_tender(payload: TenderPayload):
    if not engine:
        raise HTTPException(status_code=503, detail="Compliance Engine is not initialized.")
    
    try:
        # Step 1: Simulated NLP Extraction (Tokenizing simple clauses by sentence for demo)
        clauses = [c.strip() for c in payload.tender_text.split('.') if len(c.strip()) > 5]
        if not clauses:
            clauses = [payload.tender_text]

        traceability_table = []
        parameter_cards = []
        
        compliant_count = 0
        total_clauses = len(clauses)
        
        conn = sqlite3.connect(AUDIT_DB_PATH)
        c = conn.cursor()

        for clause in clauses:
            # Step 2: Vector Semantic Retrieval
            top_standards = engine.search_top_standards(clause, k=10)
            if not top_standards:
                continue
                
            top_match = top_standards[0]
            traceability_table.append(TraceabilityItem(
                clause=clause,
                is_code=top_match["is_code"],
                title=top_match["title"],
                score=top_match["score"]
            ))
            
            # Step 3: Dynamic LLM Parameterization
            metrics = engine.benchmark_with_groq(top_match["is_code"], top_match["title"], clause)
            
            field_name = metrics.get("field_name", "Unknown Parameter")
            field_type = metrics.get("field_type", "Mandatory")
            benchmark_threshold = metrics.get("benchmark_threshold", "N/A")
            
            # Step 4: Side-by-Side Comparative Analysis (Simulated deterministic output for safety)
            verdict = "Compliant"
            if "error" in metrics:
                verdict = "Error/Missing Specification"
            else:
                compliant_count += 1
            
            parameter_cards.append(ParameterCard(
                clause=clause,
                standard_code=top_match["is_code"],
                field_name=field_name,
                field_type=field_type,
                benchmark_threshold=benchmark_threshold,
                tender_value="Derived from clause",
                verdict=verdict
            ))
            
            # Logging to Audit DB
            now = datetime.datetime.now().isoformat()
            c.execute("INSERT INTO audit_log (timestamp, reference, clause, standard, verdict) VALUES (?, ?, ?, ?, ?)", 
                      (now, payload.reference_id, clause, top_match["is_code"], verdict))

        conn.commit()
        conn.close()
        
        compliance_rate = (compliant_count / total_clauses) * 100 if total_clauses > 0 else 0
        executive_summary = {
            "total_clauses_evaluated": total_clauses,
            "compliance_rate_percent": round(compliance_rate, 2),
            "overall_verdict": "Compliant" if compliance_rate == 100 else "Review Required"
        }

        return ValidationResponse(
            executive_summary=executive_summary,
            traceability_table=traceability_table,
            granular_parameter_cards=parameter_cards
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@app.get("/api/audit-logs", response_model=List[AuditLogItem])
def get_audit_logs():
    try:
        conn = sqlite3.connect(AUDIT_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT timestamp, reference, clause, standard, verdict FROM audit_log ORDER BY timestamp DESC LIMIT 100")
        rows = c.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            logs.append(AuditLogItem(
                timestamp=row[0],
                reference=row[1],
                clause=row[2],
                standard=row[3],
                verdict=row[4]
            ))
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
