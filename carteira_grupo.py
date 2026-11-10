"""
Carteira do grupo: junta as 10 melhores ações de cada fator em uma carteira única
e compara com o Ibovespa e o CDI, de 28/03/2024 a 01/07/2026.

Fatores (cada um escolhido no seu próprio código, com dados até 27/03/2024):
  Baixa Volatilidade  github.com/gabrielmeloboaventura/Baixa_Volatilidade_Ibovespa
  Valor               github.com/nelep-e/fator-valor-ibovespa
  Momentum            github.com/LeonardoMedeirosA/Momentum_Ibovespa
  Qualidade           github.com/GustavodaCosta0502/P2---Laerte

Regra de divisão (definida antes de ver o resultado):
  R$ 100.000 no total, R$ 25.000 por fator e R$ 2.500 por ação dentro de cada fator.
  Uma ação escolhida por mais de um fator recebe a soma (ex.: PETR4 em 3 fatores = R$ 7.500).
  Buy and hold: compra no fechamento de 28/03/2024, sem rebalanceamento até 01/07/2026.

Os preços são os mesmos da pasta dados/ (preço ajustado por proventos e eventos, com os
códigos de 2024). Rodar: python carteira_grupo.py
"""

# %% Configuração
import sys
from pathlib import Path

import matplotlib

NO_JUPYTER = "ipykernel" in sys.modules
if not NO_JUPYTER:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

DATA_COMPRA = "2024-03-28"
DATA_FINAL = "2026-07-01"
CAPITAL = 100_000

# As 10 ações de cada fator, com os códigos de 2024 (ISAE4 era TRPL4 em 2024)
FATORES = {
    "Baixa Volatilidade": ["TAEE11", "EGIE3", "BBSE3", "ITSA4", "ABEV3", "CPFE3", "ITUB4", "VIVT3", "EQTL3", "CPLE6"],
    "Valor": ["GOAU4", "ALOS3", "GGBR4", "PETR4", "BRAP4", "BBAS3", "CMIG4", "TRPL4", "VALE3", "BBDC4"],
    "Momentum": ["YDUQ3", "BRFS3", "PETR4", "UGPA3", "IRBR3", "VBBR3", "BPAC11", "CYRE3", "HAPV3", "BBAS3"],
    "Qualidade": ["PRIO3", "RECV3", "WEGE3", "GOAU4", "GGBR4", "PETR4", "KLBN11", "ABEV3", "SUZB3", "TOTS3"],
}
POR_FATOR = CAPITAL / len(FATORES)   # R$ 25.000

PASTA = Path(__file__).parent if "__file__" in globals() else Path.cwd()
SAIDA = PASTA / "resultados_grupo"
SAIDA.mkdir(exist_ok=True)
pd.set_option("display.width", 160, "display.max_columns", 20, "display.float_format", "{:,.4f}".format)

# %% 1. Dados
universo = pd.read_csv(PASTA / "dados/universo.csv", index_col="ticker")
precos = pd.read_csv(PASTA / "dados/precos_ajustados.csv", index_col="data", parse_dates=True)
cdi = pd.read_csv(PASTA / "dados/cdi.csv", index_col="data", parse_dates=True)["cdi"]
ibovespa = pd.read_csv(PASTA / "dados/ibovespa.csv", index_col="data", parse_dates=True)["ibovespa"]

periodo = precos.loc[DATA_COMPRA:DATA_FINAL].ffill()   # dia sem negócio mantém o último preço
datas = periodo.index

# %% 2. Composição: quanto vai para cada ação
alocacao = pd.DataFrame([(fator, t, POR_FATOR / len(acoes)) for fator, acoes in FATORES.items() for t in acoes],
                        columns=["fator", "ticker", "valor"])
composicao = alocacao.groupby("ticker").agg(valor_inicial=("valor", "sum"),
                                            fatores=("fator", lambda f: ", ".join(f)))
