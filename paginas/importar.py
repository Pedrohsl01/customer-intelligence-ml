"""Importar Dados: upload de vendas, mapeamento de colunas e execução do motor RFM + K-Means."""

import hashlib

import streamlit as st

from customer_intel.limpeza import COLUNAS_OBRIGATORIAS, COLUNAS_OPCIONAIS, detectar_dia_primeiro
from plataforma import estrategias, importacao, opcoes, sessao

NAO_TEM = "— não tem —"

empresa = sessao.empresa_atual()
st.title("📥 Importar Dados")
st.caption(f"As vendas enviadas aqui ficam visíveis apenas para **{empresa['nome']}**.")

if empresa["papel"] not in ("admin", "analista"):
    st.info("Somente administradores e analistas podem importar dados.")
    st.stop()

# Resultado da última importação desta sessão (mostrado após o rerun)
if resultado := st.session_state.pop("resultado_importacao", None):
    seg = resultado.segmentacao
    st.success(f"Base processada: {resultado.transacoes_gravadas:,} vendas gravadas e "
               f"{len(seg.clientes):,} clientes segmentados em {seg.k} grupos.")
    rel = resultado.relatorio
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Linhas lidas", f"{rel['linhas_lidas']:,}")
    c2.metric("Linhas válidas", f"{rel['linhas_validas']:,}")
    c3.metric("Devoluções", f"{rel['devolucoes']:,}")
    c4.metric("Silhouette", f"{seg.silhouette:.3f}", help="Qualidade da separação dos grupos (de -1 a 1).")
    descartadas = {
        "sem cliente ou pedido": rel["sem_cliente"], "data inválida": rel["data_invalida"],
        "preço inválido": rel["preco_invalido"], "quantidade zero": rel["quantidade_zero"],
        "duplicadas": rel["duplicadas"], "já importadas antes": resultado.linhas_ja_importadas,
    }
    if any(descartadas.values()):
        st.caption("Linhas descartadas — " + " · ".join(f"{k}: {v:,}" for k, v in descartadas.items() if v))
    simbolo = opcoes.simbolo_moeda(empresa.get("moeda"))
    st.dataframe(
        seg.resumo[["segmento", "quantidade_clientes", "recency_mediana", "frequency_mediana",
                    "monetary_mediano", "participacao_receita"]].rename(columns={
            "segmento": "Segmento", "quantidade_clientes": "Clientes",
            "recency_mediana": "Dias desde a última compra (mediana)",
            "frequency_mediana": "Compras (mediana)",
            "monetary_mediano": f"Gasto por cliente ({simbolo}, mediana)",
            "participacao_receita": "% da receita",
        }).style.format({"% da receita": "{:.1%}", f"Gasto por cliente ({simbolo}, mediana)": "{:,.2f}"}),
        hide_index=True, use_container_width=True,
    )
    if aviso_ia := st.session_state.pop("aviso_ia", None):
        st.warning(aviso_ia)
    else:
        st.caption("✨ Personas e estratégias geradas pela IA com o nicho e o tom de voz da empresa.")
    st.page_link("app.py", label="Abrir o dashboard", icon="📊")
    st.divider()

# -----------------------------------------------------------------------------
# 1. Arquivo
# -----------------------------------------------------------------------------
st.subheader("1. Envie o arquivo de vendas")
st.caption("Uma linha por item vendido. Colunas necessárias: pedido, cliente, data, quantidade e preço unitário. "
           "Devoluções entram como linhas de quantidade negativa.")
arquivo = st.file_uploader("Arquivo .csv ou .xlsx", type=list(importacao.EXTENSOES))
if arquivo is None:
    st.stop()

conteudo = arquivo.getvalue()
assinatura = hashlib.sha256(conteudo).hexdigest()
if st.session_state.get("_arquivo_assinatura") != assinatura:
    try:
        with st.spinner("Lendo o arquivo..."):
            st.session_state["_arquivo_df"] = importacao.ler_arquivo(arquivo.name, conteudo)
        st.session_state["_arquivo_assinatura"] = assinatura
    except importacao.ErroImportacao as erro:
        st.error(str(erro))
        st.stop()
bruto = st.session_state["_arquivo_df"]

st.caption(f"{len(bruto):,} linhas e {len(bruto.columns)} colunas encontradas.")
st.dataframe(bruto.head(5), hide_index=True, use_container_width=True)

# -----------------------------------------------------------------------------
# 2. Mapeamento de colunas
# -----------------------------------------------------------------------------
st.subheader("2. Confirme as colunas")
sugestao = importacao.sugerir_mapeamento(list(bruto.columns))
colunas_arquivo = list(bruto.columns)
escolhas: dict[str, str | None] = {}

