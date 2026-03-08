from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import tempfile
from typing import Optional, Dict, Any

# Usar FAISS em vez de ChromaDB
from vector_store_faiss import create_vector_store
from llm_service import create_llm_service

# Inicializar serviços
vector_store = create_vector_store()
llm_service = create_llm_service()

app = FastAPI(
    title="Multi-Seguradora Insurance RAG Assistant",
    description="Assistente de IA para análise de apólices de seguro (Bradesco, Porto Seguro, etc.)",
    version="1.1.0"
)

# ... (CORS configuration remains same)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Criar diretório para arquivos temporários
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Montar pasta estática para o frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve a página principal"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/health")
async def health_check():
    """Endpoint de verificação de saúde"""
    return {
        "status": "healthy",
        "service": "Insurance RAG Assistant",
        "vector_store": vector_store.get_collection_stats()
    }

@app.get("/status")
async def get_status():
    """Verifica se existem documentos prontos no banco"""
    count = vector_store.get_count()
    return {"total_chunks": count, "ready": count > 0}

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    seguradora: Optional[str] = Form(None),
    ano: Optional[int] = Form(None),
    tipo: Optional[str] = Form(None)
):
    """
    Endpoint para upload de PDFs com metadados
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")
    
    # Preparar metadados
    metadata = {}
    if seguradora: metadata["seguradora"] = seguradora
    if ano: metadata["ano"] = ano
    if tipo: metadata["tipo"] = tipo
    
    # Salvar arquivo temporariamente
    temp_path = os.path.join(TEMP_DIR, file.filename)
    
    try:
        # Salvar o arquivo
        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)
        
        # Processar o PDF com metadados
        chunks_added = vector_store.add_document(temp_path, metadata_input=metadata)
        
        # Limpar arquivo temporário
        os.remove(temp_path)
        
        return JSONResponse({
            "success": True,
            "message": f"Documento '{file.filename}' processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {str(e)}")

# Lista de seguradoras permitidas para validação
ALLOWED_SEGURADORAS = ["Bradesco", "Porto Seguro", "Azul", "Allianz", "Tokio Marine", "Liberty", "Mapfre"]

@app.post("/admin/upload")
async def admin_upload_pdf(
    file: UploadFile = File(...),
    seguradora: str = Form(...),
    ano: int = Form(...),
    tipo: Optional[str] = Form("Geral")
):
    """
    Endpoint administrativo para upload de documentos com curadoria
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")
    
    # Validação da seguradora
    if seguradora not in ALLOWED_SEGURADORAS:
        raise HTTPException(
            status_code=400, 
            detail=f"Seguradora não permitida. Escolha entre: {', '.join(ALLOWED_SEGURADORAS)}"
        )
    
    # Preparar metadados
    metadata = {
        "seguradora": seguradora,
        "ano": ano,
        "tipo": tipo
    }
    
    # Salvar arquivo temporariamente
    temp_path = os.path.join(TEMP_DIR, f"admin_{file.filename}")
    
    try:
        # Salvar o arquivo
        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)
        
        # Processar o PDF com metadados
        chunks_added = vector_store.add_document(temp_path, metadata_input=metadata)
        
        # Limpar arquivo temporário
        os.remove(temp_path)
        
        return JSONResponse({
            "success": True,
            "message": f"Documento da {seguradora} processado com sucesso!",
            "chunks_added": chunks_added,
            "filename": file.filename,
            "metadata": metadata
        })
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF administrativo: {str(e)}")

@app.post("/ask")
async def ask_question(data: dict):
    """
    Endpoint para fazer perguntas sobre os documentos com suporte a filtro
    
    Args:
        data: {
            "question": "sua pergunta aqui", 
            "n_results": 3, 
            "filter": {"seguradora": "Bradesco"}
        }
    """
    question = data.get("question")
    n_results = data.get("n_results", 3)
    filter_dict = data.get("filter")
    
    if not question:
        raise HTTPException(status_code=400, detail="A pergunta é obrigatória")
    
    try:
        # Buscar contexto relevante com filtro
        context = vector_store.query_documents(question, n_results=n_results, filter_dict=filter_dict)
        
        if not context:
            return JSONResponse({
                "success": True,
                "answer": "Não encontrei informações relevantes nos documentos filtrados para responder sua pergunta.",
                "context_used": [],
                "has_context": False
            })
        
        # Gerar resposta usando a IA
        answer = llm_service.generate_answer(context, question)
        
        # Preparar contexto para retorno
        context_preview = [
            {
                "text": ctx["text"][:200] + "..." if len(ctx["text"]) > 200 else ctx["text"],
                "source": ctx["source"],
                "page": ctx.get("page", 0),
                "seguradora": ctx.get("seguradora"),
                "relevance_score": round(ctx["relevance_score"], 3)
            }
            for ctx in context
        ]
        
        return JSONResponse({
            "success": True,
            "answer": answer,
            "context_used": context_preview,
            "has_context": True,
            "context_count": len(context)
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar pergunta: {str(e)}")

@app.get("/stats")
async def get_stats():
    """Retorna estatísticas do sistema"""
    try:
        vs_stats = vector_store.get_collection_stats()
        
        # Testar conexão com DeepSeek
        success, llm_status = llm_service.test_connection()
        
        return {
            "vector_store": vs_stats,
            "llm_service": {
                "status": "connected" if success else "disconnected",
                "message": llm_status
            },
            "temp_directory": TEMP_DIR,
            "service": "Bradesco Insurance RAG Assistant"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)