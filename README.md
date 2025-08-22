
# Copiloto de Escrita com Memória (vLLM + Chroma + FastAPI + Streamlit)

Um ambiente completo para escrever livros com auxílio de IA, memória de capítulos (RAG) e ferramentas de planejamento criativo.  
Arquitetura: **vLLM (modelo local) + FastAPI (backend) + ChromaDB (vetores) + Streamlit (UI)** — tudo orquestrado com **Docker Compose**.

> **Portas padrão deste projeto**  
> - **UI (Streamlit):** `http://localhost:8501`  
> - **API (FastAPI):** `http://localhost:8010`  
> - **vLLM (OpenAI API compatível):** `http://localhost:8015`  ← *usamos 8015 porque 8000 já estava ocupada*  
> - **ChromaDB (HTTP):** `http://localhost:8001`

---

## 🧭 Sumário
- [Visão Geral](#-visão-geral)
- [Arquitetura e Serviços](#-arquitetura-e-serviços)
- [Pré-requisitos no Windows (WSL + GPU + Docker)](#-pré-requisitos-no-windows-wsl--gpu--docker)
  - [1) Ativar WSL2 e instalar Ubuntu](#1-ativar-wsl2-e-instalar-ubuntu)
  - [2) Instalar drivers NVIDIA (Windows e WSL)](#2-instalar-drivers-nvidia-windows-e-wsl)
  - [3) Instalar Docker Desktop e habilitar WSL2 + GPU](#3-instalar-docker-desktop-e-habilitar-wsl2--gpu)
  - [4) Testar GPU no Docker/WSL](#4-testar-gpu-no-dockerwsl)
- [Instalação e Primeira Execução](#-instalação-e-primeira-execução)
- [Configuração (.env)](#-configuração-env)
- [Como usar (UI)](#-como-usar-ui)
- [Referência rápida da API](#-referência-rápida-da-api)
- [Trocar de modelo (vLLM)](#-trocar-de-modelo-vllm)
- [Dicas de memória (ChromaDB)](#-dicas-de-memória-chromadb)
- [Solução de Problemas](#-solução-de-problemas)
- [FAQ: Tokens, custos e auto-hospedagem](#-faq-tokens-custos-e-auto-hospedagem)
- [Licença](#-licença)

---

## 🚀 Visão Geral

O **Copiloto de Escrita** ajuda você a:
- Escrever capítulos com um **LLM local compatível com OpenAI** (via vLLM).
- Salvar capítulos em disco (`/data/chapters`) e **extrair metadados** (gênero, tom, personagens etc).
- **Memória** dos capítulos com **ChromaDB** para consultas de continuidade (RAG).
- Um **UI moderno** (Streamlit) com:
  - Gerenciamento de livros e capítulos (criar, carregar, sobrescrever).
  - **Perguntas para o copiloto** usando memória opcional.
  - **Gerar ideias** e **expandir** em cenas novas (e opcionalmente salvar como capítulo).
  - **Chroma Explorer** (status, coleções, documentos) e ações de manutenção.

---

## 🧩 Arquitetura e Serviços

Todos os serviços sobem via Docker Compose:

- **vLLM** (`vllm`) — exposto em `localhost:8015` (OpenAI API).  
  Por padrão servimos `Qwen/Qwen2.5-14B-Instruct` com `--served-model-name book-llm`.
- **ChromaDB** (`chroma`) — exposto em `localhost:8001` (HTTP v2). Persistência em `./data/chroma`.
- **API** (`book-api`) — FastAPI em `localhost:8010`. Fala com `vllm:8000` e `chroma:8000` internamente.
- **UI** (`book-ui`) — Streamlit em `localhost:8501`. Fala com `book-api`.

Persistência local:
```
./data/
  chapters/        # arquivos .md de capítulos, sugestões e críticas
  chroma/          # dados do banco vetorial
```

---

## 🪟 Pré-requisitos no Windows (WSL + GPU + Docker)

### 1) Ativar WSL2 e instalar Ubuntu
No **PowerShell (Admin)**:
```powershell
wsl --install -d Ubuntu
wsl --set-default-version 2
wsl --status
```
Reinicie se solicitado e **abra o Ubuntu** para concluir a configuração de usuário.

### 2) Instalar drivers NVIDIA (Windows e WSL)
- **Windows:** instale o **NVIDIA Game Ready/Studio Driver** mais recente.  
- **WSL CUDA:** instale o pacote de suporte NVIDIA para WSL (o Docker Desktop usará o runtime de GPU).  
Verifique no Ubuntu (WSL):
```bash
nvidia-smi
```

### 3) Instalar Docker Desktop e habilitar WSL2 + GPU
- Instale o **Docker Desktop para Windows**.
- Settings → **General**: “Use the WSL 2 based engine” ✅  
- Settings → **Resources → WSL Integration**: habilite sua distro Ubuntu ✅  
- Settings → **Resources → GPU**: habilite “Use WSL GPU” / NVIDIA runtime (se disponível).

### 4) Testar GPU no Docker/WSL
No Ubuntu/WSL:
```bash
docker run --rm --gpus all nvidia/cuda:12.2.2-base-ubuntu22.04 nvidia-smi
```

Se aparecer a tabela de GPUs, está tudo OK.

---

## 📦 Instalação e Primeira Execução

1) **Clone o projeto** (ou copie os arquivos) no Windows (em uma pasta sem acentos/espaços).  
2) Crie a estrutura de dados:
```bash
mkdir -p data/chapters data/chroma
```
3) Crie o arquivo **`.env`** (veja o exemplo abaixo).  
4) **Suba os serviços**:
```bash
docker compose up -d --build
```
> A primeira execução pode demorar pois o vLLM fará download do modelo (vários GB).

5) **Verifique**:
- UI: `http://localhost:8501`
- API health: `curl http://localhost:8010/health`
- API ready: `curl http://localhost:8010/ready`
- vLLM models: `curl http://localhost:8015/v1/models`
- Chroma heartbeat: `curl http://localhost:8001/api/v2/heartbeat`

---

## 🔧 Configuração (.env)

Crie um arquivo `.env` na raiz:

```dotenv
# Chave fake/local (vLLM aceita qualquer string)
OPENAI_API_KEY=sk-local-anything

# O nome SERVIDO pelo vLLM (veja --served-model-name no compose)
OPENAI_MODEL=book-llm

# Internos da API
CHROMA_HOST=chroma
CHROMA_PORT=8000
DATA_DIR=/data
```

> A UI e a API estão configuradas para falar com `vllm:8000` internamente. Externamente, expomos **8015** para testes.

---

## 🖥️ Como usar (UI)

Acesse `http://localhost:8501`.

1. **Gerenciamento de Livros (sidebar)**
   - Crie um livro (gera um `books/<id>.json`).
   - Selecione um livro existente (detectado por metadados ou pelos arquivos em `/data/chapters`).

2. **Editor de Capítulo**
   - Edite **Título** e **Texto**.
   - **Salvar Capítulo**:
     - Se **“Sobrescrever capítulo carregado”** estiver **ligado** e um capítulo estiver carregado, a UI fará **PUT** para `/chapter/update` (mesmo arquivo).  
     - Se estiver **desligado**, fará **POST** para `/chapter/save` (novo arquivo).
   - **Gerar Sugestões**: chama `/suggest` e salva `sugest_<titulo>__<id>.md`.
   - **Analisar Coerência**: chama `/critique` e salva `critica_<titulo>__<id>.md`.

3. **Copiloto Livre & Ideias**
   - **Perguntar ao Copiloto**: `/ask` com ou sem memória (Top-K).
   - **Gerar Ideias**: `/ideate` retorna lista JSON de ideias (title, logline etc.).
   - **Escrever a partir da Ideia ou Capítulo**: `/expand` cria uma cena coerente; opcionalmente **salva como capítulo**.

4. **ChromaDB Explorer**
   - Ver **status**, **coleções** e **documentos** via API.
   - Ações de manutenção: **limpar coleções** e **reindexar capítulos do disco**.

> Todos os capítulos são salvos em `/data/chapters` como `bookId__chapterId.md` (e sugestões/críticas com prefixos `sugest_`/`critica_`).

---

## 📚 Referência rápida da API

- `GET /health` — health básico.  
- `GET /ready` — verifica vLLM e Chroma.  
- `POST /test-llm` — ping no modelo.

### Capítulos
- `POST /chapter/save` — cria novo capítulo.  
  Body: `{"book_id","title","text"}`  
- `PUT /chapter/update` — **sobrescreve** capítulo existente.  
  Body: `{"book_id","chapter_id","title?","text?"}`

### Metadados
- `GET /metadata/book/{book_id}` — lista documentos do `book_id` na coleção `book_memory`.  
- `POST /metadata/extract` — extrai metadados do texto enviado.

### Roteirista/Editor
- `POST /suggest` — 3–5 caminhos narrativos + cena amostra.  
- `POST /critique` — crítica de coerência/continuidade.

### Copiloto Livre & Ideias
- `POST /ask` — pergunta livre com memória opcional.  
- `POST /ideate` — ideias em JSON.  
- `POST /expand` — cena a partir de ideia/capítulo (+ salvar).

### ChromaDB (admin)
- `GET /chroma/status` — status do Chroma.  
- `GET /chroma/collections` — listas coleções.  
- `GET /chroma/collection/{name}` — documentos de uma coleção.  
- `DELETE /chroma/clear` — **apaga tudo**.  
- `POST /chroma/vectorize-existing` — indexa `/data/chapters` atuais.

> **Opcional**: se você adicionou `DELETE /chroma/book/{book_id}`, a UI consegue limpar apenas a memória do livro selecionado.

---

## 🔁 Trocar de modelo (vLLM)

O vLLM aceita qualquer modelo do Hugging Face Hub compatível com geração. Dois presets úteis para GPU total ~48GB:

### A) Qwen 2.5 14B Instruct (bom equilíbrio qualidade/VRAM)
```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    command: >
      --model Qwen/Qwen2.5-14B-Instruct
      --dtype auto
      --max-model-len 16384
      --gpu-memory-utilization 0.92
      --tensor-parallel-size 2
      --served-model-name book-llm
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
              driver: nvidia
              count: 2
    ports:
      - "8015:8000"
    volumes:
      - huggingface_cache:/root/.cache/huggingface
```

### B) Phi-3.5 Mini Instruct (leve/rápido, ótimo para testes)
```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    command: >
      --model microsoft/Phi-3.5-mini-instruct
      --dtype auto
      --max-model-len 65536
      --gpu-memory-utilization 0.85
      --tensor-parallel-size 1
      --served-model-name book-llm
    ports:
      - "8015:8000"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
              driver: nvidia
              count: 1
    volumes:
      - huggingface_cache:/root/.cache/huggingface
```

> Ajuste `--max-model-len` / `--tensor-parallel-size` se faltar VRAM. O nome **`book-llm`** deve bater com `OPENAI_MODEL` na API.

---

## 🧠 Dicas de memória (ChromaDB)

- A coleção padrão é **`book_memory`**.  
- Cada capítulo gera **dois documentos**:  
  - `book_id:chapter_id:summary` (texto de resumo estruturado)  
  - `book_id:chapter_id:full` (texto completo)  
- Use a UI para:
  - **Vectorizar capítulos antigos** (`/chroma/vectorize-existing`).
  - **Inspecionar documentos** da coleção.  
  - **Limpar** (`/chroma/clear`) em caso de bagunça.

---

## 🛠️ Solução de Problemas

### vLLM demora/repete logs de “carregando shards”
Normal — aguardando download/carregamento. A UI mostra um **spinner de readiness** e verifica `vLLM`/`Chroma`/`API` periodicamente.

### `curl http://localhost:8015/v1/models` falha
- Verifique **Docker Desktop** e se a porta **8015** não está ocupada.
- `docker logs vllm --tail=200` para ver o progresso do modelo.
- Ajuste modelo no compose (veja seção de modelos).

### `pip Read timed out` durante build da imagem `api`
- O `Dockerfile` já usa `--timeout 300 --retries 3`.  
- Se insistir, tente mudar de rede, usar um mirror de PyPI ou `docker build` novamente.

### Chroma: `405 Method Not Allowed` em `/tenants`
- Use **endpoints v2** (`/api/v2/heartbeat`) e o cliente HTTP com `tenant/database` se necessário.  
- No projeto usamos rotas v2 e o `HttpClient` do `chromadb`.

### “Container unhealthy” / “dependency failed to start”
- Veja logs: `docker compose logs --tail=200` e corrija o serviço que está falhando (geralmente `vllm` ou `api`).

### GPU OOM (falta VRAM)
- Reduza `--max-model-len` ou troque para um modelo menor (Phi-3.5 mini).  
- Diminua `--gpu-memory-utilization` ou `--tensor-parallel-size`.

### Portas em uso
- Se `8000` estiver ocupada, continuamos com **8015:8000**. Altere se precisar e **atualize o README/UI** conforme.

---

## ❓ FAQ: Tokens, custos e auto-hospedagem

- **Por que “pagar por token”?** Porque o custo operacional de um LLM cresce com o **tamanho do contexto + geração**. Cobrar por token é proporcional ao uso real.  
- **Rodando localmente com vLLM** você **não paga tokens** — seu custo é **hardware + energia**.  
- Modelos como **`microsoft/Phi-3.5-mini-instruct`** são **gratuitos para rodar localmente** (licenças permissivas), porém **se usar API de terceiros**, haverá cobrança por token.  
- Para **SaaS**, você pode oferecer **bring-your-own-key (BYOK)** ou rodar **modelos próprios** (custos de GPU).

---

## 📄 Licença

Defina a licença do seu projeto aqui (MIT, Apache-2.0, etc.).

---

**Pronto!** Suba com:
```bash
docker compose up -d --build
```

A UI em `http://localhost:8501` vai exibir o status de readiness e liberar a edição quando tudo estiver no ar.
