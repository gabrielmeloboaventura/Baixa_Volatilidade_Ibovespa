# graficos.py
# Gera os gráficos com matplotlib. Cada função salva um PNG em resultados/ e devolve a figura.
# As cores seguem a entidade: a carteira, o Ibovespa e o CDI têm sempre a mesma cor.

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from config import PASTA_RESULTADOS

COR_CARTEIRA = "#2A6F97"
COR_IBOVESPA = "#C8553D"
COR_CDI = "#6B7280"
COR_POSITIVA = "#2A6F97"
COR_NEGATIVA = "#C8553D"
CORES = {"Low Volatility": COR_CARTEIRA, "Ibovespa": COR_IBOVESPA, "CDI": COR_CDI}
CORES_TOP = {"Top 5": "#89C2D9", "Top 10": COR_CARTEIRA, "Top 15": "#013A63"}

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "font.size": 10, "axes.titlesize": 13,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": "#E5E7EB", "grid.linewidth": 0.8,
    "axes.axisbelow": True, "axes.edgecolor": "#9CA3AF", "legend.frameon": False,
})

FORMATO_PCT = mticker.PercentFormatter(xmax=1, decimals=0)


def _salvar(figura, nome):
    PASTA_RESULTADOS.mkdir(exist_ok=True)
    figura.tight_layout()
    figura.savefig(PASTA_RESULTADOS / nome, bbox_inches="tight", facecolor="white")
    return figura


def _reais(valor, _posicao):
    return f"R$ {valor / 1000:,.0f} mil".replace(",", ".")


def _pct(valor, casas=1):
    return f"{valor * 100:.{casas}f}%".replace(".", ",")


def _rotular_final(eixo, serie, cor, texto, deslocamento=0):
    eixo.annotate(texto, xy=(serie.index[-1], serie.iloc[-1]), xytext=(6, deslocamento),
                  textcoords="offset points", va="center", fontsize=9, color="#1F2937",
                  annotation_clip=False)
    eixo.plot(serie.index[-1], serie.iloc[-1], "o", color=cor, markersize=5)


def grafico_evolucao(valores):
    figura, eixo = plt.subplots(figsize=(10, 5))
    for coluna in valores.columns:
        eixo.plot(valores.index, valores[coluna], color=CORES[coluna], linewidth=2, label=coluna)
        # Ibovespa e CDI terminam próximos: os rótulos são afastados para não colidir.
        _rotular_final(eixo, valores[coluna], CORES[coluna], coluna, {"Ibovespa": 5, "CDI": -5}.get(coluna, 0))
    eixo.axhline(valores.iloc[0, 0], color="#9CA3AF", linewidth=1, linestyle=":")
    eixo.yaxis.set_major_formatter(mticker.FuncFormatter(_reais))
    eixo.set_title("Gráfico 1: Evolução de R$ 100.000 investidos em 28/03/2024")
    eixo.set_ylabel("Valor do investimento")
    eixo.set_xlabel("Data")
    eixo.legend(loc="upper left")
    return _salvar(figura, "grafico_1_evolucao.png")


def grafico_ranking(ranking_top):
    dados = ranking_top.sort_values("vol_252", ascending=False)
    figura, eixo = plt.subplots(figsize=(10, 5))
    barras = eixo.barh(dados["ticker"], dados["vol_252"], color=COR_CARTEIRA, height=0.65)
    for barra, valor in zip(barras, dados["vol_252"]):
        eixo.text(valor + 0.002, barra.get_y() + barra.get_height() / 2, _pct(valor), va="center", fontsize=9)
    eixo.xaxis.set_major_formatter(FORMATO_PCT)
    eixo.set_xlim(0, dados["vol_252"].max() * 1.15)
    eixo.grid(axis="y", visible=False)
    eixo.set_title("Gráfico 2: Empresas selecionadas e volatilidade histórica de 252 pregões")
    eixo.set_xlabel("Volatilidade anualizada até 27/03/2024")
    eixo.set_ylabel("Ticker")
    return _salvar(figura, "grafico_2_ranking.png")


def _barras_comparacao(serie, titulo, rotulo_y, nome, casas=1):
    figura, eixo = plt.subplots(figsize=(8, 4.5))
    cores = [CORES[item] for item in serie.index]
    barras = eixo.bar(serie.index, serie.values, color=cores, width=0.55)
    for barra, valor in zip(barras, serie.values):
        eixo.annotate(_pct(valor, casas), xy=(barra.get_x() + barra.get_width() / 2, valor),
                      xytext=(0, 4), textcoords="offset points", ha="center", fontsize=10)
    eixo.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    eixo.yaxis.set_major_formatter(FORMATO_PCT)
    eixo.grid(axis="x", visible=False)
    eixo.set_title(titulo)
    eixo.set_ylabel(rotulo_y)
    eixo.set_xlabel("Alternativa de investimento")
    return _salvar(figura, nome)


