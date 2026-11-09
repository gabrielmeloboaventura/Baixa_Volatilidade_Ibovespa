# config.py
# Todos os parâmetros do estudo ficam aqui, em um só lugar.
# Eles foram definidos antes de observar qualquer retorno posterior à seleção
# e não devem ser alterados depois de ver os resultados.

from pathlib import Path

import pandas as pd

# Pastas do projeto
PASTA_PROJETO = Path(__file__).resolve().parent  # pasta preparacao_dados
PASTA_DADOS = PASTA_PROJETO / "dados"
PASTA_BRUTOS = PASTA_DADOS / "brutos"

# Datas do estudo
INICIO_HISTORICO = pd.Timestamp("2023-01-02")  # início do histórico usado na seleção
DATA_SELECAO = pd.Timestamp("2024-03-27")      # último dado permitido na seleção
DATA_COMPRA = pd.Timestamp("2024-03-28")       # compra simulada no fechamento
DATA_FINAL = pd.Timestamp("2026-07-01")        # avaliação final a mercado

# Volatilidade
PREGOES_POR_ANO = 252
JANELA_PRINCIPAL = 252     # ranking usa só esta janela
JANELAS_COMPLEMENTARES = [63, 126]

# Filtros de elegibilidade (escolhas metodológicas, justificadas no relatório)
LIQUIDEZ_MINIMA = 5_000_000       # R$ por dia, média dos últimos 63 pregões
JANELA_LIQUIDEZ = 63              # pregões
PRESENCA_MINIMA = 0.95            # negociação em pelo menos 95% dos 63 pregões
SALTO_MAXIMO_DIARIO = 0.40        # |retorno ajustado| acima disso indica evento não ajustado

# Carteira
QUANTIDADE_PRINCIPAL = 10
QUANTIDADES_SENSIBILIDADE = [5, 10, 15]
CAPITAL_INICIAL = 100_000.0
CUSTO_ENTRADA = 0.0010            # 0,10% sobre o valor comprado (cenário complementar)

# Tolerância para dizer que o fechamento do provedor difere do oficial (R$ 0,01 de
# arredondamento mais 0,1% do preço)
TOLERANCIA_FECHAMENTO = 0.001
