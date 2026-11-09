# testes.py
# Parte 1: testes com dados sintéticos, que não têm relação com o mercado real.
# Parte 2: verificações sobre os dados reais e os resultados (rode inicio.py antes).
# Parte 3: executa inicio.py como notebook para confirmar que funciona no Jupyter.
# Uso: python testes.py

import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")

import calculos as c
import coleta
from config import (DATA_COMPRA, DATA_FINAL, DATA_SELECAO, INICIO_HISTORICO, PASTA_PROJETO, PASTA_RESULTADOS)

resultados = []


def teste(nome, condicao, detalhe=""):
    resultados.append((nome, bool(condicao), detalhe))
    print(f"[{'OK' if condicao else 'FALHOU'}] {nome}" + (f" ({detalhe})" if detalhe else ""))


# ---------------------------------------------------------------------------
# Parte 1: dados sintéticos
# ---------------------------------------------------------------------------
print("PARTE 1: dados sintéticos")
gerador = np.random.default_rng(1)
datas = pd.bdate_range("2023-01-02", periods=400)
retornos_falsos = pd.Series(gerador.normal(0, 0.01, 400), index=datas)

# Volatilidade: confere com o cálculo manual do desvio amostral
trecho = retornos_falsos.iloc[-252:].values
manual = np.sqrt(((trecho - trecho.mean()) ** 2).sum() / 251) * np.sqrt(252)
teste("Volatilidade usa ddof=1 e raiz de 252", abs(c.volatilidade_janela(retornos_falsos, 252) - manual) < 1e-12)

# Janela incompleta não pode gerar volatilidade baixa
com_falta = retornos_falsos.copy()
com_falta.iloc[-10] = np.nan
teste("Janela com retorno ausente devolve NaN", np.isnan(c.volatilidade_janela(com_falta, 252)))
teste("Histórico curto devolve NaN", np.isnan(c.volatilidade_janela(retornos_falsos.iloc[:100], 252)))

# Retorno não preenche buraco
precos_buraco = pd.Series([10.0, 11.0, np.nan, 12.0, 13.0])
r = c.retornos_simples(precos_buraco)
teste("Dia sem preço invalida os retornos em volta", r.isna().tolist() == [True, False, True, True, False])

# Proventos: uma ação de 100 paga 10 e abre a 90. O retorno ajustado deve ser zero.
fechamento = pd.Series([100.0, 90.0, 99.0], index=pd.date_range("2024-01-01", periods=3))
proventos = pd.Series([10.0], index=[fechamento.index[1]])
ajustado = c.ajustar_por_proventos(fechamento, proventos)
teste("Dia ex sem variação real tem retorno zero", abs(ajustado.iloc[1] / ajustado.iloc[0] - 1) < 1e-12)
teste("Provento conta uma única vez", abs(ajustado.iloc[2] / ajustado.iloc[0] - 1.10) < 1e-12)

# Provento em dia sem negócio passa para o próximo pregão
com_vazio = pd.Series([100.0, np.nan, 90.0], index=pd.date_range("2024-01-01", periods=3))
teste("Provento em dia sem negócio não se perde",
      abs(c.ajustar_por_proventos(com_vazio, pd.Series([10.0], index=[com_vazio.index[1]])).iloc[2] - 100) < 1e-9)

# Drawdown
teste("Máximo drawdown", abs(c.maximo_drawdown(pd.Series([100, 120, 90, 130.0])) + 0.25) < 1e-12)

# Filtros e ranking com empate
base = pd.DataFrame({
    "ticker": ["AAAA3", "BBBB3", "CCCC3", "DDDD4", "DDDD3", "EEEE3", "FFFF3"],
    "empresa": ["A", "B", "C", "D", "D", "E", "F"],
    "retornos_validos_252": [252, 252, 252, 252, 252, 200, 252],
    "vol_252": [0.20, 0.20, 0.10, 0.15, 0.12, 0.05, 0.08],
    "liquidez_media_63": [8e6, 9e6, 1e6, 7e7, 6e6, 9e7, 9e7],
    "presenca_63": [1, 1, 1, 1, 1, 1, 0.90],
    "maior_salto": [.05] * 7,
})
elegib = c.aplicar_filtros(base)
ranking_falso = c.montar_ranking(elegib)
teste("Filtros removem liquidez baixa, presença baixa, histórico curto e classe duplicada",
      set(elegib[~elegib["elegivel"]]["ticker"]) == {"CCCC3", "DDDD3", "EEEE3", "FFFF3"})
