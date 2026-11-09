# coleta.py
# Funções que buscam os dados e guardam uma cópia em dados/brutos.
# Na segunda execução o programa lê a cópia local (cache), então os resultados
# ficam reproduzíveis mesmo se uma API sair do ar.
#
# Fontes usadas:
#   B3 COTAHIST ......... fechamento oficial e volume financeiro em reais
#   brapi ............... preço ajustado (consultada primeiro; plano define o acesso)
#   Yahoo Finance ....... proventos e desdobramentos quando a brapi não libera
#   B3 índices .......... série diária oficial do Ibovespa
#   Banco Central ....... CDI diário (SGS 12)

import base64
import io
import json
import os
import zipfile

import pandas as pd
import requests

from config import INICIO_HISTORICO, DATA_FINAL, PASTA_BRUTOS, PASTA_DADOS

CABECALHO = {"User-Agent": "Mozilla/5.0"}


# ---------------------------------------------------------------------------
# Universo: composição histórica do Ibovespa
# ---------------------------------------------------------------------------

def carregar_universo():
    """Lê a carteira teórica do Ibovespa de janeiro a abril de 2024 (87 ativos).

    O arquivo é uma cópia da tabela publicada pela B3 e foi conferido com a captura
    da API oficial feita pelo Internet Archive em 14/04/2024. A composição atual do
    índice não é usada em nenhum momento.
    """
    return pd.read_csv(PASTA_DADOS / "universo_ibov_jan_abr_2024.csv")


def carregar_mapa_tickers():
    """Lê a tabela que liga o ticker de março de 2024 aos códigos usados nas fontes."""
    mapa = pd.read_csv(PASTA_DADOS / "mapa_tickers.csv", keep_default_na=False)
    return mapa.set_index("ticker")


def carregar_setores():
    """Lê a classificação setorial oficial da B3 (arquivo de 05/09/2025)."""
    return pd.read_csv(PASTA_DADOS / "setores.csv").set_index("ticker")["setor"]


# ---------------------------------------------------------------------------
# COTAHIST: arquivo oficial de cotações da B3
# ---------------------------------------------------------------------------

def _baixar_ano_cotahist(ano):
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
    resposta = requests.get(url, headers=CABECALHO, timeout=600)
    resposta.raise_for_status()
    return resposta.content


def carregar_cotahist(codigos):
    """Devolve (cotações, calendário) do mercado à vista para os códigos pedidos.

    Layout oficial da B3, em posições fixas. O preço vem em centavos e o volume
    financeiro (VOLTOT) também, então os dois são divididos por 100. Dessa forma o
    volume já está em reais e não é confundido com quantidade de ações.
    Todos os códigos BDI do mercado à vista são aceitos: um filtro só por lote
    padrão perderia empresas em recuperação judicial, como a GOLL4 em 2024.
    """
    arquivo = PASTA_BRUTOS / "cotahist_universo.csv.gz"
    arquivo_calendario = PASTA_BRUTOS / "calendario_b3.csv"

    if arquivo.exists() and arquivo_calendario.exists():
        cotacoes = pd.read_csv(arquivo, parse_dates=["data"])
        calendario = pd.read_csv(arquivo_calendario, parse_dates=["data"])["data"]
        return cotacoes, pd.DatetimeIndex(calendario)

    linhas, datas = [], set()
    desejados = set(codigos)
    for ano in range(INICIO_HISTORICO.year, DATA_FINAL.year + 1):
        print(f"  baixando COTAHIST {ano} (cerca de 90 MB)...")
        with zipfile.ZipFile(io.BytesIO(_baixar_ano_cotahist(ano))) as pacote:
            with pacote.open(pacote.namelist()[0]) as texto:
                for r in texto:
                    if r[:2] != b"01":
                        continue
                    data = r[2:10].decode()
                    datas.add(data)
                    if r[24:27] != b"010":  # 010 = mercado à vista
                        continue
                    codigo = r[12:24].decode().strip()
                    if codigo in desejados:
                        linhas.append((data, codigo, r[10:12].decode(),
                                       int(r[108:121]) / 100,    # PREULT
                                       int(r[147:152]),          # TOTNEG
                                       int(r[152:170]),          # QUATOT
                                       int(r[170:188]) / 100))   # VOLTOT

    colunas = ["data", "codigo", "bdi", "fechamento", "negocios", "quantidade", "volume_financeiro"]
    cotacoes = pd.DataFrame(linhas, columns=colunas)
    cotacoes["data"] = pd.to_datetime(cotacoes["data"], format="%Y%m%d")
    calendario = pd.to_datetime(sorted(datas), format="%Y%m%d")
    PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    cotacoes.to_csv(arquivo, index=False)
    pd.DataFrame({"data": calendario}).to_csv(arquivo_calendario, index=False)
    return cotacoes, pd.DatetimeIndex(calendario)


# ---------------------------------------------------------------------------
# brapi: consultada primeiro
# ---------------------------------------------------------------------------

def token_brapi():
    """Procura a chave na variável de ambiente ou no arquivo .env local."""
    try:
        from dotenv import load_dotenv
        load_dotenv(PASTA_DADOS.parent / ".env")
    except ImportError:
        pass
    return os.environ.get("BRAPI_TOKEN", "").strip()


