#!/usr/bin/env python3
"""
Script para executar o servidor Bradesco Insurance RAG Assistant
"""

import os
import sys
import webbrowser
from dotenv import load_dotenv

def check_dependencies():
    """Verifica se todas as dependências estão instaladas"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'pypdf',
        'faiss',
        'sentence_transformers',
        'openai',
        'dotenv'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    return missing_packages

def setup_environment():
    """Configura o ambiente"""
    # Carregar variáveis de ambiente
    load_dotenv()
    
    # Verificar se a API key está configurada
    api_key = os.getenv("DEEPSEEK_API_KEY")
    
    if not api_key or api_key == "sua_chave_aqui":
        print("⚠️  ATENÇÃO: API Key não configurada!")
        print("Por favor, edite o arquivo .env e adicione sua chave da DeepSeek.")
        print("Exemplo: DEEPSEEK_API_KEY=sk-sua_chave_aqui")
        return False
    
    return True

def create_directories():
    """Cria diretórios necessários"""
    directories = ['temp_uploads', 'static']
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✓ Diretório criado: {directory}")

def main():
    """Função principal"""
    print("=" * 60)
    print("Bradesco Insurance RAG Assistant")
    print("=" * 60)
    
    # Verificar dependências
    print("\n🔍 Verificando dependências...")
    missing = check_dependencies()
    
    if missing:
        print(f"❌ Dependências faltando: {', '.join(missing)}")
        print("\nInstale as dependências com:")
        print("pip install -r requirements.txt")
        return 1
    
    print("✓ Todas as dependências estão instaladas")
    
    # Configurar ambiente
    print("\n⚙️  Configurando ambiente...")
    if not setup_environment():
        return 1
    
    print("✓ Ambiente configurado")
    
    # Criar diretórios
    print("\n📁 Criando diretórios...")
    create_directories()
    
    # Verificar se o frontend existe
    if not os.path.exists("static/index.html"):
        print("❌ Frontend não encontrado. Certifique-se de que static/index.html existe.")
        return 1
    
    # Iniciar servidor
    print("\n🚀 Iniciando servidor...")
    print("\n📊 Endpoints disponíveis:")
    print("  • http://localhost:8000/          - Interface web")
    print("  • http://localhost:8000/health    - Status do serviço")
    print("  • http://localhost:8000/stats     - Estatísticas")
    print("  • http://localhost:8000/docs      - Documentação da API")
    print("\n📝 Comandos úteis:")
    print("  • Ctrl+C para parar o servidor")
    print("  • Atualize a página web se houver problemas")
    
    # Abrir navegador automaticamente
    try:
        webbrowser.open("http://localhost:8000")
        print("\n🌐 Abrindo navegador...")
    except:
        print("\n📋 Abra manualmente: http://localhost:8000")
    
    print("\n" + "=" * 60)
    print("Servidor iniciado! Aguardando requisições...")
    print("=" * 60 + "\n")
    
    # Executar o servidor
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\n👋 Servidor encerrado pelo usuário")
        return 0
    except Exception as e:
        print(f"\n❌ Erro ao iniciar servidor: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())