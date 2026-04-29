#!/bin/sh
# coverage.sh — Executa a suíte de testes com relatório de cobertura.
#
# Uso:
#   ./scripts/coverage.sh            # relatório no terminal + HTML
#   ./scripts/coverage.sh --quick    # apenas resumo no terminal (sem HTML)
#
# Saídas:
#   - htmlcov/index.html  — relatório HTML interativo
#   - .coverage           — dados brutos (SQLite)

set -e

echo "=== Help Corretor — Cobertura de Testes ==="
echo ""

if [ "$1" = "--quick" ]; then
    echo "Modo rápido: apenas resumo no terminal"
    echo ""
    python -m pytest tests/ \
        --cov=app \
        --cov-report=term-missing \
        -x
else
    echo "Modo completo: terminal + relatório HTML em htmlcov/"
    echo ""
    python -m pytest tests/ \
        --cov=app \
        --cov-report=term-missing \
        --cov-report=html
fi

echo ""
echo "=== Concluído ==="
