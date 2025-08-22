# 📚 Book Assistant - Copiloto de Escrita com IA

Um assistente inteligente para escritores que combina **vLLM**, **ChromaDB** e **Streamlit** para criar, editar e gerenciar livros com memória contextual e geração de ideias.

## ✨ Funcionalidades Principais

### 🖊️ Editor de Capítulos
- **Editor rico** com suporte a Markdown
- **Sobrescrita inteligente** de capítulos existentes
- **Controle de versão** automático
- **Extração de metadados** automática (personagens, locais, temas)

### 🤖 Copiloto IA
- **Perguntas livres** ao copiloto com contexto do livro
- **Geração de ideias** baseada em temas e memória
- **Expansão de cenas** a partir de ideias ou capítulos existentes
- **RAG (Retrieval Augmented Generation)** para continuidade narrativa

### 🧠 Sistema de Memória
- **ChromaDB** para armazenamento vetorial
- **Busca semântica** nos capítulos anteriores
- **Contexto inteligente** para geração de conteúdo
- **Explorador de memória** para análise de dados

### 🛠️ Ferramentas de Manutenção
- **Limpeza seletiva** de memória por livro
- **Reindexação** de capítulos existentes
- **Backup e restauração** de dados
- **Monitoramento** de status dos serviços

## 🚀 Tecnologias

- **Backend**: FastAPI + Python 3.11
- **Frontend**: Streamlit com tema dark moderno
- **LLM**: vLLM com modelo Qwen2.5-14B-Instruct
- **Banco de Dados**: ChromaDB para vetores
- **Containerização**: Docker + Docker Compose
- **GPU**: Suporte a CUDA para aceleração

## 📋 Pré-requisitos

- **Docker** e **Docker Compose**
- **GPU NVIDIA** com drivers CUDA (recomendado)
- **16GB+ RAM** para o modelo 14B
- **Portas disponíveis**: 8501 (UI), 8010 (API), 8015 (vLLM), 8001 (ChromaDB)

## 🛠️ Instalação

### 1. Clone o repositório
```bash
git clone <seu-repositorio>
cd book-assistant
```

### 2. Configure as variáveis de ambiente
```bash
cp .env.example .env
# Edite .env com suas configurações
```

### 3. Execute com Docker Compose
```bash
# Para GPU (recomendado)
docker-compose -f docker-compose.yml -f docker-compose.14b.yml up -d

# Para CPU (mais lento)
docker-compose up -d
```

### 4. Acesse a interface
```
http://localhost:8501
```

## 📁 Estrutura do Projeto

```
book-assistant/
├── api/                 # Backend FastAPI
│   ├── main.py         # API principal
│   ├── requirements.txt # Dependências Python
│   └── Dockerfile      # Container da API
├── ui/                  # Frontend Streamlit
│   ├── app.py          # Interface principal
│   ├── requirements.txt # Dependências Python
│   ├── .streamlit/     # Configurações Streamlit
│   └── Dockerfile      # Container da UI
├── data/                # Dados persistentes
│   ├── chapters/        # Capítulos em Markdown
│   ├── books/           # Metadados dos livros
│   └── chroma/          # Banco vetorial
├── docker-compose.yml   # Configuração principal
├── docker-compose.14b.yml # Configuração para modelo 14B
└── README.md            # Este arquivo
```

## 🔧 Configuração

### Variáveis de Ambiente (.env)
```bash
# API Keys
OPENAI_API_KEY=sk-local
OPENAI_MODEL=book-llm

# Configurações do modelo
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
VLLM_MAX_MODEL_LEN=32768

# Configurações do ChromaDB
CHROMA_HOST=chroma
CHROMA_PORT=8000
```

### Personalização do Tema
Edite `.streamlit/config.toml` para personalizar cores e fontes:
```toml
[theme]
base="dark"
primaryColor="#6EE7B7"
backgroundColor="#0B1020"
secondaryBackgroundColor="#131A2A"
textColor="#E6EDF3"
font="sans serif"
```

## 📖 Como Usar

### 1. Criar um Novo Livro
- Acesse a aba "Editor"
- Use o painel lateral para criar um novo livro
- Defina nome e ID único

### 2. Escrever Capítulos
- Digite o título e conteúdo no editor
- Use "Salvar Capítulo" para criar novo
- Use "Sobrescrever" para editar existente

### 3. Usar o Copiloto
- **Perguntar**: Faça perguntas sobre o livro
- **Gerar Ideias**: Solicite sugestões de cenas
- **Expandir**: Desenvolva ideias em cenas completas

### 4. Gerenciar Memória
- Visualize dados no ChromaDB Explorer
- Limpe memória específica por livro
- Reindexe capítulos quando necessário

## 🔍 Troubleshooting

### vLLM não carrega
```bash
# Verifique logs
docker-compose logs vllm

# Reduza max-model-len se necessário
# Verifique GPU e drivers CUDA
```

### Erro de memória
```bash
# Reduza gpu_memory_utilization
# Aumente shm_size no docker-compose
```

### ChromaDB não conecta
```bash
# Verifique logs
docker-compose logs chroma

# Verifique volumes e permissões
```

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 🙏 Agradecimentos

- **vLLM** pela infraestrutura de LLM
- **ChromaDB** pelo banco vetorial
- **Streamlit** pela interface web
- **Hugging Face** pelos modelos de linguagem

## 📞 Suporte

Para dúvidas ou problemas:
- Abra uma [Issue](../../issues)
- Consulte a [documentação](../../wiki)
- Entre em contato via [Discussions](../../discussions)

---

**Desenvolvido com ❤️ para escritores e criadores de conteúdo**
