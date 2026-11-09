"""
Factor Investing: fator Baixa Volatilidade no Ibovespa.

Seleciona as 10 ações menos voláteis do Ibovespa (carteira de jan-abr/2024) com dados
até 27/03/2024, compra no fechamento de 28/03/2024 com pesos iguais e mantém até
01/07/2026 (buy and hold). Compara com o Ibovespa e o CDI.

Dados (pasta dados/, preparados por preparacao_dados/gerar_dados.py):
  universo.csv            ações do Ibovespa de jan-abr/2024 (B3)
  precos_ajustados.csv    preço ajustado por proventos e desdobramentos
  volume_financeiro.csv   valor negociado por dia, em reais (B3)
  cdi.csv                 CDI diário em decimal (Banco Central, série SGS 12)
  ibovespa.csv            pontos do Ibovespa (B3)

Rodar: python baixa_volatilidade.py   (ou célula a célula no VS Code, com "Run Cell")
"""

# %% Configuração
import sys
from pathlib import Path

import matplotlib

NO_JUPYTER = "ipykernel" in sys.modules
if not NO_JUPYTER:
    matplotlib.use("Agg")  # no terminal os gráficos só são salvos em arquivo

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

DATA_SELECAO = "2024-03-27"   # último dia usado para escolher as ações
DATA_COMPRA = "2024-03-28"    # compra no fechamento
DATA_FINAL = "2026-07-01"     # avaliação final
JANELA = 252                  # retornos usados na volatilidade principal
LIQUIDEZ_MINIMA = 5_000_000   # R$ por dia, média dos últimos 63 pregões
PRESENCA_MINIMA = 0.95        # negociou em pelo menos 95% desses 63 pregões
SALTO_MAXIMO = 0.40           # retorno diário acima de 40% indica evento sem ajuste
TOP_N = 10                    # ações na carteira
CAPITAL = 100_000             # R$
CUSTO = 0.001                 # 0,10% na compra (cenário complementar)

PASTA = Path(__file__).parent if "__file__" in globals() else Path.cwd()
SAIDA = PASTA / "resultados"
SAIDA.mkdir(exist_ok=True)
pd.set_option("display.width", 160, "display.max_columns", 20, "display.float_format", "{:,.4f}".format)

# %% 1. Dados
universo = pd.read_csv(PASTA / "dados/universo.csv", index_col="ticker")
precos = pd.read_csv(PASTA / "dados/precos_ajustados.csv", index_col="data", parse_dates=True)
volume = pd.read_csv(PASTA / "dados/volume_financeiro.csv", index_col="data", parse_dates=True)
cdi = pd.read_csv(PASTA / "dados/cdi.csv", index_col="data", parse_dates=True)["cdi"]
ibovespa = pd.read_csv(PASTA / "dados/ibovespa.csv", index_col="data", parse_dates=True)["ibovespa"]
print(f"Universo: {len(universo)} ações de {universo['empresa'].nunique()} empresas.")


# %% 2. Indicadores de seleção (só com dados até 27/03/2024, para evitar look-ahead bias)
def volatilidade(retornos, n):
    """Desvio-padrão amostral (ddof=1) dos últimos n retornos, anualizado por raiz de 252.
    Se faltar algum retorno na janela, devolve NaN: dado faltando não pode baixar a volatilidade."""
    ultimos = retornos.iloc[-n:]
    return (ultimos.std(ddof=1) * np.sqrt(252)).where(ultimos.notna().all())


def maximo_drawdown(valores):
    """Maior queda em relação ao pico anterior (número negativo)."""
    return (valores / valores.cummax() - 1).min()


historico = precos.loc[:DATA_SELECAO]
retornos = historico.pct_change(fill_method=None)   # dia sem negócio fica vazio, não é preenchido
volume_63 = volume.loc[:DATA_SELECAO].iloc[-63:]

