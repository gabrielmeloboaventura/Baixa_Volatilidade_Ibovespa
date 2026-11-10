# Fator Baixa Volatilidade no Ibovespa

Trabalho de programação sobre Factor Investing. O programa escolhe as 10 ações do Ibovespa (carteira de jan-abr/2024) com menor volatilidade histórica, usando só dados até 27/03/2024. Depois simula a compra de R$ 100.000 em 28/03/2024, com pesos iguais, e mantém até 01/07/2026 (buy and hold). O resultado é comparado com o Ibovespa e o CDI.

## Como rodar

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy matplotlib
.venv/bin/python baixa_volatilidade.py
```

No VS Code, também dá para abrir `baixa_volatilidade.py` e rodar célula por célula (**Run Cell**).

Os gráficos e as tabelas são salvos em `resultados/`.

## Carteira do grupo

O arquivo `carteira_grupo.py` junta as 10 ações de cada um dos quatro fatores do grupo (Baixa Volatilidade, Valor, Momentum e Qualidade) em uma carteira única: R$ 25.000 por fator e R$ 2.500 por ação, somando quando a mesma ação aparece em mais de um fator. A carteira é comprada em 28/03/2024, mantida até 01/07/2026 e comparada com o Ibovespa e o CDI. Os resultados ficam em `resultados_grupo/`.

```bash
.venv/bin/python carteira_grupo.py
```

Repositórios dos outros fatores:
- Valor: https://github.com/nelep-e/fator-valor-ibovespa
- Momentum: https://github.com/LeonardoMedeirosA/Momentum_Ibovespa
- Qualidade: https://github.com/GustavodaCosta0502/P2---Laerte

## Arquivos

| Arquivo | O que é |
|---|---|
| `baixa_volatilidade.py` | **O programa.** Volatilidade, filtros, ranking, carteira, indicadores e gráficos |
| `carteira_grupo.py` | Carteira única do grupo com os quatro fatores |
| `resultados_grupo/` | Gráficos e tabelas da carteira do grupo |
| `dados/` | Dados prontos para uso: universo, preços ajustados, volume, CDI e Ibovespa |
| `resultados/` | Gráficos e tabelas gerados pelo programa |
| `preparacao_dados/` | Como os dados de `dados/` foram coletados e corrigidos. Não precisa rodar |

## De onde vêm os dados

- **Composição do Ibovespa de jan-abr/2024:** B3.
- **Fechamento e volume financeiro:** arquivo oficial de cotações da B3 (COTAHIST).
- **Proventos e desdobramentos:** brapi (PETR4, VALE3, ITUB4 e MGLU3) e Yahoo Finance, com correções conferidas na Fundamentus. Cada correção está em `preparacao_dados/dados/correcoes_proventos.csv`, com a fonte.
- **CDI:** Banco Central, série SGS 12.
- **Ibovespa:** B3.

A preparação ficou separada porque o Yahoo tinha preços e proventos errados, e corrigir isso exige bastante código. Para refazer a coleta, rode `python preparacao_dados/gerar_dados.py`. Isso exige `requests`, `yfinance` e `python-dotenv`.
