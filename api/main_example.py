import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from chroma_bootstrap import ensure_chroma_v2_ready, CHROMA_HOST, CHROMA_PORT, TENANT, DATABASE

load_dotenv()

# garante Chroma v2 com tenant/db prontos
ensure_chroma_v2_ready()

app = FastAPI()

# cliente Chroma v2
client = chromadb.HttpClient(
    host=CHROMA_HOST,
    port=int(CHROMA_PORT),
    settings=Settings(anonymized_telemetry=False),
    tenant=TENANT,
    database=DATABASE,
)

# health
@app.get("/health")
def health():
    return {"ok": True}