tabela = universo.copy()
tabela["vol_63"] = volatilidade(retornos, 63)
tabela["vol_126"] = volatilidade(retornos, 126)
tabela["vol_252"] = volatilidade(retornos, JANELA)
tabela["max_drawdown"] = maximo_drawdown(historico.iloc[-(JANELA + 1):])
tabela["liquidez"] = volume_63.fillna(0).mean()          # R$ por dia
tabela["presenca"] = volume_63.notna().mean()             # fração dos pregões com negócio
tabela["retornos_zero"] = (retornos.iloc[-JANELA:] == 0).mean()
tabela["maior_salto"] = retornos.iloc[-JANELA:].abs().max()

# %% 3. Filtros de elegibilidade
mais_liquida = tabela["liquidez"] == tabela.groupby("empresa")["liquidez"].transform("max")
filtros = {
    "outra classe da mesma empresa é mais líquida": ~mais_liquida,
    "menos de 252 retornos válidos": tabela["vol_252"].isna(),
    "liquidez abaixo de R$ 5 milhões por dia": tabela["liquidez"] < LIQUIDEZ_MINIMA,
    "negociou em menos de 95% dos pregões": tabela["presenca"] < PRESENCA_MINIMA,
    "salto diário acima de 40%": tabela["maior_salto"] > SALTO_MAXIMO,
}
tabela["motivo_exclusao"] = ""
for motivo, reprovou in filtros.items():
    tabela.loc[reprovou, "motivo_exclusao"] += motivo + "; "
tabela["motivo_exclusao"] = tabela["motivo_exclusao"].str.rstrip("; ")
tabela["elegivel"] = tabela["motivo_exclusao"] == ""

print(f"\nExcluídas ({(~tabela['elegivel']).sum()}):")
print(tabela.loc[~tabela["elegivel"], ["empresa", "vol_252", "motivo_exclusao"]])

# %% 4. Ranking e carteira: menor volatilidade de 252 pregões primeiro
# Empate: maior liquidez, depois ordem alfabética do ticker.
ranking = (tabela[tabela["elegivel"]].reset_index()
           .sort_values(["vol_252", "liquidez", "ticker"], ascending=[True, False, True]))
ranking.insert(0, "posicao", range(1, len(ranking) + 1))
carteira = ranking["ticker"].head(TOP_N).tolist()

colunas = ["posicao", "ticker", "empresa", "setor", "vol_63", "vol_126", "vol_252", "max_drawdown", "liquidez"]
print("\nRanking (15 primeiros):")
print(ranking[colunas].head(15).to_string(index=False))
print("\nCarteira:", ", ".join(carteira))

# %% 5. Backtest buy and hold (dados depois da compra só entram aqui)
periodo = precos.loc[DATA_COMPRA:DATA_FINAL].ffill()   # dia sem negócio mantém o último preço
datas = periodo.index


def buy_and_hold(tickers, custo=0.0):
    """Compra o mesmo valor de cada ação no primeiro dia e não mexe mais.
    As quantidades são fixas (podem ser fracionárias), então os pesos mudam com os preços:
    não há rebalanceamento. Devolve o valor de cada posição em cada dia."""
    quantidades = CAPITAL / len(tickers) * (1 - custo) / periodo[tickers].iloc[0]
    return periodo[tickers] * quantidades


posicoes = buy_and_hold(carteira)

# CDI: a taxa de um dia rende até o dia útil seguinte (por isso o shift)
fator_cdi = (1 + cdi).cumprod().shift(1)
fator_cdi = fator_cdi.reindex(fator_cdi.index.union(datas)).ffill().reindex(datas)

valores = pd.DataFrame({
    "Low Volatility": posicoes.sum(axis=1),
    "Ibovespa": CAPITAL * ibovespa.reindex(datas) / ibovespa.reindex(datas).iloc[0],
    "CDI": CAPITAL * fator_cdi / fator_cdi.iloc[0],
})
retorno_cdi = valores["CDI"].pct_change()


