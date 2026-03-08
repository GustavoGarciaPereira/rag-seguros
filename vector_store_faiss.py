import os
import pickle
import numpy as np
import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import hashlib
from typing import List, Dict, Any
import json

class VectorStoreFAISS:
    def __init__(self, persist_directory="./faiss_db"):
        """Inicializa o FAISS com persistência local"""
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        # Usar embeddings locais com Sentence Transformers
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embedding_dim = 384  # Dimensão do modelo all-MiniLM-L6-v2
        
        # Inicializar índice FAISS
        self.index_path = os.path.join(persist_directory, "faiss_index.bin")
        self.metadata_path = os.path.join(persist_directory, "metadata.pkl")
        
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.load_from_disk()
        else:
            self.index = faiss.IndexFlatL2(self.embedding_dim)
            self.metadata = []
            self.document_texts = []
    
    def _split_text_into_chunks(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Divide o texto em chunks com sobreposição"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            # Garantir que não cortamos palavras no meio
            if end < len(text) and text[end] != ' ':
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
    
    def _generate_document_id(self, file_path: str) -> str:
        """Gera um ID único para o documento"""
        with open(file_path, 'rb') as f:
            content_hash = hashlib.md5(f.read()).hexdigest()
        return f"{os.path.basename(file_path)}_{content_hash[:8]}"
    
    def add_document(self, file_path: str, metadata_input: Dict[str, Any] = None, chunk_size: int = 1200, overlap: int = 200) -> int:
        """Processa um PDF e adiciona ao banco vetorial com metadados e overlap entre páginas
        
        Args:
            chunk_size: Tamanho do chunk (padrão 1200 para preservar tabelas)
            overlap: Sobreposição entre chunks (padrão 200 para continuidade)
        """
        print(f"Processando documento: {file_path}")
        
        if metadata_input is None:
            metadata_input = {}
            
        seguradora = metadata_input.get("seguradora", "Desconhecida")
        ano = metadata_input.get("ano", 0)
        tipo = metadata_input.get("tipo", "Geral")
        
        reader = PdfReader(file_path)
        doc_id = self._generate_document_id(file_path)
        
        all_chunks = []
        all_metadatas = []
        
        # Variável para manter o final da página anterior e garantir overlap entre páginas
        previous_page_tail = ""
        
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text or not text.strip():
                continue
            
            # Combina o final da página anterior com o texto atual
            current_text = previous_page_tail + text
            
            # Dividir a página em chunks com o overlap configurado
            page_chunks = self._split_text_into_chunks(current_text, chunk_size=chunk_size, overlap=overlap)
            
            for i, chunk in enumerate(page_chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    "source": file_path,
                    "document_id": doc_id,
                    "page": page_num + 1,
                    "seguradora": seguradora,
                    "ano": ano,
                    "tipo": tipo,
                    "chunk_index": len(all_chunks) - 1
                })
            
            # Guarda o final desta página para a próxima (overlap)
            # Pegamos aproximadamente o dobro do overlap para garantir contexto suficiente
            if len(text) > overlap:
                previous_page_tail = text[-overlap:]
            else:
                previous_page_tail = text
        
        if not all_chunks:
            raise ValueError("Não foi possível extrair texto do PDF")
        
        print(f"Documento dividido em {len(all_chunks)} chunks em {len(reader.pages)} páginas")
        
        embeddings = self.embedding_model.encode(all_chunks)
        self.index.add(embeddings.astype('float32'))
        self.metadata.extend(all_metadatas)
        self.document_texts.extend(all_chunks)
        
        self.save_to_disk()
        return len(all_chunks)
    
    def query_documents(self, query_text: str, n_results: int = 10, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Busca documentos relevantes (Top-K=10 para análise profunda de manuais densos)"""
        if self.index.ntotal == 0:
            return []
        
        # Se houver filtro, buscamos mais resultados para garantir que encontraremos o que precisamos após filtrar
        search_k = n_results * 5 if filter_dict else n_results
        
        # Gerar embedding da query
        query_embedding = self.embedding_model.encode([query_text]).astype('float32')
        
        # Buscar no FAISS
        distances, indices = self.index.search(query_embedding, min(search_k, self.index.ntotal))
        
        # Formatar resultados e aplicar filtro
        results = []
        for i, (idx, distance) in enumerate(zip(indices[0], distances[0])):
            if idx < 0 or idx >= len(self.metadata):
                continue
                
            meta = self.metadata[idx]
            
            # Aplicar filtro se fornecido
            if filter_dict:
                match = True
                for key, value in filter_dict.items():
                    if key in meta and meta[key] != value:
                        match = False
                        break
                if not match:
                    continue
            
            results.append({
                "text": self.document_texts[idx],
                "source": meta["source"],
                "page": meta.get("page", 0),
                "seguradora": meta.get("seguradora", "Desconhecida"),
                "ano": meta.get("ano", 0),
                "tipo": meta.get("tipo", "Geral"),
                "relevance_score": float(1 / (1 + distance))
            })
            
            # Se já atingimos o número solicitado de resultados após o filtro, paramos
            if len(results) >= n_results:
                break
        
        return results
    
    def save_to_disk(self):
        """Salva o índice e metadados no disco"""
        # Salvar índice FAISS
        faiss.write_index(self.index, self.index_path)
        
        # Salvar metadados
        with open(self.metadata_path, 'wb') as f:
            pickle.dump({
                'metadata': self.metadata,
                'document_texts': self.document_texts
            }, f)
    
    def load_from_disk(self):
        """Carrega o índice e metadados do disco"""
        # Carregar índice FAISS
        self.index = faiss.read_index(self.index_path)
        
        # Carregar metadados
        with open(self.metadata_path, 'rb') as f:
            data = pickle.load(f)
            self.metadata = data['metadata']
            self.document_texts = data['document_texts']
    
    def get_count(self) -> int:
        """Retorna o número total de chunks indexados"""
        return self.index.ntotal

    def get_collection_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da coleção"""
        return {
            "total_chunks": self.index.ntotal,
            "persist_directory": self.persist_directory,
            "embedding_dim": self.embedding_dim
        }

# Função de conveniência
def create_vector_store():
    return VectorStoreFAISS()

if __name__ == "__main__":
    # Teste rápido
    vs = VectorStoreFAISS()
    print("VectorStore (FAISS) inicializado com sucesso!")
    print(f"Estatísticas: {vs.get_collection_stats()}")