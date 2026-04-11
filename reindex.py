#!/usr/bin/env python3
"""reindex.py — apaga o índice atual e re-indexa todos os PDFs em ./pdfs/.

Útil após mudanças no chunker (ex: injeção de headers de seção) que exigem
re-embeddinging completo dos documentos.

Fluxo:
  1. Lista PDFs em --pdf-dir (default ./pdfs/)
  2. Auto-detecta metadados (seguradora, ramo, ano) a partir do nome do arquivo
  3. Exibe tabela de prévia e pede confirmação (ou usa --yes/-y para pular)
  4. Apaga faiss_db/faiss_index.bin e faiss_db/metadata.db
  5. Indexa cada PDF usando o mesmo IngestDocument da API
  6. Exibe relatório final

Metadados não detectáveis recebem valores-padrão ("Desconhecida", 0, "Geral").
Use ingest.py para coleta interativa com metadados precisos.

Uso:
    python reindex.py [--pdf-dir ./pdfs] [--yes]
"""

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

from app.domain.entities.document import InsuranceMetadata
from app.domain.entities.insurance import Ramo, Seguradora

# ---------------------------------------------------------------------------
# Auto-detect de metadados a partir do nome do arquivo
# (lógica idêntica ao ingest.py, intencionalmente não importada de lá)
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s.lower().strip())


def _detect_seguradora(filename: str) -> Optional[str]:
    name = _norm(filename)
    opcoes = Seguradora.allowed_for_admin()
    for seg in sorted(opcoes, key=len, reverse=True):
        if _norm(seg) in name:
            return seg
    return None


def _detect_ramo(filename: str) -> Optional[str]:
    name = _norm(filename)
    opcoes = [r.value for r in Ramo if r is not Ramo.DESCONHECIDO]
    for ramo in sorted(opcoes, key=len, reverse=True):
        if _norm(ramo) in name:
            return ramo
    return None


def _detect_ano(filename: str) -> Optional[int]:
    matches = re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", filename)
    return int(matches[0]) if matches else None


def _build_metadata(filename: str) -> Tuple[InsuranceMetadata, List[str]]:
    """Retorna (InsuranceMetadata, lista_de_avisos) para o arquivo."""
    seg = _detect_seguradora(filename)
    ramo = _detect_ramo(filename)
    ano = _detect_ano(filename)

    warnings = []
    if seg is None:
        warnings.append("seguradora não detectada → 'Desconhecida'")
        seg = "Desconhecida"
    if ramo is None:
        ramo = Ramo.DESCONHECIDO.value
    if ano is None:
        warnings.append("ano não detectado → 0")
        ano = 0

    return InsuranceMetadata(seguradora=seg, ano=ano, tipo="Geral", ramo=ramo), warnings


# ---------------------------------------------------------------------------
# Tabela de prévia
# ---------------------------------------------------------------------------

def _print_preview(rows: List[Tuple[str, InsuranceMetadata]]) -> None:
    MAX_FILE = 40

    def trunc(s: str) -> str:
        return s[: MAX_FILE - 1] + "…" if len(s) > MAX_FILE else s

    display = [trunc(f) for f, _ in rows]
    wf = max(len("Arquivo"), max(len(d) for d in display))
    ws = max(len("Seguradora"), max(len(m.seguradora) for _, m in rows))
    wr = max(len("Ramo"),       max(len(m.ramo)       for _, m in rows))
    wa = max(len("Ano"),        max(len(str(m.ano))   for _, m in rows))

    def row(f, s, r, a):
        return f"  | {f:<{wf}} | {s:<{ws}} | {r:<{wr}} | {a:<{wa}} |"

    sep = f"  +-{'-'*wf}-+-{'-'*ws}-+-{'-'*wr}-+-{'-'*wa}-+"

    print(f"\n{'=' * 70}")
    print("  PDFs a re-indexar")
    print(sep)
    print(row("Arquivo", "Seguradora", "Ramo", "Ano"))
    print(sep)
    for disp, (_, meta) in zip(display, rows):
        print(row(disp, meta.seguradora, meta.ramo, str(meta.ano)))
    print(sep)


