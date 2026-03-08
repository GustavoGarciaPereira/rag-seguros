#!/usr/bin/env python3
"""
Script para testar a instalação do Bradesco Insurance RAG Assistant
"""

import sys
import os
from importlib import util

def check_package(package_name, import_name=None):
    """Verifica se um pacote está instalado"""
    if import_name is None:
        import_name = package_name.replace('-', '_')
    
    try:
        if import_name == 'faiss':
            import faiss
            return True, f"✓ {package_name} instalado"
        else:
            spec = util.find_spec(import_name)
            if spec is not None:
                return True, f"✓ {package_name} instalado"
            else:
                return False, f"✗ {package_name} não encontrado"
    except ImportError:
        return False, f"✗ {package_name} não encontrado"

def test_imports():
    """Testa todas as importações necessárias"""
    packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("pypdf", "pypdf"),
        ("openai", "openai"),
        ("python-dotenv", "dotenv"),
        ("sentence-transformers", "sentence_transformers"),
        ("faiss-cpu", "faiss"),
        ("numpy", "numpy"),
    ]
    
    print("🔍 Testando importações...")
    all_ok = True
    
    for package_name, import_name in packages:
        success, message = check_package(package_name, import_name)
        print(f"  {message}")
        if not success:
            all_ok = False
    
    return all_ok

def test_file_structure():
    """Verifica a estrutura de arquivos"""
    print("\n📁 Verificando estrutura de arquivos...")
    
    required_files = [
        ("main.py", "Arquivo principal do servidor"),
        ("llm_service.py", "Serviço de IA"),
        ("vector_store_faiss.py", "Banco vetorial FAISS"),
        ("static/index.html", "Interface web"),
        (".env", "Configurações (pode ser .env.example)"),
    ]
    
    all_ok = True
    
    for file_path, description in required_files:
        if os.path.exists(file_path):
            print(f"  ✓ {description}: {file_path}")
        elif file_path == ".env" and os.path.exists(".env.example"):
            print(f"  ⚠️  {description}: .env.example encontrado (renomeie para .env)")
        else:
            print(f"  ✗ {description}: {file_path} não encontrado")
            all_ok = False
    
    return all_ok

def test_vector_store():
    """Testa o vector store"""
    print("\n🧠 Testando Vector Store (FAISS)...")
    
    try:
        from vector_store_faiss import VectorStoreFAISS
        vs = VectorStoreFAISS()
        stats = vs.get_collection_stats()
        print(f"  ✓ Vector Store inicializado")
        print(f"    • Chunks: {stats['total_chunks']}")
        print(f"    • Dimensão: {stats['embedding_dim']}")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao inicializar Vector Store: {e}")
        return False

def test_llm_service():
    """Testa o serviço de LLM"""
    print("\n🤖 Testando serviço de LLM...")
    
    try:
        from llm_service import LLMService
        
        # Verificar se a API key está configurada
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key or api_key == "sua_chave_aqui":
            print("  ⚠️  API Key não configurada (use .env)")
            print("  ⚠️  Teste de conexão com DeepSeek ignorado")
            return True  # Não é um erro fatal
        
        llm = LLMService()
        success, message = llm.test_connection()
        
        if success:
            print(f"  ✓ {message}")
            
            # Teste rápido de geração
            test_context = [{
                "text": "O seguro cobre danos por incêndio com franquia de R$ 1.000,00.",
                "relevance_score": 0.95,
                "source": "test.pdf",
                "chunk_index": 0
            }]
            
            answer = llm.generate_answer(test_context, "Qual é o valor da franquia?")
            if answer and len(answer) > 10:
                print(f"  ✓ Resposta gerada com sucesso ({len(answer)} caracteres)")
            else:
                print(f"  ⚠️  Resposta muito curta: {answer}")
            
            return True
        else:
            print(f"  ✗ {message}")
            return False
            
    except Exception as e:
        print(f"  ✗ Erro no serviço de LLM: {e}")
        return False

def main():
    """Função principal"""
    print("=" * 60)
    print("Bradesco Insurance RAG Assistant - Teste de Instalação")
    print("=" * 60)
    
    # Testar importações
    imports_ok = test_imports()
    
    # Testar estrutura de arquivos
    files_ok = test_file_structure()
    
    # Testar vector store
    vector_ok = test_vector_store()
    
    # Testar LLM service
    llm_ok = test_llm_service()
    
    print("\n" + "=" * 60)
    print("RESUMO DO TESTE:")
    print("=" * 60)
    
    if all([imports_ok, files_ok, vector_ok, llm_ok]):
        print("✅ TODOS OS TESTES PASSARAM!")
        print("\n🎉 Seu sistema está pronto para uso!")
        print("\nPara iniciar o servidor, execute:")
        print("  python run.py")
        print("\nOu diretamente:")
        print("  uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        return 0
    else:
        print("⚠️  ALGUNS TESTES FALHARAM")
        print("\nProblemas encontrados:")
        if not imports_ok:
            print("  • Dependências faltando - execute: pip install -r requirements.txt")
        if not files_ok:
            print("  • Arquivos faltando - verifique a estrutura do projeto")
        if not vector_ok:
            print("  • Problema com Vector Store - verifique instalação do FAISS")
        if not llm_ok:
            print("  • Problema com LLM Service - verifique API Key no .env")
        
        print("\n📋 Passos para resolver:")
        print("  1. Certifique-se de ter o Python 3.8+")
        print("  2. Execute: pip install -r requirements.txt")
        print("  3. Copie .env.example para .env e adicione sua API Key")
        print("  4. Execute este teste novamente")
        return 1

if __name__ == "__main__":
    sys.exit(main())