teste("Empate resolvido pela maior liquidez", ranking_falso["ticker"].tolist() == ["DDDD4", "BBBB3", "AAAA3"])

# Buy and hold
datas_bh = pd.date_range("2024-01-01", periods=3)
precos_bh = pd.DataFrame({"X": [10.0, 20.0, 40.0], "Y": [10.0, 10.0, 10.0]}, index=datas_bh)
posicoes_bh, qtd = c.simular_buy_and_hold(precos_bh, ["X", "Y"], capital=100.0)
teste("Buy and hold: pesos iniciais somam 100%", abs((posicoes_bh.iloc[0] / posicoes_bh.iloc[0].sum()).sum() - 1) < 1e-12)
teste("Buy and hold: valor final correto (X 4x, Y 1x)", abs(posicoes_bh.iloc[-1].sum() - 250) < 1e-9)
teste("Buy and hold: pesos mudam, sem rebalanceamento", abs(posicoes_bh.iloc[-1]["X"] / 250 - 0.8) < 1e-9)
rebal = 100 * (1 + 0.5 * (precos_bh.pct_change().fillna(0)).sum(axis=1)).cumprod().iloc[-1]
teste("Buy and hold difere de pesos fixos diários", abs(rebal - 250) > 1, f"pesos fixos = {rebal:.2f}")
custo, _ = c.simular_buy_and_hold(precos_bh, ["X", "Y"], capital=100.0, custo=0.001)
teste("Custo de 0,10% reduz o valor final em 0,10%", abs(custo.iloc[-1].sum() - 250 * 0.999) < 1e-9)

# Contribuição soma o retorno da carteira
ranking_bh = pd.DataFrame({"ticker": ["X", "Y"], "empresa": ["X", "Y"], "vol_252": [.1, .1]})
contrib = c.contribuicao_individual(posicoes_bh, ranking_bh)
teste("Contribuições somam o retorno da carteira", abs(contrib["contribuicao"].sum() - 1.5) < 1e-12)

# CDI: dia sem pregão continua rendendo; a taxa de hoje só paga no próximo dia
dias_cdi = pd.to_datetime(["2024-12-23", "2024-12-24", "2024-12-26"])
fator_teste = c.fator_cdi(pd.Series([0.001, 0.002, 0.003], index=dias_cdi), pd.to_datetime(["2024-12-23", "2024-12-26"]))
teste("CDI acumula a taxa de dia sem pregão e paga no dia seguinte", abs(fator_teste.iloc[1] - 1.001 * 1.002) < 1e-12)

# Sharpe
r_s = pd.Series([0.01, -0.005, 0.02, 0.0])
rf_s = pd.Series([0.001] * 4)
esperado = (r_s - rf_s).mean() / r_s.std(ddof=1) * np.sqrt(252)
teste("Sharpe segue a fórmula do trabalho", abs(c.indice_sharpe(r_s, rf_s) - esperado) < 1e-12)

# Proteção contra dado futuro
tudo = pd.DataFrame({"AAAA3": [1.0, 1.1]}, index=[DATA_SELECAO, DATA_COMPRA])
uni_teste = pd.DataFrame({"ticker": ["AAAA3"], "empresa": ["A"]})
try:
    c.indicadores_formacao(tudo, tudo, uni_teste, pd.Series(dtype=str))
    teste("Dado posterior à seleção é recusado", False)
except ValueError:
    teste("Dado posterior à seleção é recusado", True)

