#!/usr/bin/env python3
"""
Teste completo da API Book Assistant
Executa testes em todos os endpoints principais
"""

import requests
import json
import time
from typing import Dict, Any

class BookAssistantTester:
    def __init__(self, base_url: str = "http://localhost:8010"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        
    def log_test(self, endpoint: str, success: bool, response_time: float, details: str = ""):
        """Registra resultado de um teste"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "endpoint": endpoint,
            "success": success,
            "response_time": response_time,
            "details": details,
            "status": status
        }
        self.test_results.append(result)
        print(f"{status} {endpoint} ({response_time:.2f}s) {details}")
        
    def test_endpoint(self, method: str, endpoint: str, data: Dict[str, Any] = None, 
                     expected_status: int = 200, description: str = "") -> bool:
        """Testa um endpoint específico"""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=30)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=60)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, timeout=60)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, timeout=30)
            else:
                raise ValueError(f"Método HTTP inválido: {method}")
            
            response_time = time.time() - start_time
            success = response.status_code == expected_status
            
            details = f"HTTP {response.status_code}"
            if description:
                details += f" - {description}"
                
            self.log_test(f"{method} {endpoint}", success, response_time, details)
            
            if not success:
                print(f"   Resposta: {response.text[:200]}...")
                
            return success
            
        except Exception as e:
            response_time = time.time() - start_time
            self.log_test(f"{method} {endpoint}", False, response_time, f"Erro: {str(e)}")
            return False
    
    def run_health_tests(self):
        """Testa endpoints de saúde e status"""
        print("\n🔍 TESTANDO HEALTH & STATUS")
        print("=" * 50)
        
        self.test_endpoint("GET", "/health", description="Verificar se API está rodando")
        self.test_endpoint("GET", "/ready", description="Verificar readiness completo")
        self.test_endpoint("GET", "/chroma/status", description="Status do ChromaDB")
        self.test_endpoint("GET", "/chroma/collections", description="Listar coleções")
        
    def run_chapter_tests(self):
        """Testa endpoints de gestão de capítulos"""
        print("\n📚 TESTANDO GESTÃO DE CAPÍTULOS")
        print("=" * 50)
        
        # Teste de salvamento
        chapter_data = {
            "book_id": "test-book",
            "title": "Capítulo de Teste",
            "text": "Este é um capítulo de teste para verificar se a API está funcionando corretamente."
        }
        
        self.test_endpoint("POST", "/chapter/save", data=chapter_data, 
                          description="Salvar novo capítulo")
        
        # Aguarda um pouco para o processamento
        time.sleep(2)
        
        # Teste de listagem
        self.test_endpoint("GET", "/chapters/test-book", 
                          description="Listar capítulos do livro")
        
        # Teste de metadados
        self.test_endpoint("GET", "/metadata/book/test-book", 
                          description="Obter metadados do livro")
        
    def run_ai_tests(self):
        """Testa funcionalidades de IA"""
        print("\n🤖 TESTANDO FUNCIONALIDADES DE IA")
        print("=" * 50)
        
        # Teste de sugestões
        suggest_data = {
            "book_id": "test-book",
            "current_chapter_title": "Capítulo de Teste",
            "current_chapter_text": "Este é um capítulo de teste para verificar se a API está funcionando corretamente.",
            "k": 5
        }
        
        self.test_endpoint("POST", "/suggest", data=suggest_data, 
                          description="Gerar sugestões")
        
        # Teste de crítica
        critique_data = {
            "book_id": "test-book",
            "current_chapter_title": "Capítulo de Teste",
            "current_chapter_text": "Este é um capítulo de teste para verificar se a API está funcionando corretamente.",
            "k": 5
        }
        
        self.test_endpoint("POST", "/critique", data=critique_data, 
                          description="Analisar coerência")
        
        # Teste de pergunta livre
        ask_data = {
            "book_id": "test-book",
            "question": "Como posso melhorar este capítulo?",
            "k": 5,
            "use_memory": False,
            "include_current": False,
            "show_prompt": False
        }
        
        self.test_endpoint("POST", "/ask", data=ask_data, 
                          description="Fazer pergunta ao copiloto")
        
        # Teste de geração de ideias
        ideate_data = {
            "book_id": "test-book",
            "theme": "Um detetive precisa provar sua inocência",
            "n": 3,
            "use_memory": False,
            "k": 5,
            "style": "Suspense, final surpreendente",
            "show_prompt": False
        }
        
        self.test_endpoint("POST", "/ideate", data=ideate_data, 
                          description="Gerar ideias")
        
        # Teste de expansão
        expand_data = {
            "book_id": "test-book",
            "source": "idea",
            "idea": "Um escritor decide se isolar na serra para romper o bloqueio criativo",
            "use_memory": "none",
            "include_current": False,
            "length": "300-500 palavras",
            "save_as_chapter": False,
            "show_prompt": False
        }
        
        self.test_endpoint("POST", "/expand", data=expand_data, 
                          description="Expandir ideia")
        
    def run_maintenance_tests(self):
        """Testa endpoints de manutenção"""
        print("\n🛠️ TESTANDO MANUTENÇÃO & LIMPEZA")
        print("=" * 50)
        
        self.test_endpoint("POST", "/chroma/vectorize-existing", 
                          description="Vetorizar capítulos existentes")
        
        # Teste de debug
        debug_data = {
            "book_id": "test-book",
            "chapter_id": "test-chapter",
            "text": "Texto de teste para debug"
        }
        
        self.test_endpoint("POST", "/debug/metadata-extraction", data=debug_data, 
                          description="Debug de extração de metadados")
        
    def run_connectivity_tests(self):
        """Testa conectividade direta com serviços"""
        print("\n🌐 TESTANDO CONECTIVIDADE DIRETA")
        print("=" * 50)
        
        try:
            # Teste vLLM
            start_time = time.time()
            response = requests.get("http://localhost:8015/v1/models", timeout=10)
            response_time = time.time() - start_time
            success = response.status_code == 200
            self.log_test("GET vLLM /v1/models", success, response_time, 
                         f"HTTP {response.status_code}")
            
        except Exception as e:
            self.log_test("GET vLLM /v1/models", False, 0, f"Erro: {str(e)}")
            
        try:
            # Teste ChromaDB
            start_time = time.time()
            response = requests.get("http://localhost:8001/api/v2/heartbeat", timeout=10)
            response_time = time.time() - start_time
            success = response.status_code == 200
            self.log_test("GET ChromaDB /api/v2/heartbeat", success, response_time, 
                         f"HTTP {response.status_code}")
            
        except Exception as e:
            self.log_test("GET ChromaDB /api/v2/heartbeat", False, 0, f"Erro: {str(e)}")
    
    def run_all_tests(self):
        """Executa todos os testes"""
        print("🚀 INICIANDO TESTES COMPLETOS DA API BOOK ASSISTANT")
        print("=" * 60)
        print(f"URL Base: {self.base_url}")
        print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        start_time = time.time()
        
        self.run_health_tests()
        self.run_chapter_tests()
        self.run_ai_tests()
        self.run_maintenance_tests()
        self.run_connectivity_tests()
        
        total_time = time.time() - start_time
        
        # Resumo dos resultados
        print("\n📊 RESUMO DOS TESTES")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total de testes: {total_tests}")
        print(f"✅ Passou: {passed_tests}")
        print(f"❌ Falhou: {failed_tests}")
        print(f"⏱️  Tempo total: {total_time:.2f}s")
        
        if failed_tests == 0:
            print("\n🎉 TODOS OS TESTES PASSARAM!")
        else:
            print(f"\n⚠️  {failed_tests} teste(s) falharam. Verifique os logs acima.")
            
        return failed_tests == 0

def main():
    """Função principal"""
    print("Book Assistant API - Teste Completo")
    print("=" * 40)
    
    # Verifica se a API está rodando
    try:
        response = requests.get("http://localhost:8010/health", timeout=5)
        if response.status_code != 200:
            print("❌ API não está respondendo corretamente")
            print("   Certifique-se de que todos os serviços estão rodando:")
            print("   - API: http://localhost:8010")
            print("   - vLLM: http://localhost:8015")
            print("   - ChromaDB: http://localhost:8001")
            return False
    except Exception as e:
        print(f"❌ Não foi possível conectar com a API: {e}")
        return False
    
    # Executa os testes
    tester = BookAssistantTester()
    success = tester.run_all_tests()
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
