# calculos.py
# Funções financeiras do estudo. Nenhuma delas acessa a internet, o que permite
# testá-las com dados sintéticos (ver testes.py).

import numpy as np
import pandas as pd

from config import (CAPITAL_INICIAL, CUSTO_ENTRADA, DATA_COMPRA, DATA_FINAL, DATA_SELECAO,
                    INICIO_HISTORICO, JANELA_LIQUIDEZ, JANELA_PRINCIPAL, JANELAS_COMPLEMENTARES,
                    LIQUIDEZ_MINIMA, PREGOES_POR_ANO, PRESENCA_MINIMA, SALTO_MAXIMO_DIARIO,
                    TOLERANCIA_FECHAMENTO)
import coleta


# ---------------------------------------------------------------------------
# Série de preço ajustado
# ---------------------------------------------------------------------------

def ajustar_por_proventos(fechamento, proventos):
    """Monta o preço ajustado a partir do fechamento e dos proventos por ação.

    No dia ex, o retorno é fechamento_hoje / (fechamento_ontem - provento) - 1.
    Esta é a mesma convenção do Adj Close do Yahoo e equivale a reinvestir o provento
    na própria ação. Cada provento entra uma única vez, então não há dupla contagem.
    Dias sem negociação ficam vazios (NaN), nunca preenchidos.
    """
    negociado = fechamento.dropna()
    if negociado.empty:
        return fechamento.copy()

    # Se o dia ex não teve negócio, o provento passa para o próximo pregão negociado.
    por_dia = pd.Series(0.0, index=negociado.index)
    for data, valor in proventos[proventos > 0].items():
        posicao = negociado.index.searchsorted(data)
        if posicao < len(negociado):
            por_dia.iloc[posicao] += valor

    retorno = negociado / (negociado.shift(1) - por_dia) - 1
    ajustado = negociado.iloc[0] * (1 + retorno.fillna(0)).cumprod()
    return ajustado.reindex(fechamento.index)


def fechamento_oficial(ticker, mapa, cotacoes, calendario):
    """Fechamento oficial da B3 no calendário de pregões, juntando trocas de ticker."""
    codigos = mapa.loc[ticker, "codigos_cotahist"].split(",")
    partes = cotacoes[cotacoes["codigo"].isin(codigos)]
    # O código original vale enquanto negociar. O sucessor só entra depois disso, mesmo
    # que já existisse antes (caso da CPLE3, que negociava junto com a CPLE6).
    ordem = {codigo: i for i, codigo in enumerate(codigos)}
    partes = partes.assign(ordem=partes["codigo"].map(ordem)).sort_values(["data", "ordem"])
    ultimo_original = partes.loc[partes["ordem"] == 0, "data"].max()
    partes = partes[(partes["ordem"] == 0) | (partes["data"] > ultimo_original)]
    return partes.drop_duplicates("data", keep="first").set_index("data").reindex(calendario)


