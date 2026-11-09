# inicio.py
# Factor Investing: fator Baixa Volatilidade em ações da B3.
#
# Pelo terminal:   python inicio.py
# No VS Code:      abra este arquivo e use "Run Cell" nas células marcadas com # %%
#
# Os dois modos salvam tabelas e gráficos em resultados/. No Jupyter as tabelas e os
# gráficos também aparecem na tela.

# %% Preparação
import sys
import warnings
from pathlib import Path

try:
    PASTA = Path(__file__).resolve().parent
except NameError:  # o Jupyter nem sempre define __file__
    PASTA = Path.cwd()
sys.path.insert(0, str(PASTA))

import matplotlib

try:
    from IPython import get_ipython
    EM_JUPYTER = get_ipython() is not None and "IPKernelApp" in get_ipython().config
except ImportError:
    EM_JUPYTER = False
if not EM_JUPYTER:
    matplotlib.use("Agg")  # no terminal os gráficos só são salvos

import matplotlib.pyplot as plt
import pandas as pd

import calculos
import coleta
import graficos
import relatorio
from config import (CAPITAL_INICIAL, CUSTO_ENTRADA, DATA_COMPRA, DATA_FINAL, DATA_SELECAO, INICIO_HISTORICO,
                    PASTA_RESULTADOS, QUANTIDADE_PRINCIPAL, QUANTIDADES_SENSIBILIDADE)

warnings.filterwarnings("ignore", category=FutureWarning)
PASTA_RESULTADOS.mkdir(exist_ok=True)
pd.set_option("display.width", 200, "display.max_columns", 30, "display.float_format", "{:,.4f}".format)


def mostrar(tabela, titulo):
    """Mostra a tabela: formatada no Jupyter, em texto no terminal."""
    print(f"\n{titulo}")
    if EM_JUPYTER:
        from IPython.display import display
        display(tabela)
    else:
        print(tabela.to_string())


def mostrar_figura(figura):
    """No Jupyter exibe a figura. Nos dois modos libera a memória depois de salvar."""
    if EM_JUPYTER:
        plt.show()
    plt.close(figura)


# %% 1. Coleta: universo histórico, cotações oficiais e benchmarks
universo = coleta.carregar_universo()
mapa = coleta.carregar_mapa_tickers()
setores = coleta.carregar_setores()
correcoes = coleta.carregar_correcoes_proventos()
complementares = coleta.carregar_proventos_complementares()

codigos = sorted({c for texto in mapa["codigos_cotahist"] for c in texto.split(",")})
cotacoes, calendario = coleta.carregar_cotahist(codigos)
calendario = calendario[(calendario >= INICIO_HISTORICO) & (calendario <= DATA_FINAL)]
ibovespa_pontos = coleta.carregar_ibovespa()
cdi = coleta.carregar_cdi()

print(f"Universo: {len(universo)} ativos de {universo['empresa'].nunique()} empresas (carteira jan-abr/2024).")
print(f"Pregões disponíveis: {len(calendario)}, de {calendario[0]:%d/%m/%Y} a {calendario[-1]:%d/%m/%Y}.")

# %% 2. Seleção: tudo aqui usa dados só até 27/03/2024
# As séries são montadas truncadas na data de seleção, então nenhum dado futuro entra.
precos_selecao, origem = calculos.montar_precos(universo, mapa, cotacoes, calendario, correcoes,
                                                complementares, DATA_SELECAO)
datas_selecao = calendario[calendario <= DATA_SELECAO]
volume_selecao = pd.DataFrame({t: calculos.fechamento_oficial(t, mapa, cotacoes, datas_selecao)["volume_financeiro"]
                               for t in universo["ticker"]})

indicadores = calculos.indicadores_formacao(precos_selecao, volume_selecao, universo, setores)
elegibilidade = calculos.aplicar_filtros(indicadores)
ranking = calculos.montar_ranking(elegibilidade)
selecionadas = ranking.head(QUANTIDADE_PRINCIPAL)
tickers = selecionadas["ticker"].tolist()

origem.to_csv(PASTA_RESULTADOS / "origem_dados.csv", index=False)
elegibilidade.to_csv(PASTA_RESULTADOS / "elegibilidade.csv", index=False)
ranking.to_csv(PASTA_RESULTADOS / "ranking.csv", index=False)

colunas_ranking = ["posicao", "empresa", "ticker", "setor", "vol_63", "vol_126", "vol_252",
                   "max_drawdown_hist", "liquidez_media_63"]
mostrar(elegibilidade.loc[~elegibilidade["elegivel"], ["ticker", "empresa", "vol_252", "motivo_exclusao"]],
        f"Ativos excluídos ({(~elegibilidade['elegivel']).sum()} de {len(elegibilidade)}):")
mostrar(ranking[colunas_ranking].head(20), "Ranking (20 menores volatilidades de 252 pregões):")
print("\nCarteira principal:", ", ".join(tickers))
print("Motivo da escolha: são os 10 ativos elegíveis de menor volatilidade de 252 pregões em 27/03/2024.")

# %% 3. Backtest: dados posteriores à formação entram só a partir daqui
precos_completos, _ = calculos.montar_precos(universo, mapa, cotacoes, calendario, correcoes,
                                             complementares, DATA_FINAL)
precos_backtest = precos_completos.loc[DATA_COMPRA:DATA_FINAL]
datas = precos_backtest.index

posicoes, quantidades = calculos.simular_buy_and_hold(precos_backtest, tickers)
carteira = posicoes.sum(axis=1)
ibovespa = ibovespa_pontos.reindex(datas)
if ibovespa.isna().any():
    raise ValueError("Falta valor do Ibovespa em pregões do backtest.")
fator = calculos.fator_cdi(cdi, datas)