# %% 6. Indicadores de desempenho
def indicadores(valor):
    r = valor.pct_change().dropna()
    total = valor.iloc[-1] / valor.iloc[0] - 1
    return pd.Series({
        "valor_final": valor.iloc[-1],
        "retorno_acumulado": total,
        "retorno_anualizado": (1 + total) ** (252 / len(r)) - 1,
        "volatilidade": r.std(ddof=1) * np.sqrt(252),
        "max_drawdown": maximo_drawdown(valor),
        # Sharpe = média(retorno - CDI) / desvio-padrão do retorno x raiz de 252
        "sharpe": (r - retorno_cdi).mean() / r.std(ddof=1) * np.sqrt(252),
    })


resultado = valores.apply(indicadores).T
resultado.loc["CDI", "sharpe"] = np.nan   # o CDI é a própria referência do Sharpe

fins_de_ano = valores.groupby(valores.index.year).last()
por_ano = pd.concat([fins_de_ano.iloc[[0]] / valores.iloc[0] - 1, fins_de_ano.pct_change().iloc[1:]])

lv, ib, rf = resultado.loc["Low Volatility"], resultado.loc["Ibovespa"], resultado.loc["CDI"]
valor_com_custo = buy_and_hold(carteira, CUSTO).sum(axis=1).iloc[-1]

print("\nResultados de 28/03/2024 a 01/07/2026 (sem impostos):")
print(resultado)
print("\nRentabilidade por ano (2024 e 2026 são parciais):")
print(por_ano)
print(f"\nVolatilidade da carteira menos a do Ibovespa: {(lv['volatilidade'] - ib['volatilidade']) * 100:+.2f} p.p. "
      f"({lv['volatilidade'] / ib['volatilidade'] - 1:+.1%})")
print(f"Retorno da carteira menos o do Ibovespa: {(lv['retorno_acumulado'] - ib['retorno_acumulado']) * 100:+.2f} p.p.")
print(f"Retorno da carteira menos o do CDI: {(lv['retorno_acumulado'] - rf['retorno_acumulado']) * 100:+.2f} p.p.")
print(f"Valor final com custo de 0,10% na compra: R$ {valor_com_custo:,.2f}")

# %% 7. Contribuição de cada ação
contribuicao = pd.DataFrame({"empresa": universo.loc[carteira, "empresa"],
                             "vol_252": tabela.loc[carteira, "vol_252"],
                             "valor_inicial": posicoes.iloc[0],
                             "valor_final": posicoes.iloc[-1]})
contribuicao["retorno"] = contribuicao["valor_final"] / contribuicao["valor_inicial"] - 1
contribuicao["contribuicao"] = (contribuicao["valor_final"] - contribuicao["valor_inicial"]) / CAPITAL
contribuicao["peso_final"] = contribuicao["valor_final"] / contribuicao["valor_final"].sum()
contribuicao = contribuicao.sort_values("contribuicao", ascending=False)
print("\nContribuição (a soma é o retorno da carteira):")
print(contribuicao)

# %% 8. Sensibilidade: Top 5, Top 10 e Top 15 do mesmo ranking
sensibilidade = pd.DataFrame({f"Top {n}": indicadores(buy_and_hold(ranking["ticker"].head(n).tolist()).sum(axis=1))
                              for n in (5, 10, 15)}).T
print("\nSensibilidade à quantidade de ações:")
print(sensibilidade)

# %% 9. Gráficos
CORES = {"Low Volatility": "#2A6F97", "Ibovespa": "#C8553D", "CDI": "#6B7280"}
PCT = mticker.PercentFormatter(1, decimals=0)
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#E5E7EB", "axes.axisbelow": True, "axes.titleweight": "bold", "axes.titlelocation": "left"})


def finalizar(figura, nome):
    figura.tight_layout()
    figura.savefig(SAIDA / nome, dpi=200, facecolor="white")
    plt.show() if NO_JUPYTER else plt.close(figura)


def barras(eixo, serie, cores, formato="{:.1%}"):
    eixo.bar(serie.index, serie.values, color=cores, width=0.55)
    for x, y in zip(serie.index, serie.values):
        eixo.annotate(formato.format(y).replace(".", ","), (x, y), xytext=(0, 4 if y >= 0 else -12),
                      textcoords="offset points", ha="center")
    eixo.grid(axis="x", visible=False)
    eixo.margins(y=0.15)


