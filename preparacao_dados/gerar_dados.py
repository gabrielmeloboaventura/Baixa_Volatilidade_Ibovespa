# gerar_dados.py
# Prepara os arquivos da pasta dados/ usados por baixa_volatilidade.py.
# Não é preciso rodar de novo: os arquivos já estão prontos no repositório.
#
# O que este passo faz (detalhes nos comentários de coleta.py e calculos.py):
#   1. Lê o fechamento oficial e o volume financeiro da B3 (arquivos COTAHIST).
#   2. Monta o preço ajustado por proventos e desdobramentos de cada ação:
#      brapi quando liberada, senão fechamento oficial + proventos do Yahoo,
#      com as correções de dados/correcoes_proventos.csv (cada uma com fonte).
#   3. Junta códigos que mudaram (ex.: TRPL4 virou ISAE4), trata a conversão
#      da Copel (CPLE6 em CPLE3 + resgate de R$ 0,7749 em novembro de 2025) e as
#      incorporações de dados/incorporacoes.csv (BRFS3 pela Marfrig em 2025).
#   4. Baixa o CDI do Banco Central e o Ibovespa oficial da B3.
#
# Uso: python preparacao_dados/gerar_dados.py

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import calculos
import coleta
from config import DATA_FINAL, INICIO_HISTORICO

DESTINO = Path(__file__).resolve().parent.parent / "dados"
DESTINO.mkdir(exist_ok=True)

universo = coleta.carregar_universo()
mapa = coleta.carregar_mapa_tickers()
setores = coleta.carregar_setores()
codigos = sorted({c for texto in mapa["codigos_cotahist"] for c in texto.split(",")})
cotacoes, calendario = coleta.carregar_cotahist(codigos)
calendario = calendario[(calendario >= INICIO_HISTORICO) & (calendario <= DATA_FINAL)]

precos, origem = calculos.montar_precos(universo, mapa, cotacoes, calendario, coleta.carregar_correcoes_proventos(),
                                        coleta.carregar_proventos_complementares(), DATA_FINAL)
# Incorporações: depois do último pregão, a ação vira ações da empresa que a incorporou.
# O valor da posição passa a seguir o preço ajustado do sucessor, na proporção da troca.
incorporacoes = pd.read_csv(Path(__file__).resolve().parent / "dados/incorporacoes.csv", parse_dates=["ultimo_pregao"])
for _, linha in incorporacoes.iterrows():
    ticker, sucessor, ultimo = linha["ticker"], linha["sucessor"], linha["ultimo_pregao"]
    fechamento = calculos.fechamento_oficial(ticker, mapa, cotacoes, calendario)["fechamento"].loc[ultimo]
    fechamento_sucessor = calculos.fechamento_oficial(sucessor, mapa, cotacoes, calendario)["fechamento"].loc[ultimo]
    troca = linha["proporcao"] * fechamento_sucessor / fechamento   # valor recebido por real investido
    depois = precos.index > ultimo
    precos.loc[depois, ticker] = (precos.loc[ultimo, ticker] * troca
                                  * precos.loc[depois, sucessor] / precos.loc[ultimo, sucessor])
    print(f"{ticker} incorporada por {sucessor} em {ultimo:%d/%m/%Y} (troca vale {troca:.4f} da posição)")

volume = pd.DataFrame({t: calculos.fechamento_oficial(t, mapa, cotacoes, calendario)["volume_financeiro"]
                       for t in universo["ticker"]})

universo.assign(setor=universo["ticker"].map(setores))[["ticker", "empresa", "setor"]] \
    .to_csv(DESTINO / "universo.csv", index=False)
precos.rename_axis("data").to_csv(DESTINO / "precos_ajustados.csv", float_format="%.10g")
volume.rename_axis("data").to_csv(DESTINO / "volume_financeiro.csv", float_format="%.2f")
coleta.carregar_cdi().to_csv(DESTINO / "cdi.csv")
coleta.carregar_ibovespa().to_csv(DESTINO / "ibovespa.csv")
origem.to_csv(DESTINO / "origem_dos_precos.csv", index=False)
print(f"Arquivos gravados em {DESTINO}")