valores = pd.DataFrame({"Low Volatility": carteira,
                        "Ibovespa": CAPITAL_INICIAL * ibovespa / ibovespa.iloc[0],
                        "CDI": CAPITAL_INICIAL * fator})
retorno_cdi = fator.pct_change().dropna()

tabela_indicadores = pd.DataFrame({
    "Low Volatility": calculos.indicadores_desempenho(valores["Low Volatility"], retorno_cdi),
    "Ibovespa": calculos.indicadores_desempenho(valores["Ibovespa"], retorno_cdi),
    "CDI": calculos.indicadores_desempenho(valores["CDI"], retorno_cdi, usar_sharpe=False),
}).T
por_ano = calculos.rentabilidade_por_ano(valores)

vol_carteira = tabela_indicadores.loc["Low Volatility", "volatilidade_anualizada"]
vol_ibov = tabela_indicadores.loc["Ibovespa", "volatilidade_anualizada"]
comparacao = pd.Series({
    "diferenca_volatilidade_pp": (vol_carteira - vol_ibov) * 100,
    "variacao_percentual_volatilidade": vol_carteira / vol_ibov - 1,
    "diferenca_retorno_ibov_pp": (valores["Low Volatility"].iloc[-1] - valores["Ibovespa"].iloc[-1]) / CAPITAL_INICIAL * 100,
    "diferenca_retorno_cdi_pp": (valores["Low Volatility"].iloc[-1] - valores["CDI"].iloc[-1]) / CAPITAL_INICIAL * 100,
})

mostrar(tabela_indicadores, "Indicadores do backtest:")
mostrar(por_ano, "Rentabilidade por período:")
mostrar(comparacao.to_frame("valor"), "Comparação com os benchmarks:")

# %% 4. Custo hipotético de entrada (0,10% na compra)
posicoes_custo, _ = calculos.simular_buy_and_hold(precos_backtest, tickers, custo=CUSTO_ENTRADA)
carteira_custo = posicoes_custo.sum(axis=1)
tabela_custos = pd.DataFrame({
    "valor_final": [carteira.iloc[-1], carteira_custo.iloc[-1]],
    "retorno_acumulado": [carteira.iloc[-1] / CAPITAL_INICIAL - 1, carteira_custo.iloc[-1] / CAPITAL_INICIAL - 1],
}, index=["Bruto", "Com custo de entrada de 0,10%"])
mostrar(tabela_custos, "Resultado bruto e com custo de entrada (sem impostos):")

# %% 5. Contribuição individual das 10 ações
contribuicao = calculos.contribuicao_individual(posicoes, selecionadas)
mostrar(contribuicao, "Contribuição individual:")

# %% 6. Sensibilidade: Top 5, Top 10 e Top 15 do mesmo ranking
linhas_sensibilidade = {}
for quantidade in QUANTIDADES_SENSIBILIDADE:
    if len(ranking) < quantidade:
        print(f"Top {quantidade} não calculado: só há {len(ranking)} ativos elegíveis.")
        continue
    grupo = ranking["ticker"].head(quantidade).tolist()
    valor_grupo = calculos.simular_buy_and_hold(precos_backtest, grupo)[0].sum(axis=1)
    linhas_sensibilidade[f"Top {quantidade}"] = calculos.indicadores_desempenho(valor_grupo, retorno_cdi)
sensibilidade = pd.DataFrame(linhas_sensibilidade).T
mostrar(sensibilidade, "Sensibilidade à quantidade de ações:")

# %% 7. Gráficos
drawdowns = pd.DataFrame({c: calculos.serie_drawdown(valores[c]) for c in ["Low Volatility", "Ibovespa"]})
movel = valores[["Low Volatility", "Ibovespa"]].pct_change().rolling(63).std().dropna() * (252 ** 0.5)

mostrar_figura(graficos.grafico_evolucao(valores))
mostrar_figura(graficos.grafico_ranking(selecionadas))
mostrar_figura(graficos.grafico_retorno(tabela_indicadores))
mostrar_figura(graficos.grafico_volatilidade(tabela_indicadores))
mostrar_figura(graficos.grafico_drawdown(drawdowns))
mostrar_figura(graficos.grafico_contribuicao(contribuicao))
mostrar_figura(graficos.grafico_sensibilidade(sensibilidade))
mostrar_figura(graficos.grafico_volatilidade_movel(movel))

# %% 8. Tabelas CSV e relatório HTML
valores.to_csv(PASTA_RESULTADOS / "evolucao_investimento.csv")
posicoes.to_csv(PASTA_RESULTADOS / "posicoes_diarias.csv")
tabela_indicadores.to_csv(PASTA_RESULTADOS / "indicadores.csv")
por_ano.to_csv(PASTA_RESULTADOS / "rentabilidade_por_periodo.csv")
comparacao.to_csv(PASTA_RESULTADOS / "comparacao_benchmarks.csv", header=["valor"])
tabela_custos.to_csv(PASTA_RESULTADOS / "custos.csv")
contribuicao.to_csv(PASTA_RESULTADOS / "contribuicao.csv", index=False)
sensibilidade.to_csv(PASTA_RESULTADOS / "sensibilidade.csv")
correcoes.to_csv(PASTA_RESULTADOS / "correcoes_proventos_aplicadas.csv", index=False)

caminho = relatorio.gerar_relatorio(
    universo=universo, elegibilidade=elegibilidade, ranking=ranking, selecionadas=selecionadas,
    origem=origem, correcoes=correcoes, indicadores=tabela_indicadores, por_ano=por_ano,
    comparacao=comparacao, custos=tabela_custos, contribuicao=contribuicao, sensibilidade=sensibilidade,
    valores=valores, datas=datas)
print(f"\nRelatório gerado em: {caminho}")
