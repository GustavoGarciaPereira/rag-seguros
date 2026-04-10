#!/usr/bin/env python3
"""ingest.py — indexa PDFs no FAISS de forma interativa.

Usa o mesmo Use Case ``IngestDocument`` da API, garantindo que a lógica
de parsing, chunking e deduplicação seja idêntica em ambos os contextos.

Uso:
    python ingest.py [--pdf-dir ./pdfs]
"""

import argparse
import os
import sys

from app.core.dependencies import get_ingest_use_case
from app.domain.entities.document import InsuranceMetadata
from app.domain.entities.insurance import DocumentType, Seguradora


def _prompt_seguradora() -> str:
    opcoes = Seguradora.allowed_for_admin()
    print("\nSeguradoras disponíveis:")
    for i, seg in enumerate(opcoes, 1):
        print(f"  {i}. {seg}")
    while True:
        entrada = input("Seguradora (nome ou número): ").strip()
        if entrada.isdigit():
            idx = int(entrada) - 1
            if 0 <= idx < len(opcoes):
                return opcoes[idx]
            print(f"  Número inválido. Escolha entre 1 e {len(opcoes)}.")
        elif entrada in opcoes:
            return entrada
        else:
            print(f"  Seguradora '{entrada}' não reconhecida.")


def _prompt_ano() -> int:
    while True:
        ano = input("Ano do documento (ex: 2024): ").strip()
        if ano.isdigit() and 1900 <= int(ano) <= 2100:
            return int(ano)
        print("  Ano inválido. Informe um número entre 1900 e 2100.")


def _prompt_tipo() -> str:
    tipos = sorted(t.value for t in DocumentType)
    print(f"\nTipos disponíveis: {', '.join(tipos)}")
    while True:
        tipo = input("Tipo do documento: ").strip()
        if tipo in tipos:
            return tipo
        # Aceita case-insensitive
        match = next((t for t in tipos if t.lower() == tipo.lower()), None)
        if match:
            return match
        print(f"  Tipo '{tipo}' não reconhecido.")


def prompt_metadata(pdf_path: str) -> InsuranceMetadata:
    print(f"\n{'=' * 60}")
    print(f"Arquivo: {os.path.basename(pdf_path)}")
    print(f"{'=' * 60}")
    return InsuranceMetadata(
        seguradora=_prompt_seguradora(),
        ano=_prompt_ano(),
        tipo=_prompt_tipo(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa PDFs no FAISS interativamente.")
    parser.add_argument(
        "--pdf-dir", default="./pdfs", help="Pasta com os PDFs (padrão: ./pdfs)"
    )
    args = parser.parse_args()

    pdf_dir = args.pdf_dir
    if not os.path.isdir(pdf_dir):
        print(f"Erro: pasta '{pdf_dir}' não encontrada.")
        sys.exit(1)

    pdfs = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em '{pdf_dir}'.")
        sys.exit(0)

    print(f"\nEncontrados {len(pdfs)} PDF(s) em '{pdf_dir}'.")

    ingest = get_ingest_use_case()

    total_chunks = 0
    total_docs = 0

    for filename in pdfs:
        pdf_path = os.path.join(pdf_dir, filename)
        try:
            metadata = prompt_metadata(pdf_path)
            print(f"\nIndexando '{filename}'...")
            chunks = ingest.execute(pdf_path, metadata, source_name=filename)
            print(f"  OK — {chunks} chunk(s) no índice.")
            total_chunks += chunks
            total_docs += 1
        except KeyboardInterrupt:
            print("\n\nInterrompido pelo usuário.")
            break
        except Exception as exc:
            print(f"  Erro ao indexar '{filename}': {exc}")

    print(f"\n{'=' * 60}")
    print(f"Resumo: {total_docs} documento(s), {total_chunks} chunk(s) no total.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