def montar_serie_ajustada(ticker, mapa, cotacoes, calendario, correcoes, complementares, data_fim):
    """Monta o preço ajustado de um ativo usando só dados até data_fim.

    Ordem de consulta:
      1. brapi, se liberar o histórico: usa o adjustedClose.
      2. Yahoo: fechamento oficial da B3 na escala do Yahoo mais proventos do Yahoo,
         com as correções documentadas em dados/correcoes_proventos.csv.
      3. Sem provedor: COTAHIST mais dados/proventos_complementares.csv.
    O fechamento oficial substitui o do Yahoo porque a auditoria achou erros nele
    (exemplo: PETR4 em 08/03/2024, -10,57% oficial contra -9,14% no Yahoo).
    """
    cal = calendario[calendario <= data_fim]
    oficial = fechamento_oficial(ticker, mapa, cotacoes, cal)["fechamento"]
    origem = {"ticker": ticker, "ticker_consultado": ticker, "fonte_preco": "", "motivo_brapi": "",
              "fechamentos_corrigidos": 0, "proventos_corrigidos": 0}

    tabela_brapi, motivo = coleta.baixar_brapi(ticker)
    origem["motivo_brapi"] = motivo
    if tabela_brapi is not None:
        origem["fonte_preco"] = "brapi (adjustedClose)"
        ajustado = tabela_brapi["adjustedClose"].reindex(cal).where(oficial.notna())
        return ajustado, origem

    ticker_yahoo = mapa.loc[ticker, "ticker_yahoo"]
    tabela_yahoo = coleta.baixar_yahoo(ticker_yahoo) if ticker_yahoo else pd.DataFrame()
    if len(tabela_yahoo) > 0:
        yahoo = tabela_yahoo.loc[:data_fim]
        # Escala: razão entre o Yahoo (corrigido por desdobramentos) e o preço oficial.
        # A mediana móvel ignora dias com erro e preserva o degrau de um desdobramento.
        escala = (yahoo["Close"] / oficial).rolling(21, center=True, min_periods=1).median()
        escala = escala.reindex(cal).ffill().bfill()
        fechamento = oficial * escala

        proventos = yahoo["Dividends"].astype(float).copy()
        ajustes = correcoes[(correcoes["ticker"] == ticker) & (correcoes["data_ex"] <= data_fim)]
        for _, linha in ajustes.iterrows():
            proventos.loc[linha["data_ex"]] = linha["valor_correto_bruto"] * escala.loc[linha["data_ex"]]

        comparacao = (yahoo["Close"].reindex(cal) / fechamento - 1).abs()
        origem.update(ticker_consultado=ticker_yahoo, fonte_preco="B3 COTAHIST + proventos Yahoo",
                      fechamentos_corrigidos=int((comparacao > TOLERANCIA_FECHAMENTO).sum()),
                      proventos_corrigidos=len(ajustes))
        return ajustar_por_proventos(fechamento, proventos.fillna(0)), origem

    # Ativo que saiu da bolsa e não está mais nos provedores.
    dados = complementares[(complementares["ticker"] == ticker) & (complementares["data_ex"] <= data_fim)]
    proventos = dados.groupby("data_ex")["valor"].sum() if len(dados) else pd.Series(dtype=float)
    origem.update(fonte_preco="B3 COTAHIST + proventos complementares",
                  proventos_corrigidos=len(dados))
    return ajustar_por_proventos(oficial, proventos), origem


def montar_precos(universo, mapa, cotacoes, calendario, correcoes, complementares, data_fim):
    """Devolve (preços ajustados, tabela de origem) de todos os ativos até data_fim."""
    series, origens = {}, []
    for ticker in universo["ticker"]:
        series[ticker], origem = montar_serie_ajustada(ticker, mapa, cotacoes, calendario,
                                                       correcoes, complementares, data_fim)
        origens.append(origem)
    return pd.DataFrame(series), pd.DataFrame(origens)


# ---------------------------------------------------------------------------
# Indicadores básicos
# ---------------------------------------------------------------------------

def retornos_simples(precos):
    """Retorno = preço de hoje / preço de ontem - 1. Sem preenchimento de valores ausentes."""
    return precos.pct_change(fill_method=None)


def volatilidade_janela(retornos, janela):
    """Volatilidade anualizada dos últimos 'janela' retornos, ou NaN se faltar algum."""
    trecho = retornos.iloc[-janela:]
    if len(trecho) < janela or trecho.notna().sum() < janela:
        return np.nan
    return trecho.std(ddof=1) * np.sqrt(PREGOES_POR_ANO)


def maximo_drawdown(precos):
    """Maior queda em relação ao máximo anterior. Devolve número negativo."""
    return (precos / precos.cummax() - 1).min()


def serie_drawdown(precos):
    return precos / precos.cummax() - 1


# ---------------------------------------------------------------------------
# Elegibilidade, ranking e seleção
# ---------------------------------------------------------------------------

