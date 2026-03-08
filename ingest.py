"""
ingest.py — Ingestão local de PDFs para o índice FAISS.

Uso:
    python ingest.py [--pdf-dir ./pdfs]

Roda LOCALMENTE. O faiss_db/ gerado deve ser commitado e enviado
ao repositório para que o Render sirva o índice pré-construído.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from vector_store_faiss import create_vector_store

load_dotenv()

ALLOWED_SEGURADORAS = ["Bradesco", "Porto Seguro", "Azul", "Allianz", "Tokio Marine", "Liberty", "Mapfre"]


def prompt_metadata(filename: str) -> dict:
    print(f"\n--- {filename} ---")
    print(f"Seguradoras disponíveis: {', '.join(ALLOWED_SEGURADORAS)}")

    while True:
        seguradora = input("  Seguradora: ").strip()
        if seguradora in ALLOWED_SEGURADORAS:
            break
        print(f"  Inválida. Escolha entre: {', '.join(ALLOWED_SEGURADORAS)}")

    while True:
        ano_str = input("  Ano (ex: 2024): ").strip()
        if ano_str.isdigit() and 2000 <= int(ano_str) <= 2100:
            ano = int(ano_str)
            break
        print("  Ano inválido.")

    tipo = input("  Tipo (ex: Geral, Auto, Vida) [Geral]: ").strip() or "Geral"

    return {"seguradora": seguradora, "ano": ano, "tipo": tipo}


def main():
    parser = argparse.ArgumentParser(description="Indexa PDFs localmente no faiss_db/")
    parser.add_argument("--pdf-dir", default="./pdfs", help="Pasta com os PDFs (padrão: ./pdfs)")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        print(f"Pasta '{pdf_dir}' não encontrada. Crie-a e coloque os PDFs lá.")
        sys.exit(1)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"Nenhum PDF encontrado em '{pdf_dir}'.")
        sys.exit(0)

    print(f"Encontrados {len(pdf_files)} PDF(s) em '{pdf_dir}':")
    for p in pdf_files:
        print(f"  • {p.name}")

    vs = create_vector_store()

    total_docs = 0
    total_chunks = 0

    for pdf_path in pdf_files:
        metadata = prompt_metadata(pdf_path.name)
        try:
            chunks = vs.add_document(str(pdf_path), metadata_input=metadata)
            print(f"  OK — {chunks} chunks indexados")
            total_docs += 1
            total_chunks += chunks
        except Exception as e:
            print(f"  ERRO ao processar '{pdf_path.name}': {e}")

    print(f"\n{'='*50}")
    print(f"Resumo: {total_docs} documento(s), {total_chunks} chunks indexados")
    print(f"Índice salvo em: {vs.persist_directory}")
    print(f"\nPróximos passos:")
    print(f"  git add faiss_db/")
    print(f"  git commit -m 'atualiza indice FAISS'")
    print(f"  git push")


if __name__ == "__main__":
    main()
