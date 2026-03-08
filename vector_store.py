import os
import chromadb
from chromadb.config import Settings
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import hashlib

class VectorStore:
    def __init__(self, persist_directory="./chroma_db"):
        """Inicializa o ChromaDB com persistência local"""
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Usar embeddings locais com Sentence Transformers
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Criar ou obter a coleção
        self.collection = self.client.get_or_create_collection(
            name="insurance_documents",
            metadata={"hnsw:space": "cosine"}
        )
    
    def _split_text_into_chunks(self, text, chunk_size=500, overlap=50):
        """Divide o texto em chunks com sobreposição"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            # Garantir que não cortamos palavras no meio
            if end < len(text) and text[end] != ' ':
                # Encontrar o último espaço no chunk
                last_space = chunk.rfind(' ')
                if last_space != -1:
                    end = start + last_space + 1
                    chunk = text[start:end]
            
            chunks.append(chunk.strip())
            
            # Mover para o próximo chunk com sobreposição
            start = end - overlap
            
            # Se chegamos ao final, sair
            if start >= len(text):
                break
        
        return chunks
    
    def _generate_document_id(self, file_path):
        """Gera um ID único para o documento baseado no caminho e conteúdo"""
        with open(file_path, 'rb') as f:
            content_hash = hashlib.md5(f.read()).hexdigest()
        return f"{os.path.basename(file_path)}_{content_hash[:8]}"
    
    def add_document(self, file_path):
        """Processa um PDF e adiciona ao banco vetorial"""
        print(f"Processando documento: {file_path}")
        
        # Ler o PDF
        reader = PdfReader(file_path)
        full_text = ""
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        if not full_text.strip():
            raise ValueError("Não foi possível extrair texto do PDF")
        
        # Dividir em chunks
        chunks = self._split_text_into_chunks(full_text)
        print(f"Documento dividido em {len(chunks)} chunks")
        
        # Gerar IDs únicos para cada chunk
        doc_id = self._generate_document_id(file_path)
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        
        # Gerar embeddings para todos os chunks de uma vez
        embeddings = self.embedding_model.encode(chunks).tolist()
        
        # Adicionar ao ChromaDB
        self.collection.add(
            documents=chunks,
            embeddings=embeddings,
            ids=chunk_ids,
            metadatas=[{"source": file_path, "chunk_index": i} for i in range(len(chunks))]
        )
        
        print(f"Documento '{file_path}' adicionado com sucesso!")
        return len(chunks)
    
    def query_documents(self, query_text, n_results=3):
        """Busca documentos relevantes para uma consulta"""
        # Gerar embedding da query
        query_embedding = self.embedding_model.encode([query_text]).tolist()[0]
        
        # Buscar no ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        # Formatar resultados
        formatted_results = []
        if results['documents']:
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            )):
                formatted_results.append({
                    "text": doc,
                    "source": metadata["source"],
                    "chunk_index": metadata["chunk_index"],
                    "relevance_score": 1 - distance  # Converter distância para score de relevância
                })
        
        return formatted_results
    
    def get_collection_stats(self):
        """Retorna estatísticas da coleção"""
        count = self.collection.count()
        return {
            "total_chunks": count,
            "persist_directory": self.persist_directory
        }

# Função de conveniência para uso rápido
def create_vector_store():
    return VectorStore()

if __name__ == "__main__":
    # Teste rápido
    vs = VectorStore()
    print("VectorStore inicializado com sucesso!")
    print(f"Estatísticas: {vs.get_collection_stats()}")