def grafico_retorno(indicadores):
    return _barras_comparacao(indicadores["retorno_acumulado"],
                              "Gráfico 3: Retorno acumulado de 28/03/2024 a 01/07/2026",
                              "Retorno acumulado", "grafico_3_retorno.png")


def grafico_volatilidade(indicadores):
    return _barras_comparacao(indicadores["volatilidade_anualizada"],
                              "Gráfico 4: Volatilidade anualizada realizada no backtest",
                              "Volatilidade anualizada", "grafico_4_volatilidade.png")


def grafico_drawdown(drawdowns):
    figura, eixo = plt.subplots(figsize=(10, 4.5))
    for coluna in drawdowns.columns:
        eixo.plot(drawdowns.index, drawdowns[coluna], color=CORES[coluna], linewidth=2, label=coluna)
    eixo.yaxis.set_major_formatter(FORMATO_PCT)
    eixo.set_title("Gráfico 5: Queda em relação ao máximo anterior")
    eixo.set_ylabel("Drawdown")
    eixo.set_xlabel("Data")
    eixo.legend(loc="lower right")
    return _salvar(figura, "grafico_5_drawdown.png")


def grafico_contribuicao(contribuicao):
    dados = contribuicao.sort_values("contribuicao")
    figura, eixo = plt.subplots(figsize=(10, 5))
    cores = [COR_POSITIVA if valor >= 0 else COR_NEGATIVA for valor in dados["contribuicao"]]
    barras = eixo.barh(dados["ticker"], dados["contribuicao"], color=cores, height=0.65)
    limite = dados["contribuicao"].abs().max()
    for barra, valor in zip(barras, dados["contribuicao"]):
        lado = limite * 0.015 if valor >= 0 else -limite * 0.015
        eixo.text(valor + lado, barra.get_y() + barra.get_height() / 2, f"{valor * 100:+.1f}".replace(".", ",") + " p.p.",
                  va="center", ha="left" if valor >= 0 else "right", fontsize=9)
    eixo.axvline(0, color="#6B7280", linewidth=1)
    eixo.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v * 100:.0f} p.p."))
    eixo.set_xlim(min(0, dados["contribuicao"].min()) - limite * 0.05, limite * 1.18)
    eixo.grid(axis="y", visible=False)
    eixo.set_title("Gráfico 6: Contribuição de cada ação para o retorno da carteira")
    eixo.set_xlabel("Contribuição em pontos percentuais do capital inicial")
    eixo.set_ylabel("Ticker")
    return _salvar(figura, "grafico_6_contribuicao.png")


def grafico_sensibilidade(sensibilidade):
    medidas = [("retorno_acumulado", "Retorno acumulado"), ("volatilidade_anualizada", "Volatilidade anualizada"),
               ("maximo_drawdown", "Máximo drawdown"), ("sharpe", "Sharpe")]
    figura, eixos = plt.subplots(1, 4, figsize=(13, 4))
    for eixo, (coluna, nome) in zip(eixos, medidas):
        valores = sensibilidade[coluna]
        barras = eixo.bar(valores.index, valores.values, color=[CORES_TOP[i] for i in valores.index], width=0.6)
        for barra, valor in zip(barras, valores.values):
            texto = f"{valor:.2f}".replace(".", ",") if coluna == "sharpe" else _pct(valor)
            eixo.annotate(texto, xy=(barra.get_x() + barra.get_width() / 2, valor),
                          xytext=(0, 4 if valor >= 0 else -12), textcoords="offset points", ha="center", fontsize=9)
        eixo.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5, steps=[1, 2, 5, 10]))
        if coluna != "sharpe":
            eixo.yaxis.set_major_formatter(FORMATO_PCT)
        else:
            eixo.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
        eixo.margins(y=0.15)
        eixo.grid(axis="x", visible=False)
        eixo.set_title(nome, fontsize=10)
        eixo.set_xlabel("Carteira")
    figura.suptitle("Gráfico 7: Sensibilidade à quantidade de ações", x=0.01, ha="left", fontweight="bold", fontsize=13)
    return _salvar(figura, "grafico_7_sensibilidade.png")


def grafico_volatilidade_movel(volatilidade_movel):
    figura, eixo = plt.subplots(figsize=(10, 4.5))
    for coluna in volatilidade_movel.columns:
        eixo.plot(volatilidade_movel.index, volatilidade_movel[coluna], color=CORES[coluna], linewidth=2, label=coluna)
    eixo.yaxis.set_major_formatter(FORMATO_PCT)
    eixo.set_ylim(bottom=0)
    eixo.set_title("Gráfico 8: Volatilidade móvel de 63 pregões")
    eixo.set_ylabel("Volatilidade anualizada")
    eixo.set_xlabel("Data")
    eixo.legend(loc="upper right")
    return _salvar(figura, "grafico_8_volatilidade_movel.png")