# ---------------------------------------------------------------------------
# Parte 2: dados reais
# ---------------------------------------------------------------------------
print("\nPARTE 2: dados reais e resultados")
universo = coleta.carregar_universo()
mapa = coleta.carregar_mapa_tickers()
correcoes = coleta.carregar_correcoes_proventos()
complementares = coleta.carregar_proventos_complementares()
codigos = sorted({x for texto in mapa["codigos_cotahist"] for x in texto.split(",")})
cotacoes, calendario = coleta.carregar_cotahist(codigos)
calendario = calendario[(calendario >= INICIO_HISTORICO) & (calendario <= DATA_FINAL)]
ranking = pd.read_csv(PASTA_RESULTADOS / "ranking.csv")
elegib = pd.read_csv(PASTA_RESULTADOS / "elegibilidade.csv")
valores = pd.read_csv(PASTA_RESULTADOS / "evolucao_investimento.csv", index_col=0, parse_dates=True)
posicoes = pd.read_csv(PASTA_RESULTADOS / "posicoes_diarias.csv", index_col=0, parse_dates=True)
indicadores = pd.read_csv(PASTA_RESULTADOS / "indicadores.csv", index_col=0)
contribuicao = pd.read_csv(PASTA_RESULTADOS / "contribuicao.csv")
tickers = ranking["ticker"].head(10).tolist()

# 1. Universo
teste("1. Universo com 87 ativos e participações somando cerca de 100%",
      len(universo) == 87 and abs(universo["participacao_pct"].sum() - 100) < 0.01, f"soma {universo['participacao_pct'].sum():.3f}")
teste("1. Universo tem nomes que saíram do índice ou da bolsa", {"CIEL3", "CRFB3", "SOMA3", "TRPL4"} <= set(universo["ticker"]))

# 2. Sem dado futuro: as séries do corte e as completas têm os mesmos retornos no passado
corte, _ = c.montar_precos(universo, mapa, cotacoes, calendario, correcoes, complementares, DATA_SELECAO)
completo, _ = c.montar_precos(universo, mapa, cotacoes, calendario, correcoes, complementares, DATA_FINAL)
teste("2. Séries de seleção terminam em 27/03/2024", corte.index.max() == DATA_SELECAO)
dif = (c.retornos_simples(corte) - c.retornos_simples(completo.loc[:DATA_SELECAO])).abs().iloc[-252:]
teste("2. Janela de seleção igual com e sem dados futuros (selecionadas)", dif[tickers].max().max() < 1e-4,
      f"maior diferença {dif[tickers].max().max():.2e}")
retornos_refeitos = c.retornos_simples(completo.loc[:DATA_SELECAO])
ranking_refeito = pd.Series({t: c.volatilidade_janela(retornos_refeitos[t], 252) for t in ranking["ticker"]})
ordem = ranking_refeito.sort_values().index[:10].tolist()
teste("2. Mesmo ranking usando a série completa cortada na seleção", set(ordem) == set(tickers), ", ".join(ordem))

# 3. Janela
retornos_corte = c.retornos_simples(corte)
teste("3. Selecionadas têm 252 retornos válidos", (retornos_corte[tickers].iloc[-252:].notna().sum() == 252).all())
teste("3. Janela ocupa 253 pregões oficiais consecutivos", corte[tickers].iloc[-253:].notna().all().all())
datas_cal = calendario[calendario <= DATA_SELECAO]
teste("3. Janela termina em 27/03/2024", datas_cal[-1] == DATA_SELECAO, f"início {datas_cal[-253]:%d/%m/%Y}")

# 4. Seleção
vol_elegiveis = elegib[elegib["elegivel"]].sort_values("vol_252")["ticker"].head(10).tolist()
teste("4. As 10 selecionadas são as elegíveis de menor volatilidade", vol_elegiveis == tickers)
teste("4. Nenhuma empresa repetida", ranking["empresa"].is_unique)

# 5, 6 e 7. Carteira
iniciais = posicoes.iloc[0]
teste("5. Pesos iniciais de 10% somam 100%", (abs(iniciais - 10000) < 1e-6).all() and abs(iniciais.sum() - 100000) < 1e-6)
final_manual = sum(10000 * completo[t].ffill().loc[DATA_FINAL] / completo[t].loc[DATA_COMPRA] for t in tickers)
teste("7. Valor final confere com cálculo independente", abs(final_manual - valores["Low Volatility"].iloc[-1]) < 1e-6, f"R$ {final_manual:,.2f}")
pesos = posicoes.div(posicoes.sum(axis=1), axis=0)
teste("6. Pesos variam no tempo (sem rebalanceamento)", pesos.std().min() > 0.001, f"menor desvio {pesos.std().min():.4f}")
teste("6. Quantidades constantes", (posicoes.iloc[-1] / completo[tickers].ffill().loc[DATA_FINAL]).sub(
    posicoes.iloc[0] / completo[tickers].loc[DATA_COMPRA]).abs().max() < 1e-9)
