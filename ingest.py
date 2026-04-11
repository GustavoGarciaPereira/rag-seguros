#!/usr/bin/env python3
"""ingest.py — indexa PDFs no FAISS com alta produtividade.

Fluxo em 4 fases:
  1. Coleta de metadados (auto-detect + session memory + confirmação rápida)
  2. Resumo do lote + prévia de renomeação + confirmação final
  3. Renomeação física dos arquivos (com fallback em caso de erro)
  4. Indexação em sequência com relatório de progresso

Uso:
    python ingest.py [--pdf-dir ./pdfs]
"""

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.domain.entities.document import InsuranceMetadata
from app.domain.entities.insurance import DocumentType, Ramo, Seguradora


# ---------------------------------------------------------------------------
# Auto-detect: extrai seguradora / ramo / ano do nome do arquivo
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normaliza para comparação: minúsculas, sem underscores/hífens extras."""
    return re.sub(r"[\s_\-]+", " ", s.lower().strip())


def _detect_seguradora(filename: str) -> Optional[str]:
    name = _norm(filename)
    opcoes = Seguradora.allowed_for_admin()
    # Ordena por comprimento decrescente: "Porto Seguro" antes de "Porto"
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


def _detect(filename: str) -> Dict[str, object]:
    return {
        "seguradora": _detect_seguradora(filename),
        "ramo": _detect_ramo(filename),
        "ano": _detect_ano(filename),
    }


# ---------------------------------------------------------------------------
# Renomeação automática
# ---------------------------------------------------------------------------

def _sanitize(s: str) -> str:
    """Substitui espaços por _ e remove caracteres não-seguros para o filesystem."""
    s = s.replace(" ", "_")
    # Mantém apenas letras, dígitos, underscores e hífens
    s = re.sub(r"[^\w\-]", "", s, flags=re.ASCII)
    return s


def _build_new_name(original_filename: str, meta: InsuranceMetadata) -> str:
    """Gera o nome canônico: {Seguradora}_{Ramo}_{Tipo}_{Ano}_{suffix5}.pdf

    O suffix de 5 caracteres é derivado deterministicamente do nome original,
    garantindo unicidade sem depender de estado externo.
    """
    stem = os.path.splitext(original_filename)[0]
    suffix = hashlib.sha1(stem.encode()).hexdigest()[:5]
    parts = [
        _sanitize(meta.seguradora),
        _sanitize(meta.ramo),
        _sanitize(meta.tipo),
        str(meta.ano),
        suffix,
    ]
    return "_".join(parts) + ".pdf"


def _rename_batch(
    batch: List[Tuple[str, InsuranceMetadata]],
    pdf_dir: str,
) -> List[Tuple[str, str, InsuranceMetadata]]:
    """Renomeia os arquivos físicos e retorna lista de (orig, final_name, meta).

    Se a renomeação falhar para um arquivo, emite aviso e mantém o nome original.
    """
    result: List[Tuple[str, str, InsuranceMetadata]] = []

    for original_filename, meta in batch:
        new_filename = _build_new_name(original_filename, meta)
        src = os.path.join(pdf_dir, original_filename)
        dst = os.path.join(pdf_dir, new_filename)

        # Já tem o nome certo (re-run ou sem mudança)
        if os.path.abspath(src) == os.path.abspath(dst):
            result.append((original_filename, original_filename, meta))
            continue

        # Colisão com arquivo diferente → fallback
        if os.path.exists(dst):
            print(
                f"  AVISO: '{new_filename}' já existe. "
                f"Usando nome original para '{original_filename}'."
            )
            result.append((original_filename, original_filename, meta))
            continue

        try:
            os.rename(src, dst)
            print(f"  Renomeado: {original_filename}  →  {new_filename}")
            result.append((original_filename, new_filename, meta))
        except OSError as exc:
            print(
                f"  AVISO: Falha ao renomear '{original_filename}' "
                f"({exc}). Usando nome original."
            )
            result.append((original_filename, original_filename, meta))

    return result


# ---------------------------------------------------------------------------
# Resolução de entrada: índice numérico ou nome (case-insensitive)
# ---------------------------------------------------------------------------

def _resolve(entrada: str, opcoes: List[str]) -> Optional[str]:
    if entrada.isdigit():
        idx = int(entrada) - 1
        if 0 <= idx < len(opcoes):
            return opcoes[idx]
        return None
    return next((o for o in opcoes if o.lower() == entrada.lower()), None)


# ---------------------------------------------------------------------------
# Prompts individuais com sugestão / padrão de sessão
# ---------------------------------------------------------------------------

def _prompt_seguradora(suggestion: Optional[str], default: Optional[str]) -> str:
    opcoes = Seguradora.allowed_for_admin()
    hint = suggestion or default
    label = "Sugestão" if suggestion else "Padrão"

    print("\n  Seguradoras:")
    for i, seg in enumerate(opcoes, 1):
        marker = "  <" if seg == hint else ""
        print(f"    {i:2}. {seg}{marker}")

    prompt = (
        f"  Seguradora [{label}: {hint}] (Enter para confirmar ou nome/número): "
        if hint else
        "  Seguradora (nome ou número): "
    )
    while True:
        entrada = input(prompt).strip()
        if not entrada and hint:
            return hint
        resolved = _resolve(entrada, opcoes)
        if resolved:
            return resolved
        print(f"    '{entrada}' não reconhecido.")


def _prompt_ramo(suggestion: Optional[str], default: Optional[str]) -> str:
    opcoes = [r.value for r in Ramo if r is not Ramo.DESCONHECIDO]
    hint = suggestion or default
    label = "Sugestão" if suggestion else "Padrão"

    print("\n  Ramos:")
    for i, r in enumerate(opcoes, 1):
        marker = "  <" if r == hint else ""
        print(f"    {i:2}. {r}{marker}")

    if hint:
        prompt = f"  Ramo [{label}: {hint}] (Enter para confirmar, 0=Desconhecido, ou nome/número): "
    else:
        prompt = "  Ramo (nome ou número, Enter=Desconhecido): "

    while True:
        entrada = input(prompt).strip()
        if not entrada:
            return hint or "Desconhecido"
        if entrada == "0":
            return "Desconhecido"
        resolved = _resolve(entrada, opcoes)
        if resolved:
            return resolved
        print(f"    '{entrada}' não reconhecido.")


def _prompt_ano(suggestion: Optional[int], default: Optional[int]) -> int:
    hint = suggestion if suggestion is not None else default
    label = "Sugestão" if suggestion is not None else "Padrão"

    prompt = (
        f"  Ano [{label}: {hint}] (Enter para confirmar ou novo ano): "
        if hint is not None else
        "  Ano do documento (ex: 2024): "
    )
    while True:
        entrada = input(prompt).strip()
        if not entrada and hint is not None:
            return hint
        if entrada.isdigit() and 1900 <= int(entrada) <= 2100:
            return int(entrada)
        print("    Ano inválido. Informe um número entre 1900 e 2100.")


def _prompt_tipo(default: Optional[str]) -> str:
    tipos = sorted(t.value for t in DocumentType)
    hint = default or "Geral"
    print(f"\n  Tipos: {', '.join(tipos)}")
    prompt = f"  Tipo [Padrão: {hint}] (Enter para confirmar ou nome): "
    while True:
        entrada = input(prompt).strip()
        if not entrada:
            return hint
        match = next((t for t in tipos if t.lower() == entrada.lower()), None)
        if match:
            return match
        print(f"    '{entrada}' não reconhecido.")


# ---------------------------------------------------------------------------
# Session memory + coleta por arquivo
# ---------------------------------------------------------------------------

@dataclass
class _Session:
    seguradora: Optional[str] = None
    ramo: Optional[str] = None
    ano: Optional[int] = None
    tipo: Optional[str] = None


def _collect_one(filename: str, session: _Session) -> InsuranceMetadata:
    detected = _detect(filename)

    parts = []
    if detected["seguradora"]:
        parts.append(f"seguradora='{detected['seguradora']}'")
    if detected["ramo"]:
        parts.append(f"ramo='{detected['ramo']}'")
    if detected["ano"]:
        parts.append(f"ano={detected['ano']}")
    print(f"  Auto-detect: {', '.join(parts) if parts else '(nada detectado)'}")

    seguradora = _prompt_seguradora(detected["seguradora"], session.seguradora)
    ramo = _prompt_ramo(detected["ramo"], session.ramo)
    ano = _prompt_ano(detected["ano"], session.ano)
    tipo = _prompt_tipo(session.tipo)

    session.seguradora = seguradora
    session.ramo = ramo
    session.ano = ano
    session.tipo = tipo

    return InsuranceMetadata(seguradora=seguradora, ano=ano, tipo=tipo, ramo=ramo)


# ---------------------------------------------------------------------------
# Batch summary table (com prévia de renomeação)
# ---------------------------------------------------------------------------

def _print_summary(batch: List[Tuple[str, InsuranceMetadata]]) -> None:
    MAX_FILE = 38

    def trunc(s: str) -> str:
        return s[: MAX_FILE - 1] + "…" if len(s) > MAX_FILE else s

    display = [trunc(f) for f, _ in batch]

    wf = max(len("Arquivo"), max(len(d) for d in display))
    ws = max(len("Seguradora"), max(len(m.seguradora) for _, m in batch))
    wr = max(len("Ramo"), max(len(m.ramo) for _, m in batch))
    wa = max(len("Ano"), max(len(str(m.ano)) for _, m in batch))
    wt = max(len("Tipo"), max(len(m.tipo) for _, m in batch))

    def row(f, s, r, a, t):
        return f"  | {f:<{wf}} | {s:<{ws}} | {r:<{wr}} | {a:<{wa}} | {t:<{wt}} |"

    sep = f"  +-{'-'*wf}-+-{'-'*ws}-+-{'-'*wr}-+-{'-'*wa}-+-{'-'*wt}-+"

    print(f"\n{'=' * 70}")
    print("  RESUMO DO LOTE")
    print(sep)
    print(row("Arquivo", "Seguradora", "Ramo", "Ano", "Tipo"))
    print(sep)
    for disp, (_, meta) in zip(display, batch):
        print(row(disp, meta.seguradora, meta.ramo, str(meta.ano), meta.tipo))
    print(sep)

    # Prévia de renomeação
    renames = [
        (f, _build_new_name(f, meta))
        for f, meta in batch
        if f != _build_new_name(f, meta)
    ]
    if renames:
        max_orig = max(len(f) for f, _ in renames)
        print(f"\n  Renomeação prevista ({len(renames)} arquivo(s)):")
        for orig, novo in renames:
            print(f"    {orig:<{max_orig}}  →  {novo}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    print("Pressione Ctrl+C a qualquer momento para cancelar sem processar nada.\n")

    session = _Session()
    batch: List[Tuple[str, InsuranceMetadata]] = []

    # ── Fase 1: coletar metadados ──────────────────────────────────────────
    try:
        for filename in pdfs:
            print(f"\n{'─' * 60}")
            print(f"  [{len(batch) + 1}/{len(pdfs)}] {filename}")
            meta = _collect_one(filename, session)
            batch.append((filename, meta))
    except KeyboardInterrupt:
        print("\n\nCancelado. Nenhum arquivo foi processado.")
        sys.exit(0)

    # ── Fase 2: resumo + confirmação ──────────────────────────────────────
    _print_summary(batch)
    print(f"\n  Total: {len(batch)} arquivo(s) a processar.")

    try:
        resp = input("\nDeseja processar esses arquivos com os metadados acima? (S/n): ").strip().lower()
    except KeyboardInterrupt:
        print("\n\nCancelado.")
        sys.exit(0)

    if resp in ("n", "não", "nao"):
        print("Lote cancelado. Nenhum arquivo foi processado.")
        sys.exit(0)

    # ── Fase 3: renomeação física ─────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  Renomeando arquivos...")
    print(f"{'=' * 70}")

    # renamed: List[(original_filename, final_filename, meta)]
    renamed = _rename_batch(batch, pdf_dir)

    # ── Fase 4: indexação ─────────────────────────────────────────────────
    # Importado aqui para não inicializar FAISS/modelos se o usuário cancelar
    from app.core.dependencies import get_ingest_use_case

    print(f"\n{'=' * 70}")
    print("  Iniciando indexação...")
    print(f"{'=' * 70}")

    ingest = get_ingest_use_case()
    total_chunks = 0
    processed = 0
    errors: List[Tuple[str, str]] = []

    for i, (original_filename, final_filename, meta) in enumerate(renamed, 1):
        pdf_path = os.path.join(pdf_dir, final_filename)
        try:
            print(f"\n  [{i}/{len(renamed)}] {final_filename} ... ", end="", flush=True)
            chunks = ingest.execute(pdf_path, meta, source_name=final_filename)
            print(f"OK — {chunks} chunk(s).")
            total_chunks += chunks
            processed += 1
        except KeyboardInterrupt:
            print("\n\nInterrompido durante o processamento.")
            break
        except Exception as exc:
            print(f"ERRO: {exc}")
            errors.append((final_filename, str(exc)))

    # ── Relatório final ───────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  Concluído: {processed}/{len(renamed)} documento(s), {total_chunks} chunk(s) adicionados.")
    if errors:
        print(f"\n  Falhas ({len(errors)}):")
        for fname, err in errors:
            print(f"    - {fname}: {err}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