composicao.insert(0, "empresa", universo.loc[composicao.index, "empresa"])
composicao = composicao.sort_values(["valor_inicial", "fatores"], ascending=[False, True])
print(f"{len(composicao)} ações diferentes; total investido R$ {composicao['valor_inicial'].sum():,.2f}")
print(composicao[composicao["valor_inicial"] > POR_FATOR / 10])   # as que aparecem em mais de um fator

# %% 3. Buy and hold
quantidades = composicao["valor_inicial"] / periodo[composicao.index].iloc[0]   # fixas até o fim
posicoes = periodo[composicao.index] * quantidades

# Parte de cada fator dentro da carteira (R$ 25.000 iniciais cada)
por_fator = pd.DataFrame({fator: (periodo[acoes] * (POR_FATOR / len(acoes)) / periodo[acoes].iloc[0]).sum(axis=1)
                          for fator, acoes in FATORES.items()})

# CDI: a taxa de um dia rende até o dia útil seguinte (por isso o shift)
fator_cdi = (1 + cdi).cumprod().shift(1)
fator_cdi = fator_cdi.reindex(fator_cdi.index.union(datas)).ffill().reindex(datas)

valores = pd.DataFrame({
    "Carteira do grupo": posicoes.sum(axis=1),
    "Ibovespa": CAPITAL * ibovespa.reindex(datas) / ibovespa.reindex(datas).iloc[0],
    "CDI": CAPITAL * fator_cdi / fator_cdi.iloc[0],
})
retorno_cdi = valores["CDI"].pct_change()


# %% 4. Indicadores
def maximo_drawdown(valor):
    return (valor / valor.cummax() - 1).min()


def indicadores(valor):
    r = valor.pct_change().dropna()
    total = valor.iloc[-1] / valor.iloc[0] - 1
    return pd.Series({
        "valor_final": valor.iloc[-1] * CAPITAL / valor.iloc[0],   # escala para R$ 100.000
        "retorno_acumulado": total,
        "retorno_anualizado": (1 + total) ** (252 / len(r)) - 1,
        "volatilidade": r.std(ddof=1) * np.sqrt(252),
        "max_drawdown": maximo_drawdown(valor),
        "sharpe": (r - retorno_cdi).mean() / r.std(ddof=1) * np.sqrt(252),
    })


resultado = valores.apply(indicadores).T
resultado.loc["CDI", "sharpe"] = np.nan
fatores_individuais = por_fator.apply(indicadores).T   # cada fator sozinho, como se tivesse R$ 100.000

fins_de_ano = valores.groupby(valores.index.year).last()
por_ano = pd.concat([fins_de_ano.iloc[[0]] / valores.iloc[0] - 1, fins_de_ano.pct_change().iloc[1:]])

print("\nResultados de 28/03/2024 a 01/07/2026 (sem impostos):")
print(resultado)
print("\nCada fator sozinho (mesmos dados, R$ 100.000):")
print(fatores_individuais)
print("\nRentabilidade por ano (2024 e 2026 são parciais):")
print(por_ano)

# %% 5. Contribuição por fator e por ação
contrib_fator = pd.DataFrame({"valor_inicial": por_fator.iloc[0], "valor_final": por_fator.iloc[-1]})
contrib_fator["retorno"] = contrib_fator["valor_final"] / contrib_fator["valor_inicial"] - 1
contrib_fator["contribuicao"] = (contrib_fator["valor_final"] - contrib_fator["valor_inicial"]) / CAPITAL

contrib_acao = composicao.copy()
contrib_acao["valor_final"] = posicoes.iloc[-1]
contrib_acao["retorno"] = contrib_acao["valor_final"] / contrib_acao["valor_inicial"] - 1
contrib_acao["contribuicao"] = (contrib_acao["valor_final"] - contrib_acao["valor_inicial"]) / CAPITAL
contrib_acao = contrib_acao.sort_values("contribuicao", ascending=False)

print("\nContribuição de cada fator (a soma é o retorno da carteira):")
print(contrib_fator)
print("\nContribuição de cada ação:")
print(contrib_acao)