teste("7. Contribuições somam o retorno da carteira", abs(contribuicao["contribuicao"].sum() - indicadores.loc["Low Volatility", "retorno_acumulado"]) < 1e-9)
teste("7. Primeira data da série é a compra e a última é o fim", valores.index[0] == DATA_COMPRA and valores.index[-1] == DATA_FINAL)
teste("7. Primeiro retorno da carteira é de 01/04/2024", valores.index[1] == pd.Timestamp("2024-04-01"))

# 8. Sem dupla contagem: a nossa montagem reproduz o Adj Close em ativo sem correção
for ticker in ["EGIE3", "EQTL3"]:
    yahoo = coleta.baixar_yahoo(ticker).loc[:DATA_SELECAO]
    oficial = c.fechamento_oficial(ticker, mapa, cotacoes, datas_cal)["fechamento"]
    nosso = c.ajustar_por_proventos(oficial * (yahoo["Close"] / oficial).median(), yahoo["Dividends"])
    diferenca = (nosso.iloc[-1] / nosso.iloc[-253]) / (yahoo["Adj Close"].iloc[-1] / yahoo["Adj Close"].iloc[-253]) - 1
    teste(f"8. {ticker}: retorno da nossa série bate com o Adj Close do Yahoo", abs(diferenca) < 0.005, f"diferença {diferenca:.4%}")

# 8b. Provento contado uma vez: BBSE3 teve 1,6076 em 17/08/2023
yb = completo["BBSE3"]
oficial_bb = c.fechamento_oficial("BBSE3", mapa, cotacoes, calendario)["fechamento"]
r_oficial = oficial_bb.loc["2023-08-17"] / oficial_bb.loc["2023-08-16"] - 1
r_ajustado = yb.loc["2023-08-17"] / yb.loc["2023-08-16"] - 1
r_formula = oficial_bb.loc["2023-08-17"] / (oficial_bb.loc["2023-08-16"] - 1.6076) - 1
teste("8. BBSE3 no dia ex: provento de R$ 1,6076 entra uma vez", abs(r_ajustado - r_formula) < 1e-4, f"{r_oficial:.2%} vira {r_ajustado:.2%}")

# 8c. Comparação da brapi com a montagem via Yahoo no ITUB4
b_itub = coleta.baixar_brapi("ITUB4")[0]["adjustedClose"]
y_itub = coleta.baixar_yahoo("ITUB4")["Adj Close"]
rel = (b_itub.loc[DATA_COMPRA:DATA_FINAL].iloc[-1] / b_itub.loc[DATA_COMPRA]) / (y_itub.loc[DATA_COMPRA:DATA_FINAL].iloc[-1] / y_itub.loc[DATA_COMPRA]) - 1
teste("8. ITUB4: retorno na brapi perto do retorno no Yahoo", abs(rel) < 0.02, f"diferença {rel:.2%}")

# 9. CDI
cdi = coleta.carregar_cdi()
teste("9. CDI em decimal por dia", 0.0002 < cdi.loc[DATA_COMPRA:].mean() < 0.001, f"média {cdi.loc[DATA_COMPRA:].mean():.6f}")
teste("9. CDI de 28/03/2024 é 0,040168% convertido", abs(cdi.loc["2024-03-28"] - 0.00040168) < 1e-10)
direto = (1 + cdi.loc[DATA_COMPRA:DATA_FINAL - pd.Timedelta(days=1)]).prod() - 1
teste("9. Retorno do CDI confere com o produto das taxas", abs(direto - indicadores.loc["CDI", "retorno_acumulado"]) < 1e-9, f"{direto:.4%}")

