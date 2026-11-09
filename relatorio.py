# relatorio.py
# Monta o relatório HTML. As imagens ficam embutidas no próprio arquivo, então ele abre
# no navegador sem depender de outros arquivos. Os textos de resultado são calculados a
# partir dos números: nenhuma conclusão está escrita de antemão.

import base64
import html

from config import (CAPITAL_INICIAL, DATA_COMPRA, DATA_FINAL, DATA_SELECAO, JANELA_PRINCIPAL, LIQUIDEZ_MINIMA,
                    PASTA_RESULTADOS)


def reais(valor):
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def pct(valor, casas=2):
    return f"{valor * 100:.{casas}f}%".replace(".", ",")


def num(valor, casas=2):
    return "n/a" if valor != valor else f"{valor:.{casas}f}".replace(".", ",")


def milhoes(valor):
    return f"R$ {valor / 1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_html(dados, colunas, formatos=None, classe=""):
    """Transforma um DataFrame em tabela. colunas = {coluna: título}."""
    formatos = formatos or {}
    cabecalho = "".join(f"<th>{html.escape(t)}</th>" for t in colunas.values())
    linhas = []
    for _, linha in dados.iterrows():
        celulas = ""
        for coluna in colunas:
            valor = linha[coluna]
            texto = formatos[coluna](valor) if coluna in formatos else str(valor)
            celulas += f"<td>{html.escape(texto)}</td>"
        linhas.append(f"<tr>{celulas}</tr>")
    return f'<div class="tabela {classe}"><table><thead><tr>{cabecalho}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>'