# %% 6. Gráficos
CORES = {"Carteira do grupo": "#1F4E79", "Ibovespa": "#C8553D", "CDI": "#6B7280",
         "Baixa Volatilidade": "#2A6F97", "Valor": "#B07D2B", "Momentum": "#2E7D5B", "Qualidade": "#7A4E9C"}
PCT = mticker.PercentFormatter(1, decimals=0)
REAIS = mticker.FuncFormatter(lambda v, _: f"R$ {v:,.0f}".replace(",", "."))
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": "#E5E7EB", "axes.axisbelow": True, "axes.titleweight": "bold", "axes.titlelocation": "left"})


def finalizar(figura, nome):
    figura.tight_layout()
    figura.savefig(SAIDA / nome, dpi=200, facecolor="white")
    plt.show() if NO_JUPYTER else plt.close(figura)


figura, eixo = plt.subplots(figsize=(10, 5))
for nome in valores:
    eixo.plot(valores.index, valores[nome], color=CORES[nome], lw=2.4 if nome == "Carteira do grupo" else 1.8, label=nome)
eixo.yaxis.set_major_formatter(REAIS)
eixo.set(title="Carteira do grupo: evolução de R$ 100.000 investidos em 28/03/2024", xlabel="Data", ylabel="Valor do investimento")
eixo.legend()
finalizar(figura, "1_evolucao_grupo.png")

figura, eixo = plt.subplots(figsize=(10, 5))
for nome in FATORES:
    eixo.plot(por_fator.index, por_fator[nome] * CAPITAL / POR_FATOR, color=CORES[nome], lw=1.8, label=nome)
eixo.plot(valores.index, valores["Ibovespa"], color=CORES["Ibovespa"], lw=1.6, ls="--", label="Ibovespa")
eixo.yaxis.set_major_formatter(REAIS)
eixo.set(title="Cada fator separado: evolução de R$ 100.000", xlabel="Data", ylabel="Valor do investimento")
eixo.legend(ncol=3)
finalizar(figura, "2_evolucao_fatores.png")

figura, eixo = plt.subplots(figsize=(8, 4.5))
eixo.bar(contrib_fator.index, contrib_fator["contribuicao"] * 100, color=[CORES[f] for f in contrib_fator.index], width=0.55)
for x, y in zip(contrib_fator.index, contrib_fator["contribuicao"] * 100):
    eixo.annotate(f"{y:+.1f}".replace(".", ",") + " p.p.", (x, y), xytext=(0, 4 if y >= 0 else -12), textcoords="offset points", ha="center")
eixo.axhline(0, color="#6B7280", lw=1)
eixo.grid(axis="x", visible=False)
eixo.margins(y=0.2)
eixo.set(title="Contribuição de cada fator para o retorno da carteira", ylabel="Pontos percentuais do capital inicial")
finalizar(figura, "3_contribuicao_fatores.png")

figura, eixo = plt.subplots(figsize=(10, 4.5))
for nome in ["Carteira do grupo", "Ibovespa"]:
    eixo.plot(valores.index, valores[nome] / valores[nome].cummax() - 1, color=CORES[nome], lw=2, label=nome)
eixo.yaxis.set_major_formatter(PCT)
eixo.set(title="Drawdown: queda em relação ao pico anterior", xlabel="Data", ylabel="Drawdown")
eixo.legend()
finalizar(figura, "4_drawdown_grupo.png")

# %% 7. Tabelas em CSV
composicao.to_csv(SAIDA / "composicao.csv")
valores.to_csv(SAIDA / "evolucao_investimento.csv")
resultado.to_csv(SAIDA / "indicadores.csv")
fatores_individuais.to_csv(SAIDA / "indicadores_por_fator.csv")
por_ano.to_csv(SAIDA / "rentabilidade_por_ano.csv")
contrib_fator.to_csv(SAIDA / "contribuicao_fatores.csv")
contrib_acao.to_csv(SAIDA / "contribuicao_acoes.csv")
print(f"\nGráficos e tabelas salvos em {SAIDA}")