grade = st.columns(2)
for i, padrao in enumerate(COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS):
    obrigatoria = padrao in COLUNAS_OBRIGATORIAS
    alternativas = colunas_arquivo if obrigatoria else [NAO_TEM] + colunas_arquivo
    sugerida = sugestao[padrao]
    indice = alternativas.index(sugerida) if sugerida in alternativas else (None if obrigatoria else 0)
    escolha = grade[i % 2].selectbox(
        importacao.ROTULOS[padrao] + (" *" if obrigatoria else ""),
        alternativas, index=indice, key=f"map_{padrao}_{assinatura[:8]}",
        placeholder="Escolha a coluna",
    )
    escolhas[padrao] = None if escolha in (None, NAO_TEM) else escolha

# -----------------------------------------------------------------------------
# 3. Opções
# -----------------------------------------------------------------------------
st.subheader("3. Opções")
col_data, col_modo, col_k = st.columns(3)

dia_primeiro = True
if escolhas["data_compra"]:
    detectado = detectar_dia_primeiro(bruto[escolhas["data_compra"]])
    padrao_dia = detectado if detectado is not None else empresa.get("moeda") == "BRL"
    formato = col_data.radio(
        "Formato das datas", ["Dia/Mês/Ano", "Mês/Dia/Ano"], index=0 if padrao_dia else 1,
        help="Só importa para datas como 03/04/2024. Datas no formato 2024-04-03 são lidas direto.",
    )
    dia_primeiro = formato == "Dia/Mês/Ano"

modo = col_modo.radio(
    "O que fazer com as vendas já importadas?",
    [importacao.SUBSTITUIR, importacao.ACRESCENTAR],
    format_func={importacao.SUBSTITUIR: "Substituir pela base deste arquivo",
                 importacao.ACRESCENTAR: "Acrescentar as vendas novas"}.get,
    help="Ao acrescentar, vendas idênticas às já importadas são ignoradas.",
)
k = col_k.select_slider("Número de segmentos (K)", options=[3, 4, 5, 6], value=4,
                        help="4 costuma equilibrar bem detalhe e facilidade de ação.")

# -----------------------------------------------------------------------------
# 4. Processar
# -----------------------------------------------------------------------------
faltando = [importacao.ROTULOS[p] for p in COLUNAS_OBRIGATORIAS if not escolhas[p]]
escolhidas = [c for c in escolhas.values() if c]
repetidas = sorted({c for c in escolhidas if escolhidas.count(c) > 1})
if faltando:
    st.warning("Escolha as colunas obrigatórias: " + ", ".join(faltando) + ".")
elif repetidas:
    st.warning("A mesma coluna do arquivo foi usada mais de uma vez: " + ", ".join(repetidas) + ".")

if st.button("⚙️ Processar Base", type="primary", disabled=bool(faltando or repetidas)):
    mapeamento = {coluna: padrao for padrao, coluna in escolhas.items() if coluna}
    barra = st.progress(0.0, text="Iniciando...")
    try:
        resultado = importacao.processar_base(
            sessao.cliente(), empresa["id"], bruto, mapeamento, arquivo.name,
            k=k, modo=modo, dia_primeiro=dia_primeiro,
            ao_progredir=lambda etapa, fracao: barra.progress(min(fracao, 1.0), text=etapa),
        )
    except importacao.ErroImportacao as erro:
        barra.empty()
        st.error(str(erro))
        st.stop()
    st.session_state["resultado_importacao"] = resultado

    # Personas por IA: uma falha aqui não invalida a importação (dá para gerar depois no dashboard).
    if not estrategias.ia_disponivel():
        st.session_state["aviso_ia"] = "As personas não foram geradas: a IA não está configurada neste ambiente."
    else:
        try:
            estrategias.gerar_e_salvar(
                sessao.cliente(), estrategias.cliente_llm(), empresa, resultado.execucao_id,
                ao_progredir=lambda segmento, i, n: barra.progress(1.0, text=f"Gerando persona {i}/{n}: {segmento}"),
            )
        except Exception as erro:
            detalhe = str(erro) if isinstance(erro, estrategias.ErroEstrategias) else "erro ao gravar as personas."
            st.session_state["aviso_ia"] = f"Os segmentos foram gravados, mas as personas não: {detalhe} "                                            "Use “Gerar personas com IA” no dashboard."
    for chave in ("_arquivo_df", "_arquivo_assinatura", "_cache_dashboard_chave", "_cache_dashboard_dados"):
        st.session_state.pop(chave, None)
    st.rerun()
