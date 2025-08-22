import os
import time
import requests
import streamlit as st
import re
import json
from typing import List, Dict

st.set_page_config(page_title="Copiloto de Livro", layout="wide", page_icon="✍️")

CSS = """
<style>
/* limpa topo e footer do streamlit */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* container máximo um pouco mais amplo */
.main .block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px;}

/* "cartões" */
.card {
  background: var(--secondary-background-color);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 14px;
  padding: 18px 18px 14px 18px;
  box-shadow: 0 10px 25px rgba(0,0,0,0.18);
  margin-bottom: 0.75rem;
}

/* títulos menores e clean */
h1, h2, h3 { letter-spacing: .2px; }
h2 { margin-top: .2rem; }

/* badges */
.badges { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.badge {
  display:inline-flex; gap:6px; align-items:center;
  font-size: 12.5px; padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.08); opacity:.95
}
.badge.ok { background: rgba(110,231,183,.12); color:#7CEABF; }
.badge.warn { background: rgba(251,191,36,.12); color:#FACC15; }
.badge.err { background: rgba(248,113,113,.12); color:#F87171; }

/* botões ocuparem largura */
.stButton button { width: 100%; border-radius: 10px; padding:.6rem .9rem; }

/* área de texto mais "codestyle" */
textarea, .stTextArea textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  line-height: 1.5;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ========================
# Constantes e Helpers
# ========================
BOOKS_DIR = "/data/books"
CHAPTERS_DIR = "/data/chapters"
os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(CHAPTERS_DIR, exist_ok=True)

def slugify(name: str) -> str:
    s = name.strip().lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9-_]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    return (s[:64] or "livro")

API_BASE = os.getenv("API_BASE", "http://api:8010")
VLLM_BASE = os.getenv("VLLM_BASE", "http://vllm:8000")
CHROMA_BASE = os.getenv("CHROMA_BASE", "http://chroma:8000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-local")

# ========================
# Funções de readiness melhoradas
# ========================
def _short_err(exc: Exception) -> str:
    s = str(exc)
    # encurta msgs típicas
    if "Failed to establish a new connection" in s or "Max retries exceeded" in s:
        return "conexão recusada"
    if "Read timed out" in s or "timeout" in s.lower():
        return "timeout"
    return s[:120]  # corta caso venha muito grande

def check_api_ready():
    try:
        r = requests.get(f"{API_BASE}/ready", timeout=3)
        if r.ok:
            j = r.json()
            j["source"] = "api"
            return j
        return {"ready": False, "source": "api", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ready": False, "source": "api", "detail": _short_err(e)}

def probe_direct():
    # vLLM
    llm_ok, llm_detail = False, ""
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
        r = requests.get(f"{VLLM_BASE}/v1/models", headers=headers, timeout=3)
        llm_ok = (r.status_code == 200)
        if not llm_ok:
            llm_detail = f"HTTP {r.status_code}"
    except Exception as e:
        llm_detail = _short_err(e)

    # Chroma
    chroma_ok, chroma_detail = False, ""
    try:
        r = requests.get(f"{CHROMA_BASE}/api/v2/heartbeat", timeout=3)
        chroma_ok = (r.status_code == 200)
        if not chroma_ok:
            chroma_detail = f"HTTP {r.status_code}"
    except Exception as e:
        chroma_detail = _short_err(e)

    return {
        "ready": False,
        "api": False,
        "llm": {"ok": llm_ok, "detail": llm_detail},
        "chroma": {"ok": chroma_ok, "detail": chroma_detail},
        "source": "direct",
    }

def readiness_loop(max_wait=900):
    status_line = st.empty()   # um único bloco que será reescrito
    detail_line = st.empty()
    t0 = time.time()
    attempt = 0
    last_key = ""
    same_count = 0

    while time.time() - t0 < max_wait:
        api_info = check_api_ready()
        if api_info.get("ready"):
            status_line.success("✅ Tudo pronto!")
            detail_line.write(f"API ok • vLLM ok • Chroma {api_info['chroma']['status'] if 'chroma' in api_info else 'ok'}")
            return api_info

        # API ainda não pronta → sondar direto
        direct = probe_direct()

        # compõe uma "chave de estado" para detectar repetição
        key = f"api:{api_info.get('ready', False)}|llm:{direct['llm']['ok']}|chroma:{direct['chroma']['ok']}"
        if key == last_key:
            same_count += 1
        else:
            same_count = 1
            last_key = key

        # backoff exponencial com teto de 10s
        delay = min(2 ** min(attempt, 4), 10)  # 1,2,4,8,10,10…
        attempt += 1

        # linha principal sempre atualizada
        status_line.info(f"⏳ Inicializando serviços… (tentativa {attempt}, próxima verificação em {delay}s)")

        # detalhes só quando o estado mudou OU a cada 3 repetições
        if same_count == 1 or same_count % 3 == 0:
            api_txt = "ok" if api_info.get("api") else (api_info.get("detail") or "offline")
            llm_txt = "ok" if direct["llm"]["ok"] else (direct["llm"]["detail"] or "carregando…")
            chm_txt = "ok" if direct["chroma"]["ok"] else (direct["chroma"]["detail"] or "carregando…")
            detail_line.write(f"API: {api_txt} • vLLM: {llm_txt} • Chroma: {chm_txt}")

        time.sleep(delay)

    status_line.error("❌ Tempo esgotado para inicialização.")
    detail_line.write("Verifique logs dos containers (vllm, api, chroma).")
    st.stop()

# ========================
# Sistema de gerenciamento de livros
# ========================
def get_existing_books() -> List[Dict]:
    """Obtém lista de livros existentes baseado nos metadados e arquivos"""
    books = []

    # 2.1 — ler metadados oficiais
    try:
        for fn in os.listdir(BOOKS_DIR):
            if fn.endswith(".json"):
                with open(os.path.join(BOOKS_DIR, fn), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                books.append({
                    "id": meta["id"],
                    "name": meta.get("name", meta["id"]),
                    "chapters": 0,
                    "suggestions": 0,
                    "critiques": 0,
                })
    except FileNotFoundError:
        pass

    # 2.2 — se não houver meta, inferir pelos arquivos de capítulo (fallback)
    if not books and os.path.exists(CHAPTERS_DIR):
        import glob
        all_files = glob.glob(f"{CHAPTERS_DIR}/*.md")
        book_ids = set()
        for p in all_files:
            fn = os.path.basename(p)
            if "__" in fn:
                book_ids.add(fn.split("__", 1)[0])

        for bid in sorted(book_ids):
            books.append({
                "id": bid,
                "name": bid.replace("_", " ").replace("-", " ").title(),
                "chapters": 0,
                "suggestions": 0,
                "critiques": 0,
            })

    # 2.3 — contar arquivos por livro
    import glob
    for b in books:
        bid = b["id"]
        chs = glob.glob(f"{CHAPTERS_DIR}/{bid}__*.md")
        b["chapters"] = len([x for x in chs if not os.path.basename(x).startswith(("sugest_", "critica_"))])
        b["suggestions"] = len(glob.glob(f"{CHAPTERS_DIR}/sugest_{bid}__*.md"))
        b["critiques"]   = len(glob.glob(f"{CHAPTERS_DIR}/critica_{bid}__*.md"))

    return books

def get_book_chapters(book_id: str) -> List[Dict]:
    """Obtém lista de capítulos de um livro específico"""
    try:
        import glob
        import os
        
        # Usa caminho absoluto correto
        chapters_dir = "/data/chapters"
        
        if not os.path.exists(chapters_dir):
            return []
        
        # Busca por capítulos do livro
        pattern = f"{chapters_dir}/{book_id}__*.md"
        files = glob.glob(pattern)
        
        chapters = []
        for file in files:
            filename = os.path.basename(file)
            if "__" in filename:
                chapter_id = filename.split("__")[1].replace(".md", "")
                
                # Lê o conteúdo para extrair título
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Extrai título da primeira linha (formato Markdown)
                        lines = content.split('\n')
                        title = "Capítulo sem título"
                        if lines and lines[0].startswith('# '):
                            title = lines[0][2:].strip()
                        elif lines and lines[0].strip():
                            title = lines[0].strip()
                        
                        chapters.append({
                            "id": chapter_id,
                            "title": title,
                            "file_path": file,
                            "content": content,
                            "size": len(content),
                            "modified": os.path.getmtime(file)
                        })
                except Exception as e:
                    st.warning(f"Erro ao ler capítulo {filename}: {str(e)}")
        
        # Ordena por data de modificação (mais recente primeiro)
        chapters.sort(key=lambda x: x["modified"], reverse=True)
        return chapters
        
    except Exception as e:
        st.error(f"Erro ao listar capítulos: {str(e)}")
        return []

def create_new_book(book_id: str, book_name: str) -> bool:
    """Cria um novo livro com slug automático e metadados"""
    if not (book_name or "").strip():
        st.error("Nome do livro não pode estar vazio")
        return False

    if not (book_id or "").strip():
        book_id = slugify(book_name)

    # já existe?
    existing = get_existing_books()
    if any(b["id"] == book_id for b in existing):
        st.error(f"Já existe um livro com ID '{book_id}'")
        return False

    meta = {
        "id": book_id,
        "name": book_name.strip(),
        "created_at": time.time(),
    }
    os.makedirs(BOOKS_DIR, exist_ok=True)
    with open(os.path.join(BOOKS_DIR, f"{book_id}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # selecionar automaticamente
    st.session_state["selected_book"] = meta
    st.success(f"✅ Livro '{book_name}' (ID: {book_id}) criado!")
    return True

# ========================
# Inicialização dos serviços
# ========================
with st.spinner("Checando serviços…"):
    info = readiness_loop()
st.session_state["ready"] = True

def badge(text: str, kind: str="ok"):
    return f'<span class="badge {kind}">● {text}</span>'

# Cabeçalho "hero"
col_logo, col_status = st.columns([0.6, 0.4])
with col_logo:
    st.markdown("### ✍️ **Copiloto de Escrita**")
    st.caption("vLLM + RAG • editor com memória • ideias e análise em um só lugar")

with col_status:
    llm_ok = info.get("llm",{}).get("ok", False)
    chroma_ok = info.get("chroma",{}).get("ok", False) or info.get("chroma",{}).get("status") == "ready"
    api_ok = True

    b_api   = badge("API pronta", "ok" if api_ok else "err")
    b_llm   = badge("LLM ok" if llm_ok else "LLM carregando…", "ok" if llm_ok else "warn")
    b_chrm  = badge("Chroma ok" if chroma_ok else "Chroma indisponível", "ok" if chroma_ok else "warn")

    st.markdown(f'<div class="badges">{b_api}{b_llm}{b_chrm}</div>', unsafe_allow_html=True)

# ========================
# Abas principais
# ========================
tab_editor, tab_copilot, tab_memory, tab_tools = st.tabs(
    ["✍️ Editor", "🤖 Copiloto", "🧠 Memória", "🛠️ Manutenção"]
)

# ========================
# Sidebar com gerenciamento de livros
# ========================
with st.sidebar:
    st.header("📚 Gerenciamento de Livros")
    
    # Toggle para mostrar detalhes (removido para limpar interface)
    
    # Seção de livros existentes
    existing_books = get_existing_books()
    
    # Botão de debug para forçar atualização
    if st.sidebar.button("🔄 Atualizar Lista de Livros", type="secondary"):
        st.sidebar.info("🔄 Atualizando lista...")
        st.rerun()
    
    if existing_books:
        st.subheader("📖 Livros Existentes")
        
        # Dropdown para seleção
        book_options = [f"{book['name']} ({book['id']})" for book in existing_books]
        selected_book_display = st.selectbox(
            "Selecione um livro:",
            book_options,
            index=0,
            help="Escolha um livro para continuar escrevendo"
        )
        
        # Extrai o book_id da seleção
        selected_book = None
        for book in existing_books:
            if f"{book['name']} ({book['id']})" == selected_book_display:
                selected_book = book
                break
        
        if selected_book:
            st.info(f"📊 **{selected_book['name']}**")
            st.write(f"📝 Capítulos: {selected_book['chapters']}")
            st.write(f"💡 Sugestões: {selected_book['suggestions']}")
            st.write(f"🧭 Críticas: {selected_book['critiques']}")
            
            # Define o book_id selecionado
            book_id = selected_book['id']
            st.session_state["selected_book"] = selected_book
            
            # Mostra capítulos do livro selecionado
            if selected_book['chapters'] > 0:
                st.subheader("📖 Capítulos Disponíveis")
                chapters = get_book_chapters(book_id)
                
                if chapters:
                    # Dropdown para selecionar capítulo
                    chapter_options = [f"{ch['title']} ({ch['id'][:8]}...)" for ch in chapters]
                    selected_chapter_idx = st.selectbox(
                        "Selecione um capítulo:",
                        range(len(chapters)),
                        format_func=lambda x: chapter_options[x],
                        help="Escolha um capítulo para carregar e continuar"
                    )
                    
                    if st.button("📂 Carregar Capítulo", type="secondary"):
                        selected_chapter = chapters[selected_chapter_idx]
                        st.session_state["editing_chapter"] = selected_chapter
                        st.session_state["editing_chapter_id"] = selected_chapter["id"]
                        # Preenche os campos editáveis
                        st.session_state["shared_chapter_title"] = selected_chapter["title"]
                        st.session_state["shared_chapter_text"]  = selected_chapter["content"]
                        # Habilita modo sobrescrever (será feito no rerun)
                        st.success(f"✅ Capítulo '{selected_chapter['title']}' carregado para edição!")
                        st.rerun()
                
                # Botão para visualizar metadados
                if st.button("🎭 Visualizar Metadados", type="secondary"):
                    st.session_state["show_metadata"] = True
                    st.rerun()
                
                # Mostra metadados se solicitado
                if st.session_state.get("show_metadata", False):
                    st.subheader("🎭 Metadados do Livro")
                    
                    try:
                        import requests
                        response = requests.get(f"{API_BASE}/metadata/book/{book_id}", timeout=10)
                        
                        if response.ok:
                            data = response.json()
                            
                            if data["chapters_count"] > 0:
                                st.success(f"📊 **{data['chapters_count']} capítulos analisados**")
                                
                                # Mostra metadados por capítulo
                                for chapter_meta in data["chapters"][:3]:  # Mostra só os 3 primeiros
                                    with st.expander(f"📖 {chapter_meta['title']}", expanded=False):
                                        col1, col2 = st.columns(2)
                                        
                                        with col1:
                                            st.write(f"**📝 Tipo:** {chapter_meta.get('type', 'N/A')}")
                                            st.write(f"**🆔 ID:** {chapter_meta.get('chapter_id', 'N/A')}")
                                        
                                        with col2:
                                            if chapter_meta.get('timestamp'):
                                                st.write(f"**⏰ Timestamp:** {chapter_meta['timestamp']}")
                                            else:
                                                st.write("**⏰ Timestamp:** N/A")
                                        
                                        st.info("💡 Para ver metadados completos, use o botão '🔍 Ver Status do ChromaDB'")
                                
                                if data["chapters_count"] > 3:
                                    st.info(f"📚 ... e mais {data['chapters_count'] - 3} capítulos com metadados")
                                
                                # Botão para fechar
                                if st.button("❌ Fechar Metadados", type="secondary"):
                                    st.session_state["show_metadata"] = False
                                    st.rerun()
                                    
                            else:
                                st.info("📝 Nenhum capítulo com metadados encontrado. Salve um capítulo para gerar metadados.")
                                
                        else:
                            st.error(f"❌ Erro ao carregar metadados: {response.status_code}")
                            
                    except Exception as e:
                        st.error(f"❌ Erro de conexão: {str(e)}")
                        st.info("💡 Certifique-se de que a API está rodando")
            
    else:
        st.info("📚 Nenhum livro encontrado. Crie um novo livro abaixo.")
        st.session_state["selected_book"] = None
    
    # Seção para criar novo livro
    st.subheader("🆕 Criar Novo Livro")
    
    with st.form("novo_livro"):
        new_book_id = st.text_input(
            "ID do livro (sem espaços):",
            value="",
            placeholder="ex: meu-romance, aventura-espacial",
            help="Use apenas letras, números, hífens e underscores"
        )
        new_book_name = st.text_input(
            "Nome do livro:",
            value="",
            placeholder="ex: Meu Romance, Aventura Espacial",
            help="Nome completo do livro para exibição"
        )
        
        if st.form_submit_button("📚 Criar Livro"):
            if create_new_book(new_book_id, new_book_name):
                st.rerun()  # lista atualiza e o editor já habilita
    
    # Configurações gerais
    st.divider()
    st.header("⚙️ Configurações")
    
    # SEM fallback. Exige seleção/criação primeiro.
    sel = st.session_state.get("selected_book")
    if not sel:
        st.warning("Selecione um livro na barra lateral ou crie um novo para habilitar o editor.")
        st.stop()

    book_id = sel["id"]
    st.info(f"📚 **Livro selecionado:** {sel.get('name', book_id)}  —  ID: {book_id}")
    
    # ChromaDB Explorer removido da sidebar - agora está na aba Memória
    
    k = st.slider("Memória (Top-K)", 3, 15, 8, help="Quanto maior o K, mais contexto recupera dos capítulos anteriores.")
    
    # Status dos serviços
    st.divider()
    st.header("🔧 Status dos Serviços")
    
    if st.session_state.get("ready"):
        st.success("✅ Sistema Pronto")
        st.info("🎯 vLLM: Qwen2.5-14B-Instruct")
        st.info("💾 ChromaDB: Conectado")
        st.info("🚀 API: Funcionando")
    else:
        st.warning("⏳ Inicializando...")
        st.info("🔄 vLLM: Carregando modelo")
        st.info("🔄 ChromaDB: Conectando")

# ========================
# Aba Editor
# ========================
with tab_editor:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("✍️ Editor de Capítulo")

# Verifica se há um capítulo sendo editado
editing_chapter = st.session_state.get("editing_chapter")

# Inicializa valores padrão de estado
st.session_state.setdefault("overwrite", False)
st.session_state.setdefault("editing_chapter_id", None)

# se estiver editando, garanta que os campos do editor tenham o conteúdo carregado
if editing_chapter:
    st.session_state.setdefault("shared_chapter_title", editing_chapter["title"])
    st.session_state.setdefault("shared_chapter_text",  editing_chapter["content"])
    st.info(f"✏️ **Editando:** {editing_chapter['title']}")

# Mostra informações do livro selecionado (book_id já definido na sidebar)
st.info(f"📚 **Livro selecionado:** {book_id}")

# CAMPOS ÚNICOS - SEM DUPLICAÇÃO
chapter_title = st.text_input(
    "Título do capítulo",
    key="shared_chapter_title",  # usa sempre o mesmo estado
    disabled=not st.session_state.get("ready"),
)

chapter_text = st.text_area(
    "Texto do capítulo (cole aqui)",
    key="shared_chapter_text",   # usa sempre o mesmo estado
    height=300,
    disabled=not st.session_state.get("ready"),
    placeholder="Digite ou cole o texto do capítulo aqui..."
)

# Controle claro de comportamento do salvar
# Define o valor inicial baseado no estado
initial_overwrite = bool(st.session_state.get("editing_chapter_id"))
st.toggle("🔁 Sobrescrever capítulo carregado", key="overwrite", value=initial_overwrite,
          help="Quando ligado, salva por cima do capítulo carregado. Desligado salva como um novo capítulo.")

# BOTÕES DE AÇÃO - ÚNICOS
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("💾 Salvar Capítulo", type="primary", disabled=not st.session_state.get("ready"), use_container_width=True):
        if chapter_title and chapter_text:
            with st.spinner("Salvando capítulo..."):
                overwrite = st.session_state.get("overwrite")
                chap_id = st.session_state.get("editing_chapter_id")

                if overwrite and chap_id:
                    # UPDATE (PUT)
                    payload = {
                        "book_id": book_id,
                        "chapter_id": chap_id,
                        "title": chapter_title,
                        "text": chapter_text,
                    }
                    try:
                        r = requests.put(f"{API_BASE}/chapter/update", json=payload, timeout=600)
                        if r.ok:
                            data = r.json()
                            st.success("✅ Capítulo atualizado (sobrescrito) com sucesso!")
                            st.info(f"📁 ID: {data['chapter_id']}")
                            # mantém editor apontando para o capítulo atualizado
                            st.session_state["editing_chapter"] = {
                                "id": chap_id,
                                "title": chapter_title,
                                "content": chapter_text
                            }
                            st.rerun()
                        else:
                            st.error(f"❌ Erro ao atualizar: {r.text}")
                    except Exception as e:
                        st.error(f"❌ Erro de conexão: {str(e)}")
                else:
                    # CREATE (POST)
                    payload = {
                        "book_id": book_id,
                        "title": chapter_title,
                        "text": chapter_text
                    }
                    try:
                        r = requests.post(f"{API_BASE}/chapter/save", json=payload, timeout=600)
                        if r.ok:
                            data = r.json()
                            st.success("✅ Capítulo salvo como NOVO com sucesso!")
                            st.info(f"📁 ID: {data['chapter_id']}")
                            # passa a editar o novo capítulo e habilita overwrite a partir de agora
                            st.session_state["editing_chapter"] = {
                                "id": data["chapter_id"],
                                "title": chapter_title,
                                "content": chapter_text
                            }
                            st.session_state["editing_chapter_id"] = data["chapter_id"]
                            # Não modifica overwrite aqui, apenas recarrega
                            st.rerun()
                        else:
                            st.error(f"❌ Erro ao salvar: {r.text}")
                    except Exception as e:
                        st.error(f"❌ Erro de conexão: {str(e)}")
        else:
            st.error("❌ Preencha o título e o texto do capítulo")

with col2:
    if st.button("💡 Gerar Sugestões", type="secondary", disabled=not st.session_state.get("ready"), use_container_width=True):
        if chapter_title and chapter_text:
            with st.spinner("Gerando sugestões com IA..."):
                payload = {
                    "book_id": book_id,
                    "current_chapter_title": chapter_title,
                    "current_chapter_text": chapter_text,
                    "k": k
                }
                try:
                    r = requests.post(f"{API_BASE}/suggest", json=payload, timeout=600)
                    if r.ok:
                        data = r.json()
                        st.success("✅ Sugestões geradas com sucesso!")
                        st.info(f"📁 Arquivo salvo: {data.get('suggestions_file', 'N/A')}")
                        
                        st.subheader("🎭 Sugestões do co-roteirista")
                        st.write(data["suggestions"])
                    else:
                        st.error(f"❌ Erro ao gerar sugestões: {r.text}")
                except Exception as e:
                    st.error(f"❌ Erro de conexão: {str(e)}")
        else:
            st.error("❌ Preencha o título e o texto do capítulo")

with col3:
    if st.button("🧭 Analisar Coerência", type="secondary", disabled=not st.session_state.get("ready"), use_container_width=True):
        if chapter_title and chapter_text:
            with st.spinner("Analisando com IA..."):
                payload = {
                    "book_id": book_id,
                    "current_chapter_title": chapter_title,
                    "current_chapter_text": chapter_text,
                    "k": k
                }
                try:
                    r = requests.post(f"{API_BASE}/critique", json=payload, timeout=600)
                    if r.ok:
                        data = r.json()
                        st.success("✅ Crítica gerada com sucesso!")
                        st.info(f"📁 Arquivo salvo: {data.get('critique_file', 'N/A')}")
                        
                        st.subheader("📝 Feedback editorial")
                        st.write(data["critique"])
                    else:
                        st.error(f"❌ Erro ao gerar crítica: {r.text}")
                except Exception as e:
                    st.error(f"❌ Erro de conexão: {str(e)}")
        else:
            st.error("❌ Preencha o título e o texto do capítulo")
    
    # Preview formatada
    with st.expander("👁️ Prévia formatada (somente leitura)", expanded=False):
        st.markdown(f"#### {chapter_title or 'Sem título'}")
        st.write(chapter_text or "_vazio_")
    
    st.markdown('</div>', unsafe_allow_html=True)

# ========================
# Aba Copiloto
# ========================
with tab_copilot:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🤖 Perguntar ao Copiloto")
    
    # Conteúdo da tab_ask
    ask_q = st.text_area("O que você quer perguntar ao copiloto?", height=160, placeholder="Ex.: O arco da Ana está crível até aqui?", key="ask_question_tab1")
    colA, colB, colC = st.columns(3)
    with colA:
        ask_use_mem = st.checkbox("Usar memória (Top-K)", value=True, key="ask_use_mem_tab1")
    with colB:
        ask_k = st.slider("Top-K", 3, 15, 8, key="ask_k_tab1")
    with colC:
        ask_incl_cur = st.checkbox("Incluir capítulo atual", value=bool(chapter_text.strip()), key="ask_incl_cur_tab1")
    ask_show = st.checkbox("Mostrar prompt final (debug)", value=False, key="ask_show_tab1")
    if st.button("🤖 Perguntar", use_container_width=True, type="primary", key="ask_button_tab1"):
        if not ask_q.strip():
            st.error("Escreva a pergunta.")
        else:
            payload = {
                "book_id": book_id,
                "question": ask_q,
                "k": ask_k,
                "use_memory": ask_use_mem,
                "include_current": ask_incl_cur,
                "current_title": chapter_title if ask_incl_cur else None,
                "current_text": chapter_text if ask_incl_cur else None,
                "show_prompt": ask_show
            }
            try:
                r = requests.post(f"{API_BASE}/ask", json=payload, timeout=600)
                if r.ok:
                    data = r.json()
                    st.success("✅ Resposta do copiloto")
                    st.write(data["answer"])
                    if data.get("prompt_preview"):
                        with st.expander("📦 Prompt enviado (debug)", expanded=False):
                            st.code(data["prompt_preview"])
                else:
                    st.error(f"Erro: {r.text}")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("💡 Gerar Ideias")
    
    # Conteúdo da aba Gerar Ideias
    theme = st.text_input("Tema / logline", placeholder="Ex.: Detetive precisa provar inocência em uma cidade que o odeia")
    n_ideas = st.slider("Quantas ideias?", 3, 10, 5)
    style = st.text_input("Preferências (opcional)", placeholder="Tom noir, 1ª pessoa, twist no final…")
    colD, colE = st.columns(2)
    with colD:
        ide_use_mem = st.checkbox("Usar memória (Top-K)", value=False, key="ide_mem")
    with colE:
        ide_k = st.slider("Top-K", 3, 15, 6, key="ide_k")
    ide_show = st.checkbox("Mostrar prompt final (debug)", value=False, key="show_prompt_ideate")

    if st.button("🧪 Gerar ideias", use_container_width=True, key="gen_ideas"):
        if not theme.strip():
            st.error("Escreva um tema/logline.")
        else:
            payload = {
                "book_id": book_id,
                "theme": theme,
                "n": n_ideas,
                "use_memory": ide_use_mem,
                "k": ide_k,
                "style": style or None,
                "show_prompt": ide_show
            }
            try:
                r = requests.post(f"{API_BASE}/ideate", json=payload, timeout=600)
                if r.ok:
                    data = r.json()
                    ideas = data.get("ideas", [])
                    if not ideas:
                        st.info("O modelo não retornou ideias estruturadas. Tente novamente.")
                    else:
                        st.success(f"✅ {len(ideas)} ideias geradas")
                        # Escolha
                        choices = []
                        for i, it in enumerate(ideas):
                            title = it.get("title") or f"Ideia {i+1}"
                            logline = it.get("logline") or ""
                            with st.expander(f"💡 {title}", expanded=False):
                                st.write(f"**Logline:** {logline}")
                                for key in ["conflict","twist","stakes","pov","tone"]:
                                    if it.get(key):
                                        st.write(f"**{key.capitalize()}:** {it[key]}")
                            choices.append(f"{title} — {logline}")
                        if choices:
                            idx = st.radio("Escolha uma ideia para expandir:", list(range(len(choices))),
                                           format_func=lambda i: choices[i], key="ideate_choice")
                            if st.button("➡️ Usar na aba 'Escrever'", type="secondary", key="use_idea"):
                                sel = ideas[idx]
                                st.session_state["selected_idea_text"] = json.dumps(sel, ensure_ascii=False)
                                st.toast("Ideia enviada para a aba Escrever!")
                                st.success("Ideia selecionada! Vá para a aba 'Escrever a partir da Ideia'.")
                        if data.get("prompt_preview"):
                            with st.expander("📦 Prompt enviado (debug)", expanded=False):
                                st.code(data["prompt_preview"])
                else:
                    st.error(f"Erro: {r.text}")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🧠 Escrever a partir da Ideia / Capítulo")

    # Conteúdo da aba Escrever
    colA, colB = st.columns(2)
    with colA:
        mode = st.radio("Gerar a partir de:", ["Ideia", "Capítulo existente"], horizontal=True, key="expand_mode_unique")
    with colB:
        ctx = st.radio("Contexto:", ["Sem memória", "Memória do livro", "Somente capítulo atual", "Livro + capítulo atual"], index=1, key="expand_ctx_unique")
    
    use_memory_map = {
        "Sem memória": "none",
        "Memória do livro": "book",
        "Somente capítulo atual": "none",            # só injeta o atual
        "Livro + capítulo atual": "book+current",
    }
    include_current = (ctx in ["Somente capítulo atual", "Livro + capítulo atual"])
    
    # Seleção de base
    idea_text = None
    chapter_pick = None
    
    if mode == "Ideia":
        idea_prefill = st.session_state.get("selected_idea_text", "")
        idea_text = st.text_area("Descreva a ideia base", value=idea_prefill, height=160, placeholder="Ex.: Um escritor decide se isolar na serra para romper o bloqueio...")
    else:
        # buscar capítulos do livro atual
        try:
            resp = requests.get(f"{API_BASE}/chapters/{book_id}", timeout=10)
            chs = resp.json().get("chapters", []) if resp.ok else []
        except Exception:
            chs = []
        if not chs:
            st.warning("Nenhum capítulo encontrado para este livro.")
        else:
            chapter_pick = st.selectbox("Escolha o capítulo para expandir", chs, format_func=lambda c: f"{c['title']} ({c['id'][:8]})")
    
    length = st.select_slider("Tamanho desejado", options=["300-500 palavras","500-800 palavras","800-1200 palavras"], value="500-800 palavras")
    save_flag = st.checkbox("Salvar como novo capítulo")
    save_title = st.text_input("Título (se salvar)", value="Cena gerada", disabled=not save_flag)
    
    if st.button("✍️ Gerar Cena", use_container_width=True, type="primary"):
        if mode == "Ideia" and not (idea_text or "").strip():
            st.error("Descreva a ideia base.")
        elif mode == "Capítulo existente" and not chapter_pick:
            st.error("Selecione um capítulo para expandir.")
        else:
            payload = {
                "book_id": book_id,
                "source": "idea" if mode == "Ideia" else "chapter",
                "idea": idea_text if mode == "Ideia" else None,
                "chapter_id": (chapter_pick["id"] if (mode == "Capítulo existente" and chapter_pick) else None),
                "use_memory": use_memory_map[ctx],          # 'none' | 'book' | 'book+current'
                "include_current": include_current,         # True para "Somente atual" e "Livro + atual"
                "current_title": st.session_state.get("shared_chapter_title"),
                "current_text": st.session_state.get("shared_chapter_text"),
                "length": length,
                "save_as_chapter": save_flag,
                "title": (save_title if save_flag else None),
                "show_prompt": False
            }
            try:
                r = requests.post(f"{API_BASE}/expand", json=payload, timeout=600)
                if r.ok:
                    data = r.json()
                    st.success("✅ Cena gerada!")
                    if data.get("saved"):
                        st.info(f"💾 Salvo como capítulo **{data['saved']['title']}** (id: {data['saved']['chapter_id']})")

                    st.markdown("### 📄 Resultado")
                    st.text_area("Cena", value=data["scene"], height=400, disabled=True)

                    # Atalho: enviar para o editor
                    if st.button("⬇️ Usar como rascunho no editor", key="use_as_draft"):
                        st.session_state["editing_chapter"] = {
                            "id": "rascunho",
                            "title": save_title or "Cena gerada",
                            "content": data["scene"],
                            "file_path": "",
                            "size": len(data["scene"]),
                            "modified": time.time(),
                        }
                        st.session_state["editing_mode"] = "continue"
                        st.success("Rascunho carregado no editor!")
                else:
                    st.error(f"Erro: {r.text}")
            except Exception as e:
                st.error(f"Falha na requisição: {e}")

# Botão para limpar edição
if editing_chapter:
    if st.button("❌ Cancelar Edição", type="secondary"):
        if "editing_chapter" in st.session_state:
            del st.session_state["editing_chapter"]
        if "editing_mode" in st.session_state:
            del st.session_state["editing_mode"]
        st.rerun()

# ========================
# 🧠 Memória & 🛠️ Manutenção (em abas separadas)
# ========================
st.divider()
st.header("📦 Memória & Manutenção")

tab_mem, tab_maint = st.tabs(["Memória (ChromaDB)", "Manutenção"])

with tab_mem:
    st.subheader("💾 ChromaDB Explorer")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔍 Ver Status do ChromaDB", key="mem_status_btn"):
            try:
                status_response = requests.get(f"{API_BASE}/chroma/status", timeout=10)
                if status_response.ok:
                    status_data = status_response.json()
                    if status_data.get("success"):
                        st.success(f"✅ ChromaDB: {status_data['status']}")
                        st.info(f"📊 Coleções: {status_data['total_collections']}")
                        st.info(f"🌐 Host: {status_data['host']}:{status_data['port']}")
                    else:
                        st.error(status_data.get("message", "Erro"))
                else:
                    st.error(f"HTTP {status_response.status_code}")
            except Exception as e:
                st.error(f"Falha: {e}")

    with col2:
        if st.button("📂 Listar coleções", key="mem_list_collections"):
            try:
                r = requests.get(f"{API_BASE}/chroma/collections", timeout=10)
                if r.ok:
                    data = r.json()
                    cols = data.get("collections", [])
                    if not cols:
                        st.info("Nenhuma coleção encontrada.")
                    else:
                        for c in cols:
                            with st.expander(f"{c['name']} ({c['count']} docs)", expanded=False):
                                st.json(c)
                else:
                    st.error(f"Erro: HTTP {r.status_code}")
            except Exception as e:
                st.error(f"Falha: {e}")

    with col3:
        if st.button("📄 Ver docs do livro atual", key="mem_list_docs_book"):
            try:
                r = requests.get(f"{API_BASE}/chroma/collection/book_memory", timeout=30)
                if r.ok:
                    data = r.json()
                    docs = [d for d in data.get("documents", []) if d.get("metadata", {}).get("book_id") == book_id]
                    if not docs:
                        st.info("Nenhum documento deste livro na coleção.")
                    else:
                        for d in docs[:20]:
                            with st.expander(d["id"], expanded=False):
                                st.write("**Metadata:**", d.get("metadata", {}))
                                st.text(d.get("document_preview", "") or "")
                        if len(docs) > 20:
                            st.info(f"... e mais {len(docs) - 20} documentos.")
                else:
                    st.error(f"Erro ({r.status_code}): {r.text}")
            except Exception as e:
                st.error(f"Falha de conexão: {e}")

    st.markdown("---")
    st.subheader("🧹 Limpeza / Reindexação")

    c1, c2, c3 = st.columns(3)
    with c1:
        clear_this = st.checkbox("Confirmo apagar **apenas** a memória deste livro", key="confirm_clear_book")
        if st.button("🗑️ Limpar memória do livro atual", type="secondary", key="btn_clear_book") and clear_this:
            try:
                r = requests.delete(f"{API_BASE}/chroma/book/{book_id}", timeout=30)
                if r.ok:
                    st.success(f"Memória do livro '{book_id}' apagada.")
                else:
                    st.error(f"Erro ({r.status_code}): {r.text}")
            except Exception as e:
                st.error(f"Falha de conexão: {e}")

    with c2:
        clear_all = st.checkbox("Confirmo que desejo apagar **TUDO**", key="confirm_clear_all")
        if st.button("🧽 Limpar TODAS as coleções", type="secondary", key="btn_clear_all") and clear_all:
            try:
                r = requests.delete(f"{API_BASE}/chroma/clear", timeout=60)
                if r.ok:
                    st.success("ChromaDB limpo com sucesso.")
                else:
                    st.error(f"Erro ({r.status_code}): {r.text}")
            except Exception as e:
                st.error(f"Falha de conexão: {e}")

    with c3:
        if st.button("🔁 Reindexar capítulos do disco", type="secondary", key="btn_reindex"):
            try:
                r = requests.post(f"{API_BASE}/chroma/vectorize-existing", timeout=600)
                if r.ok:
                    data = r.json()
                    st.success(f"Vetorização: {data.get('vectorized_count',0)}/{data.get('total_files',0)}")
                    if data.get("errors"):
                        with st.expander("Erros", expanded=False):
                            for err in data["errors"]:
                                st.write("• ", err)
                else:
                    st.error(f"Erro ({r.status_code}): {r.text}")
            except Exception as e:
                st.error(f"Falha de conexão: {e}")

with tab_maint:
    st.subheader("🔧 Status dos Serviços")
    if st.session_state.get("ready"):
        st.success("✅ Sistema Pronto")
        st.info("🎯 vLLM: Qwen2.5-14B-Instruct")
        st.info("💾 ChromaDB: Conectado")
        st.info("🚀 API: Funcionando")
    else:
        st.warning("⏳ Inicializando...")
        st.info("🔄 vLLM: Carregando modelo")
        st.info("🔄 ChromaDB: Conectando")

    st.markdown("---")
    colX, colY = st.columns(2)
    with colX:
        if st.button("🔄 Atualizar Status", type="secondary", key="maint_refresh_status"):
            st.rerun()
    with colY:
        if st.button("📊 Atualizar Lista de Livros", type="secondary", key="maint_refresh_books"):
            st.rerun()

# (opcional) rodapé
st.divider()
st.caption("💡 Dica: arquivos em /data/chapters/ → capítulos: livro__id.md | sugestões: sugest_titulo__id.md | críticas: critica_titulo__id.md")