def baixar_brapi(ticker):
    """Tenta o histórico ajustado na brapi. Devolve (tabela ou None, motivo).

    Sem token só PETR4, VALE3, ITUB4 e MGLU3 respondem. No plano gratuito com token o
    histórico é limitado a 3 meses e um pedido maior retorna erro 400.
    """
    arquivo = PASTA_BRUTOS / f"brapi_{ticker}.csv"
    if arquivo.exists():
        return pd.read_csv(arquivo, parse_dates=["data"], index_col="data"), "cache local"

    # Sem token, só tenta os 4 símbolos abertos, para não fazer pedidos que falham.
    token = token_brapi()
    if not token and ticker not in {"PETR4", "VALE3", "ITUB4", "MGLU3"}:
        return None, "exige token"

    parametros = {"interval": "1d", "startDate": INICIO_HISTORICO.strftime("%Y-%m-%d"),
                  "endDate": DATA_FINAL.strftime("%Y-%m-%d")}
    cabecalho = {**CABECALHO}
    if token:
        cabecalho["Authorization"] = f"Bearer {token}"
    try:
        resposta = requests.get(f"https://brapi.dev/api/quote/{ticker}", params=parametros,
                                headers=cabecalho, timeout=60)
    except requests.RequestException as erro:
        return None, f"falha de conexão ({type(erro).__name__})"
    if resposta.status_code != 200:
        return None, f"HTTP {resposta.status_code}"
    resultado = resposta.json().get("results", [{}])[0].get("historicalDataPrice") or []
    if not resultado:
        return None, "sem histórico"

    tabela = pd.DataFrame(resultado)
    tabela["data"] = pd.to_datetime(tabela["date"], unit="s").dt.tz_localize("UTC") \
        .dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None).dt.normalize()
    tabela = tabela[["data", "close", "adjustedClose", "volume"]].set_index("data").sort_index()
    if tabela.index.min() > INICIO_HISTORICO + pd.Timedelta(days=10):
        return None, "histórico curto para o estudo"
    tabela.to_csv(arquivo)
    return tabela, "ok"


# ---------------------------------------------------------------------------
# Yahoo Finance: alternativa quando a brapi não libera o histórico
# ---------------------------------------------------------------------------

def baixar_yahoo(ticker_yahoo):
    """Baixa fechamento, proventos e desdobramentos. Devolve tabela vazia se não houver."""
    arquivo = PASTA_BRUTOS / f"yahoo_{ticker_yahoo}.csv"
    if arquivo.exists():
        return pd.read_csv(arquivo, parse_dates=["data"], index_col="data")

    import yfinance as yf

    fim = DATA_FINAL + pd.Timedelta(days=1)
    bruto = yf.Ticker(ticker_yahoo + ".SA").history(start=INICIO_HISTORICO, end=fim,
                                                    auto_adjust=False, actions=True)
    if bruto.empty:
        tabela = pd.DataFrame(columns=["Close", "Adj Close", "Dividends", "Stock Splits", "Volume"])
    else:
        bruto.index = bruto.index.tz_localize(None).normalize()
        tabela = bruto[["Close", "Adj Close", "Dividends", "Stock Splits", "Volume"]]
    tabela.index.name = "data"
    tabela.to_csv(arquivo)
    return tabela


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def carregar_cdi():
    """CDI diário do BCB (SGS 12). O valor vem em % ao dia e é convertido para decimal."""
    arquivo = PASTA_BRUTOS / "cdi_sgs12.csv"
    if arquivo.exists():
        return pd.read_csv(arquivo, parse_dates=["data"], index_col="data")["cdi"]

    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
    parametros = {"formato": "json", "dataInicial": INICIO_HISTORICO.strftime("%d/%m/%Y"),
                  "dataFinal": DATA_FINAL.strftime("%d/%m/%Y")}
    dados = requests.get(url, params=parametros, timeout=60).json()
    cdi = pd.DataFrame(dados)
    cdi["data"] = pd.to_datetime(cdi["data"], format="%d/%m/%Y")
    cdi["cdi"] = cdi["valor"].astype(float) / 100  # 0,040168 % vira 0,00040168
    cdi = cdi.set_index("data")["cdi"].sort_index()
    cdi.to_csv(arquivo)
    return cdi


def carregar_ibovespa():
    """Fechamento oficial do Ibovespa publicado pela B3, ano a ano.

    O Ibovespa é um índice de retorno total: a metodologia da B3 reinveste os proventos.
    Por isso os pontos do índice já representam o retorno com proventos.
    """
    arquivo = PASTA_BRUTOS / "ibovespa_b3.csv"
    if arquivo.exists():
        return pd.read_csv(arquivo, parse_dates=["data"], index_col="data")["ibovespa"]

    valores = {}
    for ano in range(INICIO_HISTORICO.year, DATA_FINAL.year + 1):
        pedido = {"index": "IBOVESPA", "language": "pt-br", "year": str(ano)}
        codigo = base64.b64encode(json.dumps(pedido).encode()).decode()
        url = f"https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{codigo}"
        resposta = requests.get(url, headers=CABECALHO, timeout=60).json()
        for linha in resposta["results"]:
            for mes in range(1, 13):
                texto = linha.get(f"rateValue{mes}")
                if texto:
                    numero = float(texto.replace(".", "").replace(",", "."))
                    valores[pd.Timestamp(ano, mes, int(linha["day"]))] = numero
    ibovespa = pd.Series(valores, name="ibovespa").sort_index()
    ibovespa.index.name = "data"
    ibovespa = ibovespa.loc[:DATA_FINAL]
    ibovespa.to_csv(arquivo)
    return ibovespa


def carregar_correcoes_proventos():
    """Proventos do provedor corrigidos após auditoria, com a fonte de cada correção."""
    return pd.read_csv(PASTA_DADOS / "correcoes_proventos.csv", parse_dates=["data_ex"])


def carregar_proventos_complementares():
    """Proventos dos ativos que nem a brapi nem o Yahoo entregam mais."""
    return pd.read_csv(PASTA_DADOS / "proventos_complementares.csv", parse_dates=["data_ex"])