# ---------------------------------------------------------------------------
# Wipe do banco
# ---------------------------------------------------------------------------

FAISS_INDEX = os.path.join("faiss_db", "faiss_index.bin")
METADATA_DB = os.path.join("faiss_db", "metadata.db")


def _wipe_db() -> None:
    """Apaga faiss_index.bin e metadata.db (chunks + documents)."""
    for path in (FAISS_INDEX, METADATA_DB):
        if os.path.exists(path):
            os.remove(path)
            print(f"  Apagado: {path}")
        else:
            print(f"  (não encontrado, ignorado): {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-indexa todos os PDFs do zero (apaga índice atual)."
    )
    parser.add_argument("--pdf-dir", default="./pdfs", help="Pasta com os PDFs (padrão: ./pdfs)")
    parser.add_argument("--yes", "-y", action="store_true", help="Pula confirmação interativa")
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

    # ── Fase 1: construir metadados + coletar avisos ───────────────────────
    batch: List[Tuple[str, InsuranceMetadata]] = []
    all_warnings: List[Tuple[str, List[str]]] = []

    for filename in pdfs:
        meta, warns = _build_metadata(filename)
        batch.append((filename, meta))
        if warns:
            all_warnings.append((filename, warns))

    # ── Fase 2: prévia ────────────────────────────────────────────────────
    _print_preview(batch)

    if all_warnings:
        print("\n  Avisos de detecção automática:")
        for fname, warns in all_warnings:
            for w in warns:
                print(f"    - {fname}: {w}")

    print(f"\n  ATENÇÃO: faiss_index.bin e metadata.db serão APAGADOS.")
    print(f"  Todos os {len(pdfs)} PDF(s) serão re-indexados do zero.")

    if not args.yes:
        try:
            resp = input("\nConfirmar? (s/N): ").strip().lower()
        except KeyboardInterrupt:
            print("\n\nCancelado.")
            sys.exit(0)
        if resp not in ("s", "sim", "y", "yes"):
            print("Cancelado.")
            sys.exit(0)

    # ── Fase 3: wipe ──────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  Limpando banco de dados...")
    print(f"{'=' * 70}")
    _wipe_db()

    # ── Fase 4: indexação ─────────────────────────────────────────────────
    # Importado aqui (após o wipe) para que lru_cache crie instâncias frescas
    # apontando para arquivos inexistentes → FAISSVectorRepository cria índice vazio.
    from app.core.dependencies import get_ingest_use_case  # noqa: PLC0415

    print(f"\n{'=' * 70}")
    print("  Iniciando re-indexação...")
    print(f"{'=' * 70}")

    ingest = get_ingest_use_case()
    total_chunks = 0
    processed = 0
    errors: List[Tuple[str, str]] = []

    for i, (filename, meta) in enumerate(batch, 1):
        pdf_path = os.path.join(pdf_dir, filename)
        try:
            print(f"\n  [{i}/{len(batch)}] {filename} ... ", end="", flush=True)
            chunks = ingest.execute(pdf_path, meta, source_name=filename)
            print(f"OK — {chunks} chunk(s).")
            total_chunks += chunks
            processed += 1
        except KeyboardInterrupt:
            print("\n\nInterrompido durante o processamento.")
            break
        except Exception as exc:
            print(f"ERRO: {exc}")
            errors.append((filename, str(exc)))

    # ── Relatório final ───────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(
        f"  Concluído: {processed}/{len(batch)} documento(s), "
        f"{total_chunks} chunk(s) adicionados."
    )
    if errors:
        print(f"\n  Falhas ({len(errors)}):")
        for fname, err in errors:
            print(f"    - {fname}: {err}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
