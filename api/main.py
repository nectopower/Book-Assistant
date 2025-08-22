from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, uuid, json, time
from datetime import datetime
from typing import List, Optional, Dict, Literal
import re, glob
import requests
import chromadb
from chromadb.config import Settings

# ========================
# Config da API/LLM
# ========================
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "sk-local")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "book-llm")
DATA_DIR        = os.getenv("DATA_DIR", "./data")
CHAPTER_DIR     = os.path.join(DATA_DIR, "chapters")
os.makedirs(CHAPTER_DIR, exist_ok=True)

# ========================
# ChromaDB Setup
# ========================
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
TENANT = os.getenv("CHROMA_TENANT", "default_tenant")
DATABASE = os.getenv("CHROMA_DATABASE", "default_database")

def ensure_chroma_v2_ready():
    """Verifica se o ChromaDB está pronto e cria tenant/database se necessário"""
    base_v2 = f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2"
    
    # Espera o Chroma responder
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_v2}/heartbeat", timeout=3)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("ChromaDB não está respondendo")
    
    # Cria tenant/database (idempotente)
    try:
        requests.post(f"{base_v2}/tenants", json={"name": TENANT}, timeout=5)
    except Exception:
        pass
    
    try:
        requests.post(
            f"{base_v2}/databases",
            json={"name": DATABASE, "tenant": TENANT},
            timeout=5
        )
    except Exception:
        pass

# Inicializa ChromaDB
try:
    ensure_chroma_v2_ready()
    print("[OK] ChromaDB conectado com sucesso")
    CHROMA_AVAILABLE = True
except Exception as e:
    print(f"[WARN] ChromaDB não disponível: {e}")
    CHROMA_AVAILABLE = False

# Tentativa de cliente Python do Chroma para permitir upsert real
HAVE_CHROMA_CLIENT = False
COLLECTION = None
try:
    if CHROMA_AVAILABLE:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        CHROMA_CLIENT = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
            tenant=TENANT,
            database=DATABASE,
        )
        COLLECTION = CHROMA_CLIENT.get_or_create_collection(
            name="book_memory",
            metadata={"hnsw:space": "cosine"}
        )
        HAVE_CHROMA_CLIENT = True
        print("[OK] Chroma client inicializado (HTTP)")
except Exception as e:
    print(f"[WARN] Chroma client indisponível: {e}")
    HAVE_CHROMA_CLIENT = False
    COLLECTION = None

# ========================
# FastAPI
# ========================
app = FastAPI(title="Book Narrative Assistant", version="1.0")

# ========================
# Schemas
# ========================
class ChapterIn(BaseModel):
    book_id: str
    chapter_id: Optional[str] = None
    title: str
    text: str

class SuggestionIn(BaseModel):
    book_id: str
    current_chapter_title: str
    current_chapter_text: str
    k: int = 8

class CritiqueIn(BaseModel):
    book_id: str
    current_chapter_title: str
    current_chapter_text: str
    k: int = 8

# --- Update schema ---
class ChapterUpdateIn(BaseModel):
    book_id: str
    chapter_id: str
    title: Optional[str] = None   # se None, mantém o atual
    text: Optional[str] = None    # se None, mantém o atual

class MetadataExtractionIn(BaseModel):
    book_id: str
    chapter_title: str
    chapter_text: str

class BookMetadata(BaseModel):
    book_id: str
    title: str
    genre: str
    target_audience: str
    main_characters: List[Dict[str, str]]
    supporting_characters: List[Dict[str, str]]
    locations: List[Dict[str, str]]
    themes: List[str]
    plot_summary: str
    world_building: Dict[str, str]
    timeline: str
    relationships: List[Dict[str, str]]
    conflicts: List[str]
    tone: str
    pacing: str