figura, eixo = plt.subplots(figsize=(10, 5))
for nome in valores:
    eixo.plot(valores.index, valores[nome], color=CORES[nome], lw=2, label=nome)
eixo.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R$ {v:,.0f}".replace(",", ".")))
eixo.set(title="Evolução de R$ 100.000 investidos em 28/03/2024", xlabel="Data", ylabel="Valor do investimento")
eixo.legend()
finalizar(figura, "1_evolucao.png")

figura, eixo = plt.subplots(figsize=(9, 5))
selecao = ranking.head(TOP_N).iloc[::-1]
eixo.barh(selecao["ticker"], selecao["vol_252"], color=CORES["Low Volatility"])
eixo.xaxis.set_major_formatter(PCT)
eixo.set(title="Volatilidade de 252 pregões das ações selecionadas", xlabel="Volatilidade anualizada até 27/03/2024")
finalizar(figura, "2_ranking_volatilidade.png")

for coluna, titulo, arquivo in [("retorno_acumulado", "Retorno acumulado no período", "3_retorno.png"),
                                ("volatilidade", "Volatilidade anualizada no período", "4_volatilidade.png")]:
    figura, eixo = plt.subplots(figsize=(7, 4.5))
    barras(eixo, resultado[coluna], [CORES[n] for n in resultado.index])
    eixo.yaxis.set_major_formatter(PCT)
    eixo.set(title=titulo)
    finalizar(figura, arquivo)

figura, eixo = plt.subplots(figsize=(10, 4.5))
for nome in ["Low Volatility", "Ibovespa"]:
    eixo.plot(valores.index, valores[nome] / valores[nome].cummax() - 1, color=CORES[nome], lw=2, label=nome)
eixo.yaxis.set_major_formatter(PCT)
eixo.set(title="Drawdown: queda em relação ao pico anterior", xlabel="Data", ylabel="Drawdown")
eixo.legend()
finalizar(figura, "5_drawdown.png")

figura, eixo = plt.subplots(figsize=(9, 5))
ordem = contribuicao.iloc[::-1]
eixo.barh(ordem.index, ordem["contribuicao"] * 100,
          color=[CORES["Low Volatility"] if c >= 0 else CORES["Ibovespa"] for c in ordem["contribuicao"]])
eixo.set(title="Contribuição de cada ação para o retorno da carteira", xlabel="Pontos percentuais do capital inicial")
finalizar(figura, "6_contribuicao.png")

figura, eixos = plt.subplots(1, 4, figsize=(14, 4))
for eixo, (coluna, titulo) in zip(eixos, [("retorno_acumulado", "Retorno"), ("volatilidade", "Volatilidade"),
                                          ("max_drawdown", "Máximo drawdown"), ("sharpe", "Sharpe")]):
    barras(eixo, sensibilidade[coluna], ["#89C2D9", "#2A6F97", "#013A63"], "{:.2f}" if coluna == "sharpe" else "{:.1%}")
    if coluna != "sharpe":
        eixo.yaxis.set_major_formatter(PCT)
    eixo.set_title(titulo)
figura.suptitle("Sensibilidade: Top 5, Top 10 e Top 15", x=0.01, ha="left", fontweight="bold")
finalizar(figura, "7_sensibilidade.png")

# %% 10. Tabelas em CSV
tabela.to_csv(SAIDA / "elegibilidade.csv")
ranking.to_csv(SAIDA / "ranking.csv", index=False)
valores.to_csv(SAIDA / "evolucao_investimento.csv")
resultado.to_csv(SAIDA / "indicadores.csv")
por_ano.to_csv(SAIDA / "rentabilidade_por_ano.csv")
contribuicao.to_csv(SAIDA / "contribuicao.csv")
sensibilidade.to_csv(SAIDA / "sensibilidade.csv")
print(f"\nGráficos e tabelas salvos em {SAIDA}")