def indicadores_formacao(precos, volume_financeiro, universo, setores):
    """Calcula os indicadores de cada ativo. Recusa dados posteriores à seleção."""
    if precos.index.max() > DATA_SELECAO or volume_financeiro.index.max() > DATA_SELECAO:
        raise ValueError("Dados posteriores à data de seleção não podem entrar aqui.")

    linhas = []
    for _, ativo in universo.iterrows():
        ticker = ativo["ticker"]
        retornos = retornos_simples(precos[ticker])
        janela = retornos.iloc[-JANELA_PRINCIPAL:]
        volume = volume_financeiro[ticker].iloc[-JANELA_LIQUIDEZ:]
        linha = {"ticker": ticker, "empresa": ativo["empresa"], "setor": setores.get(ticker, "")}
        linha["retornos_validos_252"] = int(janela.notna().sum())
        for tamanho in JANELAS_COMPLEMENTARES + [JANELA_PRINCIPAL]:
            linha[f"vol_{tamanho}"] = volatilidade_janela(retornos, tamanho)
        linha["max_drawdown_hist"] = maximo_drawdown(precos[ticker].iloc[-(JANELA_PRINCIPAL + 1):])
        linha["liquidez_media_63"] = volume.fillna(0).mean()
        linha["presenca_63"] = volume.notna().mean()
        linha["freq_retorno_zero"] = (janela == 0).sum() / max(janela.notna().sum(), 1)
        linha["maior_salto"] = janela.abs().max()
        linhas.append(linha)
    return pd.DataFrame(linhas)


def aplicar_filtros(indicadores):
    """Tabela de elegibilidade, com o motivo de cada exclusão.

    Quando a empresa tem mais de uma classe no índice, fica a mais líquida em 63 pregões.
    A regra usa liquidez e não volatilidade, para não escolher a classe pelo resultado.
    """
    tabela = indicadores.copy()
    maior_liquidez = tabela.groupby("empresa")["liquidez_media_63"].transform("max")
    tabela["instrumento_da_empresa"] = tabela["liquidez_media_63"] == maior_liquidez

    motivos = []
    for _, linha in tabela.iterrows():
        problemas = []
        if not linha["instrumento_da_empresa"]:
            problemas.append("outra classe da mesma empresa é mais líquida")
        if linha["retornos_validos_252"] < JANELA_PRINCIPAL:
            problemas.append(f"só {linha['retornos_validos_252']} retornos válidos")
        if linha["liquidez_media_63"] < LIQUIDEZ_MINIMA:
            problemas.append("liquidez abaixo de R$ 5 milhões por dia")
        if linha["presenca_63"] < PRESENCA_MINIMA:
            problemas.append("negociou em menos de 95% dos pregões")
        if linha["maior_salto"] > SALTO_MAXIMO_DIARIO:
            problemas.append("salto diário acima de 40% (evento sem ajuste)")
        motivos.append("; ".join(problemas))
    tabela["motivo_exclusao"] = motivos
    tabela["elegivel"] = tabela["motivo_exclusao"] == ""
    return tabela


def montar_ranking(elegibilidade):
    """Ordena por volatilidade de 252 pregões. Empate: maior liquidez, depois ticker."""
    ranking = elegibilidade[elegibilidade["elegivel"]].copy()
    ranking["liquidez_negativa"] = -ranking["liquidez_media_63"]
    ranking = ranking.sort_values(["vol_252", "liquidez_negativa", "ticker"]).drop(columns="liquidez_negativa")
    ranking.insert(0, "posicao", range(1, len(ranking) + 1))
    return ranking.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Carteira buy and hold
# ---------------------------------------------------------------------------

def simular_buy_and_hold(precos, tickers, capital=CAPITAL_INICIAL, custo=0.0):
    """Simula a compra com pesos iguais na primeira data e mantém até a última.

    A quantidade de cada ação é calculada uma única vez, na compra. Depois disso só o
    preço muda, então os pesos variam livremente e não há rebalanceamento. A quantidade
    pode ser fracionária (premissa do relatório). 'custo' reduz o valor aplicado na compra.
    Devolve (valor de cada posição por dia, quantidades).
    """
    trecho = precos[list(tickers)].ffill()  # dia sem negócio mantém o último preço só na avaliação
    if trecho.iloc[0].isna().any():
        raise ValueError("Ativo sem preço na data da compra.")
    por_ativo = capital / len(tickers)
    quantidades = por_ativo * (1 - custo) / trecho.iloc[0]
    return trecho * quantidades, quantidades


