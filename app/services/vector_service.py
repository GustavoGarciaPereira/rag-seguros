import os
import re
import pickle
import faiss
from abc import ABC, abstractmethod
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import hashlib
from typing import List, Dict, Any

# Padrão para detectar limites semânticos em apólices de seguros
_CLAUSE_BOUNDARY = re.compile(
    r'\n{2,}'                                               # parágrafo duplo
    r'|\n(?=[ \t]*(?:'
    r'\d+(?:\.\d+)*\.?[ \t]'                               # cláusulas numeradas: "1.", "3.2."
    r'|Art\.?[ \t]|Artigo[ \t]'                            # artigos
    r'|SEÇ[AÃ]O\b|CAP[IÍ]TULO\b|CL[AÁ]USULA\b'          # seções
    r'|COBERTURA\b|EXCLUS[AÃ]O\b|FRANQUIA\b'              # blocos de apólice
    r'))',
    re.IGNORECASE,
)


class VectorStoreBase(ABC):
    @abstractmethod
    def search(self, query: str, n_results: int = 10, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def add_document(self, file_path: str, metadata_input: Dict[str, Any] = None) -> int:
        ...


class FAISSStore(VectorStoreBase):
    def __init__(self, persist_directory="./faiss_db"):
        """Inicializa o FAISS com persistência local"""
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)

        # Lazy loading: o modelo é carregado apenas na primeira chamada que o exige.
        # Isso evita bloquear o import/startup por ~60s no Render antes do healthcheck passar.
        self._embedding_model = None
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

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedding_model

    def warm_up(self):
        """Pré-carrega o modelo de embeddings. Chamado no startup para mover
        o carregamento pesado para antes do primeiro request real."""
        _ = self.embedding_model.encode("warm up")

    def _split_text_into_chunks(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[tuple]:
        """Divide o texto em chunks com sobreposição.
        Retorna lista de (chunk_text, start_pos) para permitir cálculo de página por posição."""
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

            chunks.append((chunk.strip(), start))

            # Mover para o próximo chunk com sobreposição
            start = end - overlap

            # Se chegamos ao final, sair
            if start >= len(text):
                break

        return chunks

    def _split_text_semantically(self, text: str, chunk_size: int = 1200, overlap: int = 200) -> List[tuple]:
        """Chunking semântico heurístico para apólices de seguros.

        Divide o texto nos limites naturais do documento (parágrafos, cláusulas numeradas,
        seções) antes de recorrer ao corte fixo por caractere. Isso mantém cláusulas
        inteiras no mesmo chunk, melhorando a precisão das citações.

        Retorna lista de (chunk_text, start_pos) — mesma interface de _split_text_into_chunks.
        """
        # Encontrar posições dos limites semânticos
        segments: List[tuple] = []
        last = 0
        for m in _CLAUSE_BOUNDARY.finditer(text):
            seg = text[last:m.start()].strip()
            if seg:
                segments.append((seg, last))
            last = m.end()
        if last < len(text):
            seg = text[last:].strip()
            if seg:
                segments.append((seg, last))

        if not segments:
            return self._split_text_into_chunks(text, chunk_size, overlap)

        # Agrupar segmentos em chunks respeitando chunk_size, com overlap
        chunks: List[tuple] = []
        current_parts: List[str] = []
        current_start = 0
        current_len = 0

        for seg_text, seg_pos in segments:
            if len(seg_text) > chunk_size:
                # Segmento isolado muito grande: fechar acumulado e subdividir
                if current_parts:
                    chunk = "\n\n".join(current_parts)
                    chunks.append((chunk, current_start))
                    current_parts, current_len = [], 0
                for sub_text, sub_pos in self._split_text_into_chunks(seg_text, chunk_size, overlap):
                    chunks.append((sub_text, seg_pos + sub_pos))
                current_start = 0
                continue

            if current_len + len(seg_text) + 2 > chunk_size and current_parts:
                # Fechar chunk atual e iniciar novo com overlap
                chunk = "\n\n".join(current_parts)
                chunks.append((chunk, current_start))
                overlap_text = chunk[-overlap:] if len(chunk) > overlap else chunk
                current_parts = [overlap_text, seg_text]
                current_start = seg_pos           # posição do novo conteúdo
                current_len = len(overlap_text) + len(seg_text) + 2
            else:
                if not current_parts:
                    current_start = seg_pos
                current_parts.append(seg_text)
                current_len += len(seg_text) + 2

        if current_parts:
            chunks.append(("\n\n".join(current_parts), current_start))

        return chunks if chunks else self._split_text_into_chunks(text, chunk_size, overlap)

    def _generate_document_id(self, file_path: str) -> str:
        """Gera um ID único para o documento baseado no conteúdo (hash MD5)"""
        with open(file_path, 'rb') as f:
            content_hash = hashlib.md5(f.read()).hexdigest()
        return f"{os.path.basename(file_path)}_{content_hash[:8]}"

    def _remove_document_chunks(self, doc_id: str) -> int:
        """Remove todos os chunks de um documento do índice, reconstruindo-o sem eles.
        Retorna o número de chunks removidos."""
        keep_mask = [m.get("document_id") != doc_id for m in self.metadata]
        removed = keep_mask.count(False)

        if removed == 0:
            return 0

        keep_texts = [t for t, keep in zip(self.document_texts, keep_mask) if keep]
        keep_metadata = [m for m, keep in zip(self.metadata, keep_mask) if keep]

        # Reconstruir índice FAISS sem os chunks removidos
        self.index = faiss.IndexFlatL2(self.embedding_dim)
        if keep_texts:
            embeddings = self.embedding_model.encode(keep_texts)
            self.index.add(embeddings.astype('float32'))

        self.metadata = keep_metadata
        self.document_texts = keep_texts
        return removed

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

        # Deduplicação: remove versão anterior do mesmo documento antes de reindexar
        removed = self._remove_document_chunks(doc_id)
        if removed > 0:
            print(f"Documento já existia — {removed} chunks removidos antes de reindexar.")

        all_chunks = []
        all_metadatas = []

        # Variável para manter o final da página anterior e garantir overlap entre páginas
        previous_page_tail = ""

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if not text or not text.strip():
                continue

            # Tamanho do tail: usado para calcular a qual página cada chunk pertence
            tail_len = len(previous_page_tail)

            # Combina o final da página anterior com o texto atual
            current_text = previous_page_tail + text

            # Dividir em chunks semânticos — retorna (chunk_text, start_pos)
            page_chunks = self._split_text_semantically(current_text, chunk_size=chunk_size, overlap=overlap)

            for chunk_text, start_pos in page_chunks:
                # Atribuir página pelo ponto médio do chunk:
                # se o meio cair dentro do tail, pertence à página anterior; caso contrário, à atual.
                chunk_mid = start_pos + len(chunk_text) // 2
                if tail_len > 0 and chunk_mid < tail_len:
                    assigned_page = page_num          # página anterior (1-indexada)
                else:
                    assigned_page = page_num + 1      # página atual (1-indexada)

                all_chunks.append(chunk_text)
                all_metadatas.append({
                    "source": file_path,
                    "document_id": doc_id,
                    "page": assigned_page,
                    "seguradora": seguradora,
                    "ano": ano,
                    "tipo": tipo,
                    "chunk_index": len(all_chunks) - 1
                })

            # Guarda o final desta página para a próxima (overlap)
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

    def _rerank_results(self, query_text: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reranking leve: combina score FAISS (70%) com sobreposição de termos da query (30%).

        Melhora a recuperação de termos específicos de seguros (valores em R$, nomes de
        coberturas) que podem ter baixo score semântico por embeddings genéricos.
        """
        _STOPWORDS_PT = {
            'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'o', 'a', 'os', 'as',
            'que', 'por', 'com', 'para', 'se', 'um', 'uma', 'no', 'na', 'nos',
            'nas', 'ao', 'aos', 'é', 'são', 'foi', 'ser', 'ter', 'mais', 'mas',
            'ou', 'também', 'não', 'sim', 'já', 'como', 'quando', 'seu', 'sua',
        }
        query_terms = set(re.sub(r'[^\w\s]', '', query_text.lower()).split()) - _STOPWORDS_PT
        if not query_terms:
            return results

        for result in results:
            text_terms = set(re.sub(r'[^\w\s]', '', result['text'].lower()).split())
            overlap = len(query_terms & text_terms) / len(query_terms)
            result['relevance_score'] = 0.7 * result['relevance_score'] + 0.3 * overlap

        return sorted(results, key=lambda x: x['relevance_score'], reverse=True)

    def search(self, query: str, n_results: int = 10, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Busca documentos relevantes (Top-K=10 para análise profunda de manuais densos)"""
        if self.index.ntotal == 0:
            return []

        # Se houver filtro, buscamos mais resultados para garantir que encontraremos o que precisamos após filtrar
        search_k = n_results * 5 if filter_dict else n_results

        # Gerar embedding da query
        query_embedding = self.embedding_model.encode([query]).astype('float32')

        # Buscar no FAISS
        distances, indices = self.index.search(query_embedding, min(search_k, self.index.ntotal))

        # Formatar resultados e aplicar filtro
        results = []
        for idx, distance in zip(indices[0], distances[0]):
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

        return self._rerank_results(query, results)

    def save_to_disk(self):
        """Salva o índice e metadados no disco"""
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'wb') as f:
            pickle.dump({
                'metadata': self.metadata,
                'document_texts': self.document_texts
            }, f)

    def load_from_disk(self):
        """Carrega o índice e metadados do disco"""
        self.index = faiss.read_index(self.index_path)
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
