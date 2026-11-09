# Fator Baixa Volatilidade na B3

Trabalho de programação: seleciona as 10 ações do Ibovespa de março de 2024 com menor volatilidade de 252 pregões, simula buy and hold de 28/03/2024 a 01/07/2026 e compara com Ibovespa e CDI.

## Como rodar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python inicio.py     # gera resultados/
.venv/bin/python testes.py     # verificações
```

No VS Code: abra `inicio.py`, escolha o Python de `.venv` e use **Run Cell** nas células `# %%`. As tabelas e os gráficos aparecem na janela interativa.

O relatório fica em `resultados/relatorio.html`. Os dados baixados estão em `dados/brutos/`, então o programa roda sem internet.

## Arquivos

| Arquivo | Função |
|---|---|
| `inicio.py` | Programa principal, em células |
| `config.py` | Datas e parâmetros |
| `coleta.py` | Busca os dados nas fontes |
| `calculos.py` | Volatilidade, filtros, ranking, carteira e indicadores |
| `graficos.py` | Gráficos |
| `relatorio.py` | Relatório HTML |
| `testes.py` | Testes sintéticos, conferência dos dados reais e execução no Jupyter |
| `dados/correcoes_proventos.csv` | Proventos corrigidos, com fonte e motivo |
| `dados/proventos_complementares.csv` | Proventos dos ativos sem provedor |

## Chave da brapi (opcional)

Copie `.env.example` para `.env` e preencha `BRAPI_TOKEN`. Só o plano Pro libera o histórico completo. Para refazer a coleta, apague os arquivos `brapi_*.csv` de `dados/brutos/`. Os números podem mudar um pouco.