# ========================
# Helpers
# ========================
def openai_chat(messages: List[Dict], temperature=0.4, max_tokens=800):
    """Chama o vLLM direto, sempre. Força UTF-8 no corpo para evitar erros de parse."""
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
        
        payload = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        r = requests.post(
            f"{OPENAI_API_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if r.ok:
            return r.json()["choices"][0]["message"]["content"]
        else:
            raise Exception(f"vLLM retornou {r.status_code}: {r.text}")
            
    except Exception as e:
        print(f"[DEBUG] openai_chat retornou: {str(e)}")
        raise e

def extract_metadata_from_chapter(book_id: str, chapter_title: str, chapter_text: str) -> BookMetadata:
    """Extrai metadados estruturados do capítulo usando IA"""
    
    prompt = f"""
    Analise o seguinte capítulo e extraia metadados estruturados em formato JSON.
    
    LIVRO: {book_id}
    TÍTULO DO CAPÍTULO: {chapter_title}
    
    TEXTO DO CAPÍTULO:
    {chapter_text[:2000]}...
    
    Extraia e retorne um JSON com a seguinte estrutura:
    {{
        "book_id": "{book_id}",
        "title": "Título do livro baseado no contexto",
        "genre": "Gênero literário (ex: Ficção Científica, Romance, Fantasia)",
        "target_audience": "Público-alvo (ex: Adulto, Jovem Adulto, Infantil)",
        "main_characters": [
            {{"name": "Nome", "role": "Papel na história", "description": "Descrição física e psicológica", "goals": "Objetivos do personagem"}}
        ],
        "supporting_characters": [
            {{"name": "Nome", "role": "Papel na história", "description": "Descrição breve"}}
        ],
        "locations": [
            {{"name": "Nome do local", "type": "Tipo (cidade, planeta, dimensão)", "description": "Descrição do ambiente"}}
        ],
        "themes": ["Tema 1", "Tema 2", "Tema 3"],
        "plot_summary": "Resumo da trama em 2-3 frases",
        "world_building": {{
            "setting": "Ambiente geral da história",
            "time_period": "Período temporal",
            "magic_system": "Sistema mágico se aplicável",
            "technology": "Nível tecnológico"
        }},
        "timeline": "Período temporal da história",
        "relationships": [
            {{"character1": "Nome", "character2": "Nome", "type": "Tipo de relacionamento", "description": "Descrição da relação"}}
        ],
        "conflicts": ["Conflito principal", "Conflito secundário"],
        "tone": "Tom da narrativa (ex: Sombrio, Otimista, Melancólico)",
        "pacing": "Ritmo da narrativa (ex: Rápido, Moderado, Lento)"
    }}
    
    IMPORTANTE: Retorne APENAS o JSON válido, sem texto adicional.
    """
    
    try:
        response = openai_chat([
            {"role": "system", "content": "Você é um assistente especializado em análise literária e extração de metadados estruturados. Sempre retorne JSON válido."},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=1500)
        
        # Tenta extrair o JSON da resposta
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            metadata_dict = json.loads(json_str)
            return BookMetadata(**metadata_dict)
        else:
            raise Exception("JSON não encontrado na resposta")
            
    except Exception as e:
        print(f"[ERROR] Erro ao extrair metadados: {str(e)}")
        # Retorna metadados básicos em caso de erro
        return BookMetadata(
            book_id=book_id,
            title=book_id.replace("_", " ").title(),
            genre="Não identificado",
            target_audience="Não identificado",
            main_characters=[],
            supporting_characters=[],
            locations=[],
            themes=[],
            plot_summary="Não foi possível extrair resumo",
            world_building={},
            timeline="Não identificado",
            relationships=[],
            conflicts=[],
            tone="Não identificado",
            pacing="Não identificado"
        )

# ========================
# Helpers de caminho/leitura/sumário
# ========================
def _chapter_path(book_id: str, chapter_id: str) -> str:
    return os.path.join(CHAPTER_DIR, f"{book_id}__{chapter_id}.md")

def read_chapter(book_id: str, chapter_id: str) -> Dict:
    path = _chapter_path(book_id, chapter_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Capítulo não encontrado")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # título = primeira linha iniciando com "# "
    title = "Capítulo"
    first = content.splitlines()[0] if content else ""
    if first.startswith("# "):
        title = first[2:].strip()
        text = content[len(first):].lstrip()
    else:
        text = content
    return {"title": title, "text": text, "path": path}

def summary_to_text(title: str, summary: Dict) -> str:
    return (
        f"Título: {title}\n"
        f"Personagens: {summary.get('personagens')}\n"
        f"Locais: {summary.get('locais')}\n"
        f"Tempo: {summary.get('tempo')}\n"
        f"Plot points: {summary.get('plot_points')}\n"
        f"Ganchos: {summary.get('ganchos')}\n"
        f"Temas: {summary.get('temas')}\n"
    )

def save_chapter(book_id: str, chapter_id: str, title: str, text: str):
    """Salva capítulo em arquivo local"""
    path = os.path.join(CHAPTER_DIR, f"{book_id}__{chapter_id}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{text}\n")
    return path

def save_suggestions(book_id: str, chapter_id: str, title: str, suggestions: str):
    """Salva sugestões em arquivo local"""
    safe_title = title.replace(' ', '_').replace(':', '_').replace('/', '_').replace('\\', '_')
    filename = f"sugest_{safe_title}__{chapter_id}.md"
    path = os.path.join(CHAPTER_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Sugestões para: {title}\n\n")
        f.write(f"**Livro:** {book_id}\n")
        f.write(f"**Capítulo:** {title}\n")
        f.write(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Sugestões Geradas pela IA\n\n")
        f.write(suggestions)
    return path

def save_critique(book_id: str, chapter_id: str, title: str, critique: str):
    """Salva crítica em arquivo local"""
    safe_title = title.replace(' ', '_').replace(':', '_').replace('/', '_').replace('\\', '_')
    filename = f"critica_{safe_title}__{chapter_id}.md"
    path = os.path.join(CHAPTER_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Crítica para: {title}\n\n")
        f.write(f"**Livro:** {book_id}\n")
        f.write(f"**Capítulo:** {title}\n")
        f.write(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Análise da IA\n\n")
        f.write(critique)
    return path

def upsert_to_chroma(book_id: str, chapter_id: str, title: str, text: str, summary: Dict) -> bool:
    """Salva/atualiza no Chroma usando upsert (idempotente)."""
    if not (CHROMA_AVAILABLE and HAVE_CHROMA_CLIENT and COLLECTION):
        # Sem client → apenas loga sucesso lógico
        print(f"[INFO] (fake) upsert Chroma: {book_id}:{chapter_id}")
        return True
    try:
        summary_text = summary_to_text(title, summary)
        COLLECTION.upsert(
            ids=[
                f"{book_id}:{chapter_id}:summary",
                f"{book_id}:{chapter_id}:full",
            ],
            documents=[summary_text, text],
            metadatas=[
                {
                    "book_id": book_id,
                    "chapter_id": chapter_id,
                    "title": title,
                    "type": "summary",
                },
                {
                    "book_id": book_id,
                    "chapter_id": chapter_id,
                    "title": title,
                    "type": "chapter",
                },
            ],
        )
        print(f"[OK] upsert Chroma: {book_id}:{chapter_id}")
        return True
    except Exception as e:
        print(f"[ERROR] upsert Chroma falhou: {e}")
        return False

def summarize_chapter(title: str, text: str) -> Dict:
    """Gera resumo estruturado do capítulo"""
    sys = {
        "role": "system",
        "content": (
            "Você é um analista literário. Gere um RESUMO ESTRUTURADO curto do capítulo, "
            "nos campos JSON: personagens (lista), locais (lista), tempo (string), "
            "plot_points (lista), temas (lista), tom (string), ganchos (lista). "
            "Responda APENAS com JSON válido."
        ),
    }
    user = {
        "role": "user",
        "content": f"Título: {title}\n\nTexto: {text}",
    }
    
    out = openai_chat([sys, user], temperature=0.2, max_tokens=2000)
    try:
        data = json.loads(out)
    except Exception:
        data = {
            "personagens": [],
            "locais": [],
            "tempo": "",
            "plot_points": [],
            "temas": [],
            "tom": "",
            "ganchos": [],
            "raw": out,
        }
    return data

def get_chromadb_health_string():
    """Retorna o status do ChromaDB"""
    if CHROMA_AVAILABLE:
        try:
            r = requests.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat", timeout=3)
            if r.status_code == 200:
                return "connected"
        except:
            pass
        return "degraded"
    return "disconnected"

# ========================
# Endpoints
# ========================
@app.get("/health")
def health_check():
    """Endpoint de health check simples"""
    return {
        "status": "healthy",
        "message": "API funcionando",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/ready")
def ready():
    """Endpoint para verificar se todos os serviços estão prontos"""
    try:
        # Verifica ChromaDB
        chroma_ok = False
        chroma_status = "disconnected"
        if CHROMA_AVAILABLE:
            try:
                # Testa conexão com ChromaDB
                client = chromadb.HttpClient(
                    host=CHROMA_HOST,
                    port=CHROMA_PORT,
                    settings=Settings(anonymized_telemetry=False)
                )
                # Tenta listar collections (teste simples)
                client.list_collections()
                chroma_ok = True
                chroma_status = "ready"
            except Exception as e:
                chroma_status = f"error: {str(e)}"
        else:
            chroma_status = "not configured"
        
        # Verifica vLLM
        llm_ok = False
        llm_detail = "checking..."
        try:
            # Testa se o vLLM está respondendo
            r = requests.get(f"{OPENAI_API_BASE.replace('/v1', '')}/v1/models", timeout=5)
            if r.status_code == 200:
                llm_ok = True
                llm_detail = "ready"
            else:
                llm_detail = f"status {r.status_code}"
        except Exception as e:
            llm_detail = f"error: {str(e)}"
        
        # Sistema está pronto se ambos os serviços estiverem ok
        ready = chroma_ok and llm_ok
        
        return {
            "ready": ready,
            "chroma": {
                "ok": chroma_ok,
                "status": chroma_status
            },
            "llm": {
                "ok": llm_ok,
                "detail": llm_detail
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "ready": False,
            "error": str(e),
            "chroma": {"ok": False, "status": "error"},
            "llm": {"ok": False, "detail": "error"}
        }

@app.get("/chroma/status")
async def chroma_status_endpoint():
    """Verifica o status do ChromaDB"""
    try:
        if not CHROMA_AVAILABLE:
            return {
                "success": False,
                "status": "unavailable",
                "message": "ChromaDB não foi inicializado corretamente"
            }
        
        client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Tenta fazer uma operação simples
        collections = client.list_collections()
        
        return {
            "success": True,
            "status": "healthy",
            "host": CHROMA_HOST,
            "port": CHROMA_PORT,
            "total_collections": len(collections),
            "message": "ChromaDB está funcionando normalmente"
        }
        
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "error": str(e),
            "message": "Erro ao conectar com ChromaDB"
        }

@app.get("/chroma/collections")
async def list_chroma_collections():
    """Lista todas as coleções do ChromaDB"""
    try:
        if not CHROMA_AVAILABLE:
            raise HTTPException(status_code=503, detail="ChromaDB não disponível")
        
        client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )
        
        collections = client.list_collections()
        
        collections_info = []
        for collection in collections:
            try:
                # Obtém informações básicas da coleção
                count = collection.count()
                collections_info.append({
                    "name": collection.name,
                    "count": count,
                    "metadata_count": count if count > 0 else 0
                })
            except Exception as e:
                collections_info.append({
                    "name": collection.name,
                    "count": "Erro",
                    "metadata_count": "Erro",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "total_collections": len(collections_info),
            "collections": collections_info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/chroma/collection/{collection_name}")
async def get_collection_details(collection_name: str):
    """Obtém detalhes de uma coleção específica"""
    try:
        if not CHROMA_AVAILABLE:
            raise HTTPException(status_code=503, detail="ChromaDB não disponível")
        
        client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            collection = client.get_collection(collection_name)
            results = collection.get()
            
            # Organiza os dados da coleção
            documents = []
            for i, doc_id in enumerate(results["ids"]):
                doc_data = {
                    "id": doc_id,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                    "document_preview": results["documents"][i][:200] + "..." if results["documents"] and len(results["documents"][i]) > 200 else results["documents"][i] if results["documents"] else ""
                }
                documents.append(doc_data)
            
            return {
                "success": True,
                "collection_name": collection_name,
                "total_documents": len(documents),
                "documents": documents
            }
            
        except Exception as e:
            return {
                "success": False,
                "collection_name": collection_name,
                "error": f"Coleção não encontrada: {str(e)}"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chroma/book/{book_id}")
def delete_book_memory(book_id: str):
    """Remove toda a memória de um livro específico do ChromaDB"""
    if not CHROMA_AVAILABLE:
        raise HTTPException(status_code=503, detail="ChromaDB não disponível")
    client = chromadb.HttpClient(
        host=CHROMA_HOST, port=CHROMA_PORT,
        settings=Settings(anonymized_telemetry=False)
    )
    try:
        col = client.get_collection("book_memory")
        # apaga tudo que tiver esse book_id
        col.delete(where={"book_id": book_id})
        return {"success": True, "message": f"Memória do livro '{book_id}' removida."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/chroma/clear")
async def clear_chromadb():
    """Limpa todas as coleções do ChromaDB"""
    try:
        if not CHROMA_AVAILABLE:
            raise HTTPException(status_code=503, detail="ChromaDB não disponível")
        
        client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Lista todas as coleções
        collections = client.list_collections()
        
        # Deleta cada coleção
        deleted_count = 0
        for collection in collections:
            try:
                client.delete_collection(collection.name)
                deleted_count += 1
                print(f"[INFO] Coleção deletada: {collection.name}")
            except Exception as e:
                print(f"[WARN] Erro ao deletar coleção {collection.name}: {e}")
        
        return {
            "success": True,
            "message": f"ChromaDB limpo com sucesso. {deleted_count} coleções deletadas.",
            "deleted_collections": deleted_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chroma/vectorize-existing")
async def vectorize_existing_chapters():
    """Vetoriza todos os capítulos existentes no disco"""
    try:
        if not CHROMA_AVAILABLE:
            raise HTTPException(status_code=503, detail="ChromaDB não disponível")
        
        # Lista todos os arquivos de capítulos
        chapters_dir = "/data/chapters"
        if not os.path.exists(chapters_dir):
            raise HTTPException(status_code=404, detail="Diretório de capítulos não encontrado")
        
        # Encontra todos os arquivos .md
        import glob
        chapter_files = glob.glob(f"{chapters_dir}/*.md")
        
        if not chapter_files:
            return {
                "success": True,
                "message": "Nenhum capítulo encontrado para vetorizar",
                "vectorized_count": 0
            }
        
        vectorized_count = 0
        errors = []
        
        for file_path in chapter_files:
            try:
                # Extrai book_id e chapter_id do nome do arquivo
                filename = os.path.basename(file_path)
                if "__" in filename:
                    parts = filename.split("__", 1)
                    book_id = parts[0]
                    chapter_id = parts[1].replace(".md", "")
                    
                    # Lê o conteúdo do arquivo
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Extrai título e texto
                    lines = content.splitlines()
                    title = "Capítulo"
                    if lines and lines[0].startswith("# "):
                        title = lines[0][2:].strip()
                        text = "\n".join(lines[1:]).lstrip()
                    else:
                        text = content
                    
                    # Extrai metadados
                    metadata = extract_metadata_from_chapter(book_id, title, text)
                    
                    # Vetoriza no ChromaDB
                    chroma_ok = upsert_to_chroma(book_id, chapter_id, title, text, metadata.dict())
                    
                    if chroma_ok:
                        vectorized_count += 1
                        print(f"[INFO] Capítulo vetorizado: {book_id}:{chapter_id}")
                    else:
                        errors.append(f"Falha ao vetorizar {book_id}:{chapter_id}")
                        
            except Exception as e:
                errors.append(f"Erro ao processar {file_path}: {str(e)}")
                print(f"[ERROR] Erro ao processar {file_path}: {e}")
        
        return {
            "success": True,
            "message": f"Vetorização concluída. {vectorized_count} capítulos processados.",
            "vectorized_count": vectorized_count,
            "total_files": len(chapter_files),
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/debug/metadata-extraction")
async def debug_metadata_extraction(book_id: str, chapter_id: str):
    """Debug da extração de metadados para um capítulo específico"""
    try:
        # Lê o capítulo
        chapter_path = os.path.join("/data/chapters", f"{book_id}__{chapter_id}.md")
        if not os.path.exists(chapter_path):
            raise HTTPException(status_code=404, detail="Capítulo não encontrado")
        
        with open(chapter_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extrai título e texto
        lines = content.splitlines()
        title = "Capítulo"
        if lines and lines[0].startswith("# "):
            title = lines[0][2:].strip()
            text = "\n".join(lines[1:]).lstrip()
        else:
            text = content
        
        # Tenta extrair metadados
        try:
            metadata = extract_metadata_from_chapter(book_id, title, text)
            metadata_dict = metadata.dict()
            extraction_success = True
        except Exception as e:
            metadata_dict = {"error": str(e)}
            extraction_success = False
        
        return {
            "success": True,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "title": title,
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "extraction_success": extraction_success,
            "metadata": metadata_dict,
            "raw_content_length": len(content)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test-llm")
def test_llm():
    """Endpoint de teste para verificar se o LLM está funcionando"""
    try:
        sys = {
            "role": "system",
            "content": "Você é um assistente útil. Responda de forma simples e direta."
        }
        user = {
            "role": "user",
            "content": "Olá, como você está? Responda em português brasileiro."
        }
        
        response = openai_chat([sys, user], temperature=0.7, max_tokens=100)
        
        return {
            "success": True,
            "response": response,
            "message": "LLM testado com sucesso"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Erro ao testar LLM"
        }

@app.post("/chapter/save")
async def save_chapter_endpoint(chapter: ChapterIn):
    """Salva um capítulo e extrai metadados"""
    try:
        # Gera ID único se não fornecido
        if not chapter.chapter_id:
            chapter.chapter_id = str(uuid.uuid4())
        
        # Salva o capítulo
        save_chapter(chapter.book_id, chapter.chapter_id, chapter.title, chapter.text)
        
        # Extrai metadados
        metadata = extract_metadata_from_chapter(chapter.book_id, chapter.title, chapter.text)
        
        # Salva no ChromaDB usando a nova função upsert
        chroma_ok = upsert_to_chroma(chapter.book_id, chapter.chapter_id, chapter.title, chapter.text, metadata.dict())
        
        if chroma_ok:
            print(f"[INFO] Capítulo salvo no ChromaDB: {chapter.book_id}:{chapter.chapter_id}")
        else:
            print(f"[WARN] Falha ao salvar no ChromaDB: {chapter.book_id}:{chapter.chapter_id}")
        
        return {
            "success": True,
            "chapter_id": chapter.chapter_id,
            "metadata": metadata.dict(),
            "message": "Capítulo salvo com sucesso e metadados extraídos"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/chapter/update")
async def chapter_update(payload: ChapterUpdateIn):
    """Atualiza (sobrescreve) um capítulo existente, reescrevendo o mesmo arquivo e fazendo upsert no Chroma."""
    try:
        # Lê o capítulo atual para manter campos não enviados
        current = read_chapter(payload.book_id, payload.chapter_id)
        new_title = payload.title if payload.title is not None else current["title"]
        new_text  = payload.text  if payload.text  is not None else current["text"]

        # Regrava o arquivo
        path = _chapter_path(payload.book_id, payload.chapter_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {new_title}\n\n{new_text}\n")

        # Regera resumo/metadados
        summary = summarize_chapter(new_title, new_text)

        # Upsert no Chroma
        chroma_ok = upsert_to_chroma(payload.book_id, payload.chapter_id, new_title, new_text, summary)

        return {
            "chapter_id": payload.chapter_id,
            "saved_path": path,
            "summary": summary if isinstance(summary, dict) else str(summary),
            "chroma_saved": chroma_ok,
            "message": "Capítulo atualizado com sucesso"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/metadata/extract")
async def extract_metadata_endpoint(request: MetadataExtractionIn):
    """Extrai metadados de um capítulo específico"""
    try:
        metadata = extract_metadata_from_chapter(
            request.book_id, 
            request.chapter_title, 
            request.chapter_text
        )
        
        return {
            "success": True,
            "metadata": metadata.dict(),
            "message": "Metadados extraídos com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metadata/book/{book_id}")
async def get_book_metadata(book_id: str):
    """Obtém todos os metadados de um livro"""
    try:
        if not CHROMA_AVAILABLE:
            raise HTTPException(status_code=503, detail="ChromaDB não disponível")
        
        client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Busca na coleção unificada book_memory
        try:
            collection = client.get_collection("book_memory")
            results = collection.get()
            
            # Organiza os metadados por capítulo, filtrando pelo book_id
            chapters_metadata = []
            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i]
                # Só inclui documentos do livro específico
                if metadata.get("book_id") == book_id:
                    chapters_metadata.append({
                        "chapter_id": metadata.get("chapter_id"),
                        "title": metadata.get("title"),
                        "type": metadata.get("type"),
                        "timestamp": metadata.get("timestamp")
                    })
            
            return {
                "success": True,
                "book_id": book_id,
                "chapters_count": len(chapters_metadata),
                "chapters": chapters_metadata
            }
            
        except Exception as e:
            return {
                "success": True,
                "book_id": book_id,
                "chapters_count": 0,
                "chapters": [],
                "message": f"Livro não encontrado ou sem metadados: {str(e)}"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/suggest")
def suggest_next(payload: SuggestionIn):
    """Sugere próximos passos baseado no capítulo atual"""
    print(f"[DEBUG] /suggest chamado com payload: {payload}")
    try:
        sys = {
            "role": "system",
            "content": (
                "Você é um co-roteirista experiente. Analise o capítulo atual e sugira "
                "3-5 próximos passos narrativos coerentes. Seja criativo mas mantenha "
                "a continuidade da história. Responda em português brasileiro."
            ),
        }
        user = {
            "role": "user",
            "content": f"Título: {payload.current_chapter_title}\n\nTexto: {payload.current_chapter_text}",
        }
        
        print(f"[DEBUG] Chamando openai_chat com mensagens: {[sys, user]}")
        suggestions = openai_chat([sys, user], temperature=0.7, max_tokens=2000)
        print(f"[DEBUG] openai_chat retornou: {suggestions[:100]}...")
        
        # Salva as sugestões automaticamente
        chapter_id = str(uuid.uuid4())
        suggestions_path = save_suggestions(payload.book_id, chapter_id, payload.current_chapter_title, suggestions)
        print(f"[INFO] Sugestões salvas em: {suggestions_path}")
        
        return {
            "suggestions": suggestions,
            "book_id": payload.book_id,
            "chapter_title": payload.current_chapter_title,
            "suggestions_file": os.path.basename(suggestions_path),
            "message": "Sugestões geradas e salvas com sucesso"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/critique")
def critique_chapter(payload: CritiqueIn):
    """Faz crítica de coerência do capítulo"""
    try:
        sys = {
            "role": "system",
            "content": (
                "Você é um editor literário experiente. Analise o capítulo atual e "
                "identifique possíveis problemas de coerência, continuidade ou lógica. "
                "Seja construtivo e sugira melhorias. Responda em português brasileiro."
            ),
        }
        user = {
            "role": "user",
            "content": f"Título: {payload.current_chapter_title}\n\nTexto: {payload.current_chapter_text}",
        }
        
        critique = openai_chat([sys, user], temperature=0.3, max_tokens=2000)
        
        # Salva a crítica automaticamente
        chapter_id = str(uuid.uuid4())
        critique_path = save_critique(payload.book_id, chapter_id, payload.current_chapter_title, critique)
        print(f"[INFO] Crítica salva em: {critique_path}")
        
        return {
            "critique": critique,
            "book_id": payload.book_id,
            "chapter_title": payload.current_chapter_title,
            "critique_file": os.path.basename(critique_path),
            "message": "Crítica gerada e salva com sucesso"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================
# ====== NOVOS RECURSOS: Perguntar / Idear / Expandir ======
# ========================
import numpy as np

# Embeddings (lazy): tentamos carregar MiniLM; se falhar, caímos em score por palavras
_embed_model = None
def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as e:
            print(f"[WARN] Não foi possível carregar sentence-transformers: {e}")
            _embed_model = False  # indica fallback
    return _embed_model

def _read_chapters_fs(book_id: str):
    """Lê capítulos do FS /data/chapters/<book_id>__*.md"""
    base = "/data/chapters"
    files = sorted(glob.glob(os.path.join(base, f"{book_id}__*.md")))
    docs = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                txt = f.read()
            # título = primeira linha '# ' ou 1ª linha não vazia
            first = next((ln.strip() for ln in txt.splitlines() if ln.strip()), "")
            title = first[2:].strip() if first.startswith("# ") else first[:120] or "Capítulo"
            chapter_id = os.path.basename(fp).split("__", 1)[1].replace(".md", "")
            docs.append({"id": chapter_id, "title": title, "text": txt, "file": fp})
        except Exception as e:
            print(f"[WARN] Falha ao ler {fp}: {e}")
    return docs

def _semantic_top_k(query: str, docs, k: int = 8):
    """Top-K por similaridade (se houver embeddings) ou por contagem de palavras-chave."""
    if not docs:
        return []
    model = _get_embed_model()
    if model:
        # Embed (normalizado)
        qv = model.encode([query], normalize_embeddings=True)
        dv = model.encode([ (d["title"] + "\n" + d["text"][:2000]) for d in docs ], normalize_embeddings=True)
        sims = (dv @ qv[0])
        idx = np.argsort(-sims)[:k]
        out = []
        for i in idx:
            d = docs[int(i)]
            out.append({**d, "score": float(sims[int(i)])})
        return out
    # Fallback: ranking ingênuo por match de termos
    terms = [t for t in re.findall(r"\w{3,}", query.lower())]
    def score(d):
        s = (d["title"] + " " + d["text"][:4000]).lower()
        return sum(s.count(t) for t in terms)
    scored = sorted(docs, key=score, reverse=True)[:k]
    for d in scored:
        d["score"] = 0.0
    return scored

def _fmt_context(hits):
    blocks = []
    for h in hits:
        preview = re.sub(r"\s+", " ", h["text"])[:600]
        blocks.append(f"- Capítulo {h['id']} — {h['title']}\n  Trecho: {preview}")
    return "\n".join(blocks) if blocks else "(sem contexto recuperado)"

def _build_context(book_id: Optional[str], use_memory: str, k: int,
                   include_current: bool, current_title: Optional[str], current_text: Optional[str]):
    blocks = []
    if use_memory in ("book", "book+current") and book_id:
        hits = _semantic_top_k(current_title or "", _read_chapters_fs(book_id), k=k)
        blocks.append(_fmt_context(hits))
    if include_current or use_memory == "book+current":
        if current_text:
            blocks.append(f"## CAPÍTULO ATUAL: {current_title or 'Capítulo atual'}\n{current_text}")
    return "\n\n".join([b for b in blocks if b]) or "(sem contexto recuperado)"

class AskIn(BaseModel):
    book_id: str
    question: str
    k: int = 8
    use_memory: bool = True
    include_current: bool = False
    current_title: str | None = None
    current_text: str | None = None
    show_prompt: bool = False

@app.post("/ask")
def ask(inp: AskIn):
    """Pergunta livre ao copiloto, com RAG opcional (FS-based)."""
    # Recupera contexto
    context = ""
    if inp.use_memory:
        docs = _read_chapters_fs(inp.book_id)
        hits = _semantic_top_k(inp.question, docs, k=inp.k)
        context = _fmt_context(hits)
    # Capítulo atual opcional
    cur_block = ""
    if inp.include_current and inp.current_text:
        cur_t = inp.current_title or "Capítulo atual"
        cur_block = f"\n## CAPÍTULO ATUAL: {cur_t}\n{inp.current_text}\n"

    system = {
        "role": "system",
        "content": (
            "Você é um coautor atento à continuidade. Use ESTRITAMENTE o contexto fornecido "
            "para responder. Se faltar contexto, diga o que precisa. Responda em PT-BR."
        )
    }
    user = {
        "role": "user",
        "content": f"## CONTEXTO (Memória)\n{context}{cur_block}\n\n## PERGUNTA\n{inp.question}"
    }
    prompt_preview = f"[SYSTEM]\n{system['content']}\n\n[USER]\n{user['content']}" if inp.show_prompt else None
    out = openai_chat([system, user], temperature=0.5, max_tokens=1200)
    return {"answer": out, "prompt_preview": prompt_preview}

class IdeateIn(BaseModel):
    book_id: str | None = None
    theme: str
    n: int = 5
    use_memory: bool = False
    k: int = 6
    style: str | None = None
    show_prompt: bool = False

@app.post("/ideate")
def ideate(inp: IdeateIn):
    """Gera N ideias estruturadas (JSON) a partir de um tema (com memória opcional)."""
    context = ""
    if inp.use_memory and inp.book_id:
        hits = _semantic_top_k(inp.theme, _read_chapters_fs(inp.book_id), k=inp.k)
        context = _fmt_context(hits)
    style = f"\nPreferências/estilo: {inp.style}" if inp.style else ""
    system = {
        "role": "system",
        "content": (
            "Você é um roteirista. Gere ideias de cenas/capítulos em JSON (lista), sem texto extra. "
            "Cada item deve ter: title, logline, conflict, twist, stakes, pov, tone."
        )
    }
    user = {
        "role": "user",
        "content": (
            f"Tema / logline: {inp.theme}{style}\n"
            f"{'Contexto: '+context if context else ''}\n"
            f"Gere {inp.n} ideias distintas. Responda APENAS com JSON válido."
        )
    }
    preview = f"[SYSTEM]\n{system['content']}\n\n[USER]\n{user['content']}" if inp.show_prompt else None
    raw = openai_chat([system, user], temperature=0.9, max_tokens=1600)
    ideas = []
    try:
        ideas = json.loads(raw)
        if isinstance(ideas, dict):  # caso o modelo retorne {"ideas":[...]}
            ideas = ideas.get("ideas", [])
    except Exception:
        # fallback: lista simples numerada
        ideas = [{"title": f"Ideia {i+1}", "logline": line.strip()} for i, line in enumerate(raw.split("\n")) if line.strip()]
    return {"ideas": ideas, "prompt_preview": preview}

class ExpandIn(BaseModel):
    book_id: Optional[str] = None

    # de onde vem a base do texto
    source: Literal["idea", "chapter"] = "idea"
    idea: Optional[str] = None          # usado quando source="idea"
    chapter_id: Optional[str] = None    # usado quando source="chapter"

    # controle de contexto/memória
    use_memory: Literal["none", "book", "book+current"] = "book"
    include_current: bool = False       # injeta o que o usuário está editando agora
    current_title: Optional[str] = None
    current_text: Optional[str] = None
    k: int = 8

    # saída
    length: str = "500-800 palavras"
    save_as_chapter: bool = False
    title: Optional[str] = None
    show_prompt: bool = False

@app.get("/chapters/{book_id}")
def list_chapters(book_id: str):
    """Lista todos os capítulos de um livro"""
    docs = _read_chapters_fs(book_id)
    return {"chapters": [{"id": d["id"], "title": d["title"]} for d in docs]}

@app.post("/expand")
def expand(inp: ExpandIn):
    """Escreve uma cena a partir de uma ideia ou capítulo, com controle preciso de contexto."""
    # Decide a base (ideia ou capítulo)
    if inp.source == "chapter":
        if not (inp.book_id and inp.chapter_id):
            raise HTTPException(status_code=400, detail="Para 'chapter', envie 'book_id' e 'chapter_id'.")
        ch = read_chapter(inp.book_id, inp.chapter_id)
        base_text = ch["text"]
        base_kind = "CAPÍTULO"
    else:
        if not inp.idea:
            raise HTTPException(status_code=400, detail="Para 'idea', envie o campo 'idea'.")
        base_text = inp.idea
        base_kind = "IDEIA"

    # Constrói o contexto de acordo com o modo escolhido
    context = _build_context(
        inp.book_id, inp.use_memory, inp.k, inp.include_current, inp.current_title, inp.current_text
    )

    system = {
        "role": "system",
        "content": (
            "Você é um co-roteirista. Escreva uma CENA fluida e cinematográfica, coerente com o contexto. "
            "Mantenha consistência de personagens e tom. PT-BR."
        )
    }
    user = {
        "role": "user",
        "content": (
            f"## CONTEXTO (Memória)\n{context}\n\n"
            f"## BASE ({base_kind})\n{base_text}\n\n"
            f"Diretriz de tamanho: {inp.length}\n"
            "Entregue apenas a cena, sem metacomentários."
        )
    }
    preview = f"[SYSTEM]\n{system['content']}\n\n[USER]\n{user['content']}" if inp.show_prompt else None

    scene = openai_chat([system, user], temperature=0.8, max_tokens=2200)

    saved = None
    if inp.save_as_chapter and inp.book_id:
        ch_id = str(uuid.uuid4())[:8]
        title = inp.title or ("Cena gerada" if inp.source == "idea" else f"Expansão de {base_kind.lower()}")
        path = save_chapter(inp.book_id, ch_id, title, scene)
        saved = {"chapter_id": ch_id, "path": path, "title": title}

    return {"scene": scene, "saved": saved, "prompt_preview": preview}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