# 10. Sharpe
ret = valores.pct_change().dropna()
rf = ret["CDI"]
s = ((ret["Low Volatility"] - rf).mean() / ret["Low Volatility"].std(ddof=1)) * np.sqrt(252)
teste("10. Sharpe da carteira confere", abs(s - indicadores.loc["Low Volatility", "sharpe"]) < 1e-9, f"{s:.4f}")
s_ib = ((ret["Ibovespa"] - rf).mean() / ret["Ibovespa"].std(ddof=1)) * np.sqrt(252)
teste("10. Sharpe do Ibovespa confere", abs(s_ib - indicadores.loc["Ibovespa", "sharpe"]) < 1e-9, f"{s_ib:.4f}")

# Ibovespa oficial x Yahoo
ib_b3 = coleta.carregar_ibovespa()
try:
    import yfinance as yf
    h = yf.Ticker("^BVSP").history(start=DATA_COMPRA, end=DATA_FINAL + pd.Timedelta(days=1))
    h.index = h.index.tz_localize(None).normalize()
    r_b3 = ib_b3.loc[DATA_FINAL] / ib_b3.loc[DATA_COMPRA] - 1
    r_yh = h["Close"].loc[DATA_FINAL] / h["Close"].loc[DATA_COMPRA] - 1
    teste("Ibovespa oficial da B3 confere com o Yahoo no período", abs(r_b3 - r_yh) < 0.005, f"B3 {r_b3:.2%}, Yahoo {r_yh:.2%}")
except Exception as erro:
    teste("Ibovespa oficial da B3 confere com o Yahoo no período", False, f"não executado: {erro}")

# 11 e 12. Arquivos
pngs = sorted(PASTA_RESULTADOS.glob("grafico_*.png"))
csvs = sorted(PASTA_RESULTADOS.glob("*.csv"))
teste("11. Oito gráficos gerados e não vazios", len(pngs) == 8 and all(p.stat().st_size > 10000 for p in pngs))
teste("11. Tabelas CSV geradas", len(csvs) >= 10, f"{len(csvs)} arquivos")
texto = (PASTA_RESULTADOS / "relatorio.html").read_text(encoding="utf-8")
secoes = re.findall(r"<h2>(\d+)\.", texto)
teste("12. Relatório tem as 18 seções e 8 imagens", secoes == [str(i) for i in range(1, 19)] and texto.count("data:image/png") == 8)
teste("12. Relatório não tem travessão nem NaN", "—" not in texto and ">nan<" not in texto.lower())
from html.parser import HTMLParser
HTMLParser().feed(texto)
teste("12. HTML interpretado sem erro pelo parser", True)

# ---------------------------------------------------------------------------
# Parte 3: execução como notebook
# ---------------------------------------------------------------------------
print("\nPARTE 3: execução no Jupyter")
try:
    import nbformat
    from nbclient import NotebookClient

    fonte = (PASTA_PROJETO / "inicio.py").read_text(encoding="utf-8")
    celulas = [nbformat.v4.new_code_cell(p) for p in re.split(r"^# %%.*$", fonte, flags=re.M)[1:]]
    caderno = nbformat.v4.new_notebook(cells=celulas)
    NotebookClient(caderno, timeout=600, kernel_name="python3",
                   resources={"metadata": {"path": str(PASTA_PROJETO)}}).execute()
    saidas = [s for cel in caderno.cells for s in cel.outputs]
    imagens = sum("image/png" in s.get("data", {}) for s in saidas)
    tabelas = sum("text/html" in s.get("data", {}) for s in saidas)
    teste("13. Notebook executa todas as células", True, f"{len(celulas)} células")
    teste("13. Gráficos aparecem no notebook", imagens == 8, f"{imagens} imagens")
    teste("13. Tabelas aparecem no notebook", tabelas >= 8, f"{tabelas} tabelas")
except Exception as erro:
    teste("13. Notebook executa todas as células", False, f"{type(erro).__name__}: {str(erro)[:300]}")

falhas = [r for r in resultados if not r[1]]
print(f"\n{len(resultados) - len(falhas)} de {len(resultados)} verificações passaram.")
with open(PASTA_RESULTADOS / "validacao.txt", "w", encoding="utf-8") as saida:
    for nome, ok, detalhe in resultados:
        saida.write(f"[{'OK' if ok else 'FALHOU'}] {nome}" + (f" ({detalhe})" if detalhe else "") + "\n")
sys.exit(1 if falhas else 0)