def fator_cdi(cdi, datas):
    """Fator acumulado do CDI nas datas pedidas, com base 1 na primeira.

    A taxa de um dia remunera até o dia útil seguinte. Quem aplica no fechamento de
    28/03/2024 recebe a taxa de 28/03 ao chegar em 01/04. Por isso o fator de uma data
    usa as taxas anteriores a ela. Assim dias com CDI e sem pregão (24/12 e 31/12)
    continuam rendendo.
    """
    acumulado = (1 + cdi).cumprod().shift(1).fillna(1.0)
    alinhado = acumulado.reindex(acumulado.index.union(datas)).ffill().reindex(datas)
    return alinhado / alinhado.iloc[0]


# ---------------------------------------------------------------------------
# Indicadores de desempenho
# ---------------------------------------------------------------------------

def indicadores_desempenho(valor, retorno_cdi, usar_sharpe=True):
    """Calcula os indicadores de uma série de valor do investimento."""
    retornos = valor.pct_change(fill_method=None).dropna()
    acumulado = valor.iloc[-1] / valor.iloc[0] - 1
    anualizado = (1 + acumulado) ** (PREGOES_POR_ANO / len(retornos)) - 1
    volatilidade = retornos.std(ddof=1) * np.sqrt(PREGOES_POR_ANO)
    resultado = {"valor_final": valor.iloc[-1], "retorno_acumulado": acumulado,
                 "retorno_anualizado": anualizado, "volatilidade_anualizada": volatilidade,
                 "maximo_drawdown": maximo_drawdown(valor), "sharpe": np.nan}
    if usar_sharpe:
        resultado["sharpe"] = indice_sharpe(retornos, retorno_cdi)
    return resultado


def indice_sharpe(retornos, retorno_cdi):
    """Sharpe = média(retorno - CDI) / desvio-padrão amostral(retorno) * raiz(252)."""
    excesso = retornos - retorno_cdi.reindex(retornos.index)
    return excesso.mean() / retornos.std(ddof=1) * np.sqrt(PREGOES_POR_ANO)


def rentabilidade_por_ano(valores):
    """Retorno em cada ano civil. Os anos de 2024 e 2026 são períodos parciais."""
    resultado = {}
    for coluna in valores.columns:
        serie = valores[coluna]
        fins = serie.groupby(serie.index.year).last()
        inicio = serie.iloc[0]
        for ano, fim in fins.items():
            resultado.setdefault(ano, {})[coluna] = fim / inicio - 1
            inicio = fim
    tabela = pd.DataFrame(resultado).T
    tabela.index = [_nome_do_ano(ano, valores.index) for ano in tabela.index]
    tabela.index.name = "periodo"
    return tabela


def _nome_do_ano(ano, datas):
    do_ano = datas[datas.year == ano]
    inicio, fim = do_ano.min(), do_ano.max()
    if ano == datas.min().year and inicio.month > 1 or ano == datas.max().year and fim.month < 12:
        return f"{ano} (parcial, {inicio:%d/%m} a {fim:%d/%m})"
    return str(ano)


def contribuicao_individual(posicoes, ranking):
    """Retorno e contribuição de cada ação. A soma das contribuições é o retorno da carteira."""
    inicial, final = posicoes.iloc[0], posicoes.iloc[-1]
    capital = inicial.sum()
    tabela = pd.DataFrame({"ticker": posicoes.columns, "valor_inicial": inicial.values,
                           "peso_inicial": (inicial / capital).values, "valor_final": final.values})
    tabela["retorno_acumulado"] = tabela["valor_final"] / tabela["valor_inicial"] - 1
    tabela["contribuicao"] = (tabela["valor_final"] - tabela["valor_inicial"]) / capital
    tabela["peso_final"] = tabela["valor_final"] / final.sum()
    dados = ranking.set_index("ticker")
    tabela.insert(1, "empresa", tabela["ticker"].map(dados["empresa"]))
    tabela.insert(2, "vol_252", tabela["ticker"].map(dados["vol_252"]))
    return tabela.sort_values("contribuicao", ascending=False).reset_index(drop=True)
