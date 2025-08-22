# Book Assistant - Guia de Uso

## 📱 1. Streamlit UI — "O App que Você Usa"

**URL:** http://localhost:8501

**Para quê:** É a interface gráfica onde você escreve/cola o capítulo, salva, e solicita funcionalidades.

### Funcionalidades Principais:
- **💾 Salvar capítulo** → Gera e armazena o resumo estruturado + indexa no Chroma
- **💡 Sugerir próximos passos** → Ideias de enredo coerentes com a memória
- **🧭 Crítica de coerência** → Checklist de continuidade/contradições

**Quando acessar:** No dia a dia da escrita. É o que você abre no navegador e trabalha normalmente.

---

## 🧠 2. API (FastAPI) — "O Cérebro de Orquestração/Memória"

**URL:** http://localhost:8010/health (só para conferir que está ok)

**Para quê:** Endpoints REST que a UI usa por trás dos panos. Você pode chamá-los direto se quiser automatizar coisas, scripts, integração com outros apps.

### Endpoints Principais:

- **POST** `/chapter/save` — Salva capítulo + cria resumo + indexa na memória
- **POST** `/suggest` — Gera sugestões para o próximo passo com base na memória
- **POST** `/critique` — Faz revisão de coerência

### Quando Acessar:

- **Para testar/depurar:** Ver se a API está de pé (`/health`)
- **Para integrações:** Chamar endpoints a partir de outro sistema

### Exemplo Rápido (PowerShell/CMD):

```bash
curl -X POST http://localhost:8010/suggest ^
  -H "Content-Type: application/json" ^
  -d "{\"book_id\":\"meu-livro\",\"current_chapter_title\":\"Cap 7\",\"current_chapter_text\":\"texto...\",\"k\":8}"
```

---

## 🤖 3. vLLM (OpenAI API) — "O Servidor do Modelo"

**URL base:** http://localhost:8000/v1

**Para quê:** Expõe o modelo (Qwen 32B) em API compatível com OpenAI. A API e a UI falam com ele. Você também pode usar este endpoint direto com qualquer cliente OpenAI (SDK) local.

### Quando Acessar:

- **Para testar o modelo cru** (sem RAG/memória) — útil para diagnóstico de qualidade
- **Para usar o modelo em outros projetos** que falem OpenAI

### Testes Úteis:

#### Listar Modelos:
```bash
curl http://localhost:8000/v1/models
```

#### Chat Simples:
```bash
curl http://localhost:8000/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer sk-local-anything" ^
  -d "{\"model\":\"book-llm\",\"messages\":[{\"role\":\"user\",\"content\":\"Escreva um parágrafo criativo em PT-BR.\"}]}"
```

> **Nota:** `book-llm` é o nome servido (definido no `--served-model-name`).

---

## 🔄 Fluxo Prático (Resumo)

1. **Suba os serviços** com `docker compose up -d --build`
2. **Abra a UI** (:8501) e trabalhe nos capítulos
3. **Se algo parecer estranho:**
   - Cheque a API em `:8010/health`
   - Teste o vLLM em `:8000/v1/models` e um chat simples (acima)
   - Este comando roda o modelo setado > --model Qwen/Qwen2.5-32B-Instruct

---

### Subir modo rápido (14B):
```bash 
docker compose -f docker-compose.yml -f docker-compose.14b.yml up -d --build vllm
```

### Subir alta qualidade (32B):

```bash 
docker compose -f docker-compose.yml -f docker-compose.32b.yml up -d --build vllm
```

### Subir Interface gráfica:

```bash 
docker compose -f docker-compose.yml -f docker-compose.14b.yml up -d --build chroma api ui

```

## 💡 Dicas e Solução de Problemas

### Primeira Execução
- O modelo baixa os pesos no serviço vllm na primeira execução

### Logs (em outra janela/terminal):
```bash
docker compose logs -f vllm
docker compose logs -f api
docker compose logs -f ui
```

### Recarregar Depois de Alterar `docker-compose.yml`:
```bash
docker compose up -d --build
```

### Checar Uso das Duas GPUs:
```bash
docker exec -it vllm nvidia-smi
```

> **Resultado esperado:** Você deve ver a 3090 e a 4090 com memória alocada quando gerar texto.

### Mudou o Modelo/Janela de Contexto?
Edite o `docker-compose.yml` (bloco vllm, flags `--model`, `--max-model-len`, `--tensor-parallel-size`) e recrie o serviço:

```bash 
docker compose up -d --build vllm
```

### Checar download/carregamento do modelo:
````bash
docker compose logs -f vllm
````

### Testar chat rápido:

````bash
curl http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer sk-local-anything" `
  -d "{\"model\":\"book-llm\",\"messages\":[{\"role\":\"user\",\"content\":\"Escreva um parágrafo criativo em PT-BR.\"}]}"

````