def imagem(nome, descricao):
    conteudo = base64.b64encode((PASTA_RESULTADOS / nome).read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{conteudo}" alt="{html.escape(descricao)}"></figure>'


def texto_discussao(indicadores, comparacao, contribuicao, por_ano):
    """Escreve a discussão a partir dos números calculados."""
    lv, ib, cdi = indicadores.loc["Low Volatility"], indicadores.loc["Ibovespa"], indicadores.loc["CDI"]
    p = []
    if lv["volatilidade_anualizada"] < ib["volatilidade_anualizada"]:
        p.append(f"A carteira apresentou menor volatilidade que o Ibovespa: {pct(lv['volatilidade_anualizada'])} contra "
                 f"{pct(ib['volatilidade_anualizada'])} ao ano, uma redução de "
                 f"{pct(-comparacao['variacao_percentual_volatilidade'], 1)}. Nesse ponto, a hipótese foi confirmada no período.")
    else:
        p.append(f"A carteira não apresentou menor volatilidade que o Ibovespa: {pct(lv['volatilidade_anualizada'])} contra "
                 f"{pct(ib['volatilidade_anualizada'])} ao ano. Nesse ponto, a hipótese não foi confirmada no período.")

    if abs(lv["maximo_drawdown"]) < abs(ib["maximo_drawdown"]):
        p.append(f"A maior queda da carteira ({pct(lv['maximo_drawdown'])}) foi menor que a do Ibovespa ({pct(ib['maximo_drawdown'])}).")
    else:
        p.append(f"A maior queda da carteira ({pct(lv['maximo_drawdown'])}) não foi menor que a do Ibovespa ({pct(ib['maximo_drawdown'])}).")

    relacao_ib = "superior" if lv["retorno_acumulado"] > ib["retorno_acumulado"] else "inferior"
    relacao_cdi = "superior" if lv["retorno_acumulado"] > cdi["retorno_acumulado"] else "inferior"
    p.append(f"Em rentabilidade, a carteira acumulou {pct(lv['retorno_acumulado'])}, resultado {relacao_ib} ao Ibovespa "
             f"({pct(ib['retorno_acumulado'])}, diferença de {num(comparacao['diferenca_retorno_ibov_pp'])} p.p.) e "
             f"{relacao_cdi} ao CDI ({pct(cdi['retorno_acumulado'])}, diferença de {num(comparacao['diferenca_retorno_cdi_pp'])} p.p.).")

    relacao_sharpe = "maior" if lv["sharpe"] > ib["sharpe"] else "menor"
    sinal = "A carteira rendeu mais que o CDI no período." if lv["sharpe"] > 0 else "A carteira não rendeu mais que o CDI no período."
    p.append(f"O Sharpe da carteira foi {num(lv['sharpe'])}, {relacao_sharpe} que o do Ibovespa ({num(ib['sharpe'])}). "
             f"{sinal} O Sharpe mede esse excesso por unidade de risco total, sem separar outros fatores.")

    positivas = contribuicao[contribuicao["contribuicao"] > 0]
    negativas = contribuicao[contribuicao["contribuicao"] < 0]
    maior, menor = contribuicao.iloc[0], contribuicao.iloc[-1]
    p.append(f"Na análise individual, {len(positivas)} ações contribuíram positivamente e {len(negativas)} negativamente. "
             f"A maior contribuição foi de {maior['ticker']} ({num(maior['contribuicao'] * 100)} p.p.) e a menor foi de "
             f"{menor['ticker']} ({num(menor['contribuicao'] * 100)} p.p.). Estes números mostram quanto cada ação somou, "
             "não por que ela subiu ou caiu: o estudo não testa causas.")
    if negativas.empty:
        p.append("Nenhuma ação prejudicou o resultado em termos absolutos, pois todas terminaram com retorno positivo. "
                 "As de menor contribuição apenas somaram menos.")
    else:
        p.append("Prejudicaram o resultado: " + ", ".join(negativas["ticker"]) + ".")
    return "".join(f"<p>{t}</p>" for t in p)


def gerar_relatorio(universo, elegibilidade, ranking, selecionadas, origem, correcoes, indicadores, por_ano, comparacao,
                    custos, contribuicao, sensibilidade, valores, datas):
    excluidos = elegibilidade[~elegibilidade["elegivel"]]
    corte = selecionadas["vol_252"].iloc[-1]
    proximo = ranking.iloc[len(selecionadas)]
    lv, ib = indicadores.loc["Low Volatility"], indicadores.loc["Ibovespa"]
    menor_vol = lv["volatilidade_anualizada"] < ib["volatilidade_anualizada"]
    maior_ret_ib = lv["retorno_acumulado"] > ib["retorno_acumulado"]
    fontes = origem["fonte_preco"].value_counts()
    fechamentos = int(origem["fechamentos_corrigidos"].sum())

    f_vol = {c: (lambda v: pct(v, 2) if v == v else "n/a") for c in ["vol_63", "vol_126", "vol_252", "max_drawdown_hist"]}
    t_ranking = tabela_html(ranking, {"posicao": "Posição", "empresa": "Empresa", "ticker": "Ticker", "setor": "Setor",
                                      "vol_63": "Vol. 63", "vol_126": "Vol. 126", "vol_252": "Vol. 252",
                                      "max_drawdown_hist": "Máx. drawdown", "liquidez_media_63": "Liquidez média",
                                      "freq_retorno_zero": "Retornos zero"},
                            {**f_vol, "liquidez_media_63": milhoes, "freq_retorno_zero": lambda v: pct(v, 1)}, "alta")
    t_elegib = tabela_html(elegibilidade.sort_values("ticker").assign(sit=lambda d: d["elegivel"].map({True: "Elegível", False: "Excluído"})),
                           {"ticker": "Ticker", "empresa": "Empresa", "retornos_validos_252": "Retornos válidos",
                            "liquidez_media_63": "Liquidez média", "presenca_63": "Presença", "maior_salto": "Maior salto",
                            "sit": "Situação", "motivo_exclusao": "Motivo"},
                           {"liquidez_media_63": milhoes, "presenca_63": lambda v: pct(v, 0), "maior_salto": lambda v: pct(v, 1)}, "alta")
    t_excl = tabela_html(excluidos, {"ticker": "Ticker", "empresa": "Empresa", "motivo_exclusao": "Motivo"})
    t_carteira = tabela_html(selecionadas.assign(peso="10%", inv=CAPITAL_INICIAL / len(selecionadas)),
                             {"posicao": "Posição", "empresa": "Empresa", "ticker": "Ticker", "setor": "Setor",
                              "vol_252": "Vol. 252", "peso": "Peso inicial", "inv": "Valor investido"},
                             {"vol_252": lambda v: pct(v), "inv": reais})
    t_ind = tabela_html(indicadores.reset_index(names="alt"),
                        {"alt": "Alternativa", "valor_final": "Valor final", "retorno_acumulado": "Retorno acumulado",
                         "retorno_anualizado": "Retorno anualizado", "volatilidade_anualizada": "Volatilidade",
                         "maximo_drawdown": "Máx. drawdown", "sharpe": "Sharpe"},
                        {"valor_final": reais, "retorno_acumulado": pct, "retorno_anualizado": pct,
                         "volatilidade_anualizada": pct, "maximo_drawdown": pct, "sharpe": num})
    t_ano = tabela_html(por_ano.reset_index(), {"periodo": "Período", "Low Volatility": "Low Volatility", "Ibovespa": "Ibovespa", "CDI": "CDI"},
                        {"Low Volatility": pct, "Ibovespa": pct, "CDI": pct})
    t_custos = tabela_html(custos.reset_index(names="c"), {"c": "Cenário", "valor_final": "Valor final", "retorno_acumulado": "Retorno acumulado"},
                           {"valor_final": reais, "retorno_acumulado": pct})
    t_contrib = tabela_html(contribuicao, {"empresa": "Empresa", "ticker": "Ticker", "vol_252": "Vol. seleção", "peso_inicial": "Peso inicial",
                                           "valor_inicial": "Valor inicial", "retorno_acumulado": "Retorno", "contribuicao": "Contribuição",
                                           "valor_final": "Valor final", "peso_final": "Peso final"},
                            {"vol_252": pct, "peso_inicial": lambda v: pct(v, 1), "valor_inicial": reais, "retorno_acumulado": pct,
                             "contribuicao": lambda v: f"{num(v * 100)} p.p.", "valor_final": reais, "peso_final": lambda v: pct(v, 1)})
    t_sens = tabela_html(sensibilidade.reset_index(names="c"), {"c": "Carteira", "retorno_acumulado": "Retorno acumulado", "volatilidade_anualizada": "Volatilidade",
                                                                 "sharpe": "Sharpe", "maximo_drawdown": "Máx. drawdown", "valor_final": "Valor final"},
                         {"retorno_acumulado": pct, "volatilidade_anualizada": pct, "sharpe": num, "maximo_drawdown": pct, "valor_final": reais})
    t_correcoes = tabela_html(correcoes.assign(d=correcoes["data_ex"].dt.strftime("%d/%m/%Y")),
                              {"ticker": "Ticker", "d": "Data ex", "valor_yahoo_bruto": "Yahoo", "valor_correto_bruto": "Valor usado", "motivo": "Motivo", "fonte": "Fonte"},
                              {"valor_yahoo_bruto": lambda v: num(v, 4), "valor_correto_bruto": lambda v: num(v, 4)})
    t_origem = tabela_html(origem[origem["ticker"].isin(selecionadas["ticker"])],
                           {"ticker": "Ticker", "ticker_consultado": "Consultado como", "fonte_preco": "Fonte do preço", "motivo_brapi": "Resposta da brapi",
                            "fechamentos_corrigidos": "Fechamentos corrigidos", "proventos_corrigidos": "Proventos corrigidos ou complementares"})

    if menor_vol and not maior_ret_ib:
        sintese = "A carteira foi menos volátil que o Ibovespa, mas rendeu menos que ele."
    elif menor_vol and maior_ret_ib:
        sintese = "A carteira foi menos volátil que o Ibovespa e também rendeu mais que ele."
    elif not menor_vol and maior_ret_ib:
        sintese = "A carteira não foi menos volátil que o Ibovespa, embora tenha rendido mais."
    else:
        sintese = "A carteira não foi menos volátil que o Ibovespa e também rendeu menos."

    cartoes = "".join(f'<div class="cartao"><span>{r}</span><strong>{v}</strong><small>{d}</small></div>' for r, v, d in [
        ("Valor final", reais(lv["valor_final"]), f"Ibovespa: {reais(ib['valor_final'])}"),
        ("Retorno acumulado", pct(lv["retorno_acumulado"]), f"Ibovespa: {pct(ib['retorno_acumulado'])}"),
        ("Volatilidade", pct(lv["volatilidade_anualizada"]), f"Ibovespa: {pct(ib['volatilidade_anualizada'])}"),
        ("Máx. drawdown", pct(lv["maximo_drawdown"]), f"Ibovespa: {pct(ib['maximo_drawdown'])}"),
    ])

    corpo = f"""
<header><p class="sobre">Trabalho acadêmico de programação</p>
<h1>Factor Investing: fator Baixa Volatilidade na B3</h1>
<p class="sub">Carteira de {len(selecionadas)} ações formada em {DATA_COMPRA:%d/%m/%Y} e avaliada em {DATA_FINAL:%d/%m/%Y}.</p>
<p class="sintese">{sintese}</p><div class="cartoes">{cartoes}</div></header>

<h2>1. Introdução ao Factor Investing</h2>
<p>Factor Investing é uma forma de montar carteiras escolhendo ações por uma característica mensurável, como tamanho, valor ou risco, em vez de analisar cada empresa de forma subjetiva. A regra é definida antes e aplicada a todo o universo, o que permite testá-la com dados históricos.</p>

<h2>2. O fator Baixa Volatilidade</h2>
<p>Volatilidade mede quanto o retorno de uma ação oscila em torno da própria média. O fator Baixa Volatilidade escolhe as ações que menos oscilaram no passado. A classificação é relativa ao universo: não existe um limite que define uma ação como boa ou ruim. Este trabalho analisa somente esse fator, sem comparar outros fatores e sem usar correlação, covariância ou otimização de pesos.</p>

<h2>3. Objetivo e hipótese</h2>
<p>O objetivo é verificar se uma carteira de ações de menor volatilidade histórica teve de fato menor risco no período e como foi seu desempenho financeiro.</p>
<blockquote>Uma carteira selecionada com base em ações de menor volatilidade histórica tende a apresentar oscilações mais moderadas do que o mercado, podendo proporcionar uma relação entre risco e retorno interessante para o investidor.</blockquote>

<h2>4. Período do estudo</h2>
<ul><li><b>Seleção:</b> {DATA_SELECAO:%d/%m/%Y}, após o fechamento. Histórico a partir de janeiro de 2023.</li>
<li><b>Compra:</b> fechamento de {DATA_COMPRA:%d/%m/%Y}. O dia 29/03/2024 foi feriado, então o primeiro retorno da carteira é de 01/04/2024.</li>
<li><b>Avaliação final:</b> {DATA_FINAL:%d/%m/%Y}, a mercado, em {len(datas) - 1} retornos diários.</li></ul>
<p>Para evitar look-ahead bias, as séries usadas na seleção são montadas já cortadas em {DATA_SELECAO:%d/%m/%Y}, e a função de indicadores recusa qualquer dado posterior. Os dados seguintes só são lidos depois de a carteira estar definida.</p>

<h2>5. Universo e critérios de elegibilidade</h2>
<p>O universo é a carteira teórica do Ibovespa vigente de janeiro a abril de 2024: {len(universo)} ativos de {universo['empresa'].nunique()} empresas. A lista veio da tabela publicada pela B3 e foi conferida com a captura da API oficial em 14/04/2024: os 87 códigos coincidem. A composição atual do índice não foi usada. O universo não tem ETFs, FIIs nem BDRs. Empresas que depois mudaram de ticker ou saíram da bolsa foram mantidas.</p>
<p>Critérios, todos com dados até a seleção:</p>
<ol><li>Pertencer ao universo.</li><li>Ter {JANELA_PRINCIPAL} retornos diários válidos seguidos (253 preços).</li>
<li>Ter volume financeiro médio de pelo menos {reais(LIQUIDEZ_MINIMA)} por dia em 63 pregões, para que a carteira hipotética seja negociável, e negociação em pelo menos 95% desses pregões, para que a volatilidade não fique artificialmente baixa por falta de negócios.</li>
<li>Ter série consistente: nenhum retorno ajustado acima de 40% em módulo, sinal de evento societário sem ajuste.</li>
<li>Um instrumento por empresa: fica a classe mais líquida. A regra usa liquidez, não volatilidade, para não favorecer o resultado.</li></ol>
<p>{len(ranking)} ativos ficaram elegíveis e {len(excluidos)} foram excluídos. O filtro de liquidez excluiu {int((elegibilidade["liquidez_media_63"] < LIQUIDEZ_MINIMA).sum())} ativos, e a menor liquidez do universo foi de {milhoes(elegibilidade["liquidez_media_63"].min())} por dia.</p>
{t_excl}
<details><summary>Tabela completa de elegibilidade ({len(elegibilidade)} ativos)</summary>{t_elegib}</details>

<h2>6. Fontes dos dados</h2>
<ul><li><b>B3 COTAHIST:</b> fechamento oficial e volume financeiro em reais de todos os ativos, inclusive os que saíram da bolsa.</li>
<li><b>brapi:</b> consultada primeiro para cada ativo. Sem token, só libera PETR4, VALE3, ITUB4 e MGLU3. O plano gratuito com token limita o histórico a 3 meses.</li>
<li><b>Yahoo Finance:</b> proventos e desdobramentos dos demais ativos, com auditoria.</li>
<li><b>Fundamentus:</b> tabela usada para auditar os proventos do Yahoo e para os ativos sem provedor.</li>
<li><b>Banco Central:</b> CDI diário, série SGS 12, convertido de % ao dia para decimal.</li>
<li><b>B3 índices:</b> fechamento diário oficial do Ibovespa, índice de retorno total.</li></ul>
<p>Distribuição de fontes de preço nos {len(origem)} ativos: {"; ".join(f"{k}: {v}" for k, v in fontes.items())}. O arquivo <code>origem_dados.csv</code> traz a origem de cada ativo.</p>
<p><b>Por que o fechamento oficial substituiu o do Yahoo.</b> A comparação com o COTAHIST achou {fechamentos} fechamentos divergentes no período de seleção. Exemplo: em 08/03/2024 a PETR4 caiu 10,57% no dado oficial e 9,14% no Yahoo. Por isso o preço vem da B3 e o Yahoo contribui com os eventos. A brapi trouxe o valor correto nesse exemplo.</p>
<p><b>Proventos corrigidos.</b> A auditoria achou proventos ausentes ou com valor errado no Yahoo. As correções estão abaixo. A mais relevante foi na TIMS3, cuja volatilidade subia de forma artificial.</p>
{t_correcoes}
<h3>Origem dos dados da carteira</h3>{t_origem}

<h2>7. Metodologia de cálculo da volatilidade</h2>
<p class="formula">Retorno diário = (Preço ajustado atual / Preço ajustado anterior) − 1</p>
<p class="formula">Volatilidade anualizada = desvio-padrão amostral dos últimos 252 retornos (ddof=1) × √252</p>
<p>O preço ajustado considera proventos e desdobramentos. No dia ex, o retorno é fechamento atual / (fechamento anterior − provento) − 1, o que equivale a reinvestir o provento na própria ação. Cada provento entra uma única vez e nada é somado depois, então não há dupla contagem. Valores ausentes não são preenchidos: um dia sem negócio invalida os retornos em volta dele.</p>
<p>Volatilidades de 63 e 126 pregões, máximo drawdown e frequência de retornos zero são apenas complementares. O ranking usa só a janela de 252 pregões.</p>

<h2>8. Ranking das empresas</h2>
<p>Ordem crescente de volatilidade de 252 pregões. Em empate, vale a maior liquidez e depois a ordem alfabética do ticker. Liquidez é o volume financeiro médio de 63 pregões.</p>
{t_ranking}

<h2>9. Composição da carteira</h2>
<p>As {len(selecionadas)} primeiras do ranking foram selecionadas porque têm as menores volatilidades entre as elegíveis. O corte ficou em {pct(corte)} ({selecionadas['ticker'].iloc[-1]}). A primeira fora da carteira foi {proximo['ticker']}, com {pct(proximo['vol_252'])}.</p>
{t_carteira}

<h2>10. Simulação do investimento</h2>
<p>Capital de {reais(CAPITAL_INICIAL)}, com R$ 10.000 por ação no fechamento de {DATA_COMPRA:%d/%m/%Y}. A estratégia é buy and hold: as quantidades são calculadas uma vez e mantidas, sem aportes, retiradas, alavancagem ou rebalanceamento. Os pesos variam com os preços. Admitem-se quantidades fracionárias, uma simplificação teórica para aplicar exatamente 10% em cada ação. O reinvestimento de proventos está embutido no preço ajustado.</p>
<p><b>Evento societário na carteira:</b> a CPLE6 negociou até 07/11/2025. Na migração da Copel para o Novo Mercado, cada ação foi convertida em uma ação ordinária (CPLE3) mais uma ação PNC resgatada por R$ 0,7749. A posição continua na CPLE3, e o resgate foi tratado como provento em 10/11/2025, embora o pagamento previsto fosse em 30/12/2025. Os preços confirmam a equivalência: CPLE3 a R$ 13,46 mais R$ 0,77 dão R$ 14,23, perto dos R$ 14,26 da CPLE6 em 07/11/2025.</p>
<h3>Custo hipotético de entrada</h3>
<p>O cenário principal é sem custos. O complementar cobra 0,10% sobre o valor comprado. A avaliação final é a mercado, sem simular venda. Impostos não estão incluídos.</p>
{t_custos}

<h2>11. Resultados e indicadores</h2>
{t_ind}
<p><b>Retorno anualizado:</b> (1 + retorno acumulado)^(252 / número de retornos) − 1.</p>
<p class="formula">Sharpe = média(retorno diário − CDI diário) / desvio-padrão amostral(retorno diário) × √252</p>
<p>O Sharpe não se aplica ao CDI, pois ele é a própria referência.</p>
<h3>Rentabilidade por período</h3>{t_ano}

<h2>12. Comparação com Ibovespa e CDI</h2>
<ul><li>Diferença de volatilidade em relação ao Ibovespa: {num(comparacao['diferenca_volatilidade_pp'])} p.p.</li>
<li>Variação percentual da volatilidade em relação ao Ibovespa: {pct(comparacao['variacao_percentual_volatilidade'], 1)}</li>
<li>Diferença de retorno acumulado em relação ao Ibovespa: {num(comparacao['diferenca_retorno_ibov_pp'])} p.p.</li>
<li>Diferença de retorno acumulado em relação ao CDI: {num(comparacao['diferenca_retorno_cdi_pp'])} p.p.</li></ul>
<p>O CDI usa a taxa de cada dia para remunerar até o dia útil seguinte, incluindo dias com taxa e sem pregão, como 24/12 e 31/12.</p>

<h2>13. Contribuição individual das empresas</h2>
<p>Contribuição = (valor final da posição − valor inicial) / capital inicial. A soma das contribuições é igual ao retorno da carteira.</p>
{t_contrib}

<h2>14. Análise de sensibilidade</h2>
<p>As três carteiras usam o mesmo ranking e pesos iniciais iguais. A carteira principal continua sendo a Top 10, definida antes do backtest, independentemente de qual tenha rendido mais.</p>
{t_sens}
<p>Menor volatilidade: {sensibilidade['volatilidade_anualizada'].idxmin()}. Maior retorno: {sensibilidade['retorno_acumulado'].idxmax()}. Maior Sharpe: {sensibilidade['sharpe'].idxmax()}. A comparação vale para este período e não serve para escolher a carteira depois de ver o resultado.</p>

<h2>15. Gráficos</h2>
{imagem("grafico_1_evolucao.png", "Evolução de R$ 100.000 na carteira, no Ibovespa e no CDI")}
{imagem("grafico_2_ranking.png", "Volatilidade das empresas selecionadas")}
{imagem("grafico_3_retorno.png", "Retorno acumulado")}
{imagem("grafico_4_volatilidade.png", "Volatilidade realizada no backtest")}
{imagem("grafico_5_drawdown.png", "Drawdown da carteira e do Ibovespa")}
{imagem("grafico_6_contribuicao.png", "Contribuição de cada ação")}
{imagem("grafico_7_sensibilidade.png", "Comparação das carteiras Top 5, Top 10 e Top 15")}
{imagem("grafico_8_volatilidade_movel.png", "Volatilidade móvel de 63 pregões")}

<h2>16. Discussão dos resultados</h2>
{texto_discussao(indicadores, comparacao, contribuicao, por_ano)}

<h2>17. Limitações</h2>
<ul><li>A CPLE6 teve a maior contribuição da carteira e entrou por pouco no ranking: {pct(corte)} contra {pct(proximo['vol_252'])} de {proximo['ticker']}. Sua série não vem de um provedor de preço ajustado: ela usa o COTAHIST, proventos da Fundamentus e o tratamento manual da conversão em 2025. Parte do resultado depende dessa série.</li>
<li>O resultado vale para um único período, de cerca de dois anos e três meses, e uma única data de formação. Não permite generalizar para outros períodos.</li>
<li>Os proventos dependem do Yahoo com auditoria pela Fundamentus, que não é fonte oficial. Divergências abaixo de 3% do provento ou de 0,05% do preço não foram corrigidas. Doze ativos, nenhum deles entre os 15 primeiros do ranking, não tinham tabela para auditar.</li>
<li>Foram mantidos os valores do Yahoo para os ativos que ficaram fora do Top 15 quando a divergência ocorreu no período do backtest, pois eles não afetam nenhuma carteira. Na TIMS3 em abril de 2024 o valor do Yahoo foi mantido porque a Fundamentus listava duas parcelas e outra tabela consultada listava ao menos três.</li>
<li>O preço ajustado da brapi é usado como vem nos 4 ativos liberados, sem proventos abertos para auditoria. Com um token do plano Pro, mais ativos passariam para a brapi e os números podem mudar um pouco.</li>
<li>Proventos brutos: o imposto sobre juros sobre capital próprio não é descontado, e nenhum imposto é considerado.</li>
<li>Ativos sem provedor (AZUL4, BRFS3, CIEL3, CPLE6, CRFB3, ELET6, GOLL4, NTCO3, PETZ3, SOMA3) usam a tabela complementar. Para ELET6 e AZUL4 ela não trouxe proventos. A ELET6 foi excluída pela regra de classe, e a AZUL4 ficou longe do corte.</li>
<li>A PCAR3 ficou fora por um salto de preço acima de 40% em um dia, sem ajuste na série. A causa do salto não foi investigada. Sua volatilidade calculada ficou muito acima do corte.</li>
<li>O setor vem do arquivo oficial da B3 de 05/09/2025, não de 2024. CIEL3, CRFB3, NTCO3 e SOMA3 não constam nele.</li>
<li>A liquidez usa o fechamento e o volume oficiais, sem simular impacto de mercado. Quantidades fracionárias não existem como lote padrão.</li></ul>

<h2>18. Conclusão</h2>
<p>{sintese} De {DATA_COMPRA:%d/%m/%Y} a {DATA_FINAL:%d/%m/%Y}, R$ 100.000 na carteira chegaram a {reais(lv['valor_final'])}, contra {reais(ib['valor_final'])} no Ibovespa e {reais(indicadores.loc['CDI', 'valor_final'])} no CDI. A volatilidade foi de {pct(lv['volatilidade_anualizada'])}, contra {pct(ib['volatilidade_anualizada'])} do Ibovespa, e o Sharpe foi de {num(lv['sharpe'])}, contra {num(ib['sharpe'])}.</p>
<p>Esses resultados se referem apenas a este período e a estas premissas. Não são recomendação de investimento nem garantem desempenho futuro.</p>
"""
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Low Volatility B3</title><style>
:root{{--t:#1F2937;--m:#6B7280;--b:#E5E7EB;--f:#F9FAFB;--a:#2A6F97}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--t);font:16px/1.6 Georgia,'Times New Roman',serif}}
main{{max-width:980px;margin:auto;padding:32px 16px 64px}}h1,h2,h3,th,.cartao,summary,.sobre{{font-family:Helvetica,Arial,sans-serif}}
h1{{font-size:32px;line-height:1.2;margin:4px 0 8px}}h2{{font-size:22px;margin:44px 0 12px;padding-top:12px;border-top:1px solid var(--b)}}h3{{font-size:16px;margin:24px 0 8px}}
.sobre{{color:var(--a);font-size:13px;font-weight:700;margin:0}}.sub{{color:var(--m);margin:0 0 16px}}.sintese{{font-size:20px;font-weight:700;margin:0 0 16px}}
.cartoes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}.cartao{{border:1px solid var(--b);border-radius:8px;padding:12px 14px;display:flex;flex-direction:column}}
.cartao span,.cartao small{{color:var(--m);font-size:13px}}.cartao strong{{font-size:22px;margin:2px 0}}
.tabela{{overflow-x:auto;margin:12px 0;border:1px solid var(--b);border-radius:6px}}.alta{{max-height:520px;overflow-y:auto}}
table{{border-collapse:collapse;width:100%;font:13px/1.4 Helvetica,Arial,sans-serif}}th{{position:sticky;top:0;background:var(--f);text-align:left;font-weight:700}}th,td{{padding:7px 10px;border-bottom:1px solid var(--b)}}tr:last-child td{{border-bottom:0}}
figure{{margin:16px 0}}img{{max-width:100%;height:auto;display:block}}blockquote{{margin:12px 0;padding:8px 16px;border-left:3px solid var(--a);background:var(--f)}}
.formula{{font-family:Helvetica,Arial,sans-serif;background:var(--f);padding:10px 14px;border-radius:6px;overflow-x:auto}}summary{{cursor:pointer;font-weight:700;margin:12px 0;font-size:14px}}
code{{font-size:14px}}</style></head><body><main>{corpo}</main></body></html>"""
    caminho = PASTA_RESULTADOS / "relatorio.html"
    caminho.write_text(pagina, encoding="utf-8")
    return caminho
