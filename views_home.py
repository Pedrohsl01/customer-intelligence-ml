# views_home.py — Landing Page
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from plataforma import ui

# -----------------------------------------------------------------------------
# CSS exclusivo da Home (esconde a sidebar apenas nesta página)
# -----------------------------------------------------------------------------
ui.carregar_css("main.css")

# O que fazer com cada segmento, em uma linha (texto de apresentação)
ACOES = {
    "Clientes VIP": "Fidelidade e acesso antecipado a lançamentos.",
    "Clientes Fiéis": "Benefícios para manter a recorrência.",
    "Clientes Regulares": "Cross-sell para aumentar o ticket.",
    "Clientes Promissores": "Incentivo à segunda compra.",
    "Clientes em Risco": "Contato antes que parem de comprar.",
    "Clientes Inativos": "Reativação com cupom de retorno.",
}


@st.cache_data
def carregar_resumo_demo():
    """Tamanho de cada segmento da base de demonstração, para ilustrar a página."""
    for caminho in (Path("resumo_clusters_rfm.csv"), Path("data/processed/resumo_clusters_rfm.csv")):
        if caminho.exists():
            return pd.read_csv(caminho)[["Segmento", "Quantidade_Clientes"]]
    return None


def milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def painel_da_base(resumo: pd.DataFrame) -> str:
    resumo = resumo.sort_values("Quantidade_Clientes", ascending=False)
    total = int(resumo["Quantidade_Clientes"].sum())
    fatias, itens = [], []
    for _, linha in resumo.iterrows():
        nome, quantidade = linha["Segmento"], int(linha["Quantidade_Clientes"])
        cor = ui.CORES_SEGMENTOS.get(nome, ui.TEXTO_SUAVE)
        parte = quantidade / total
        fatias.append(f'<div class="base__fatia" style="--peso: {parte * 100:.2f}; --cor: {cor}" '
                      f'title="{escape(nome)}: {parte:.0%}"></div>')
        itens.append(
            f'<li class="base__item" style="--cor: {cor}"><b>{escape(nome)}</b>'
            f"<strong>{milhar(quantidade)} <small>clientes, {parte:.0%} da base</small></strong>"
            f"<p>{escape(ACOES.get(nome, ''))}</p></li>"
        )
    return (
        '<section class="base"><div class="base__titulo">'
        f"<h2>Uma base real, separada em {len(resumo)} segmentos</h2>"
        f"<span>{milhar(total)} clientes do dataset público Online Retail</span></div>"
        f'<div class="base__barra" role="img" aria-label="Proporção de clientes em cada segmento">{"".join(fatias)}</div>'
        f'<ul class="base__lista">{"".join(itens)}</ul></section>'
    )


# -----------------------------------------------------------------------------
# TOPO E HERO
# -----------------------------------------------------------------------------
st.markdown(f'<div class="topo">{ui.MARCA_SVG}Customer Intelligence</div>', unsafe_allow_html=True)

st.markdown(
    """
    <div class="hero">
        <h1>Saiba quem são seus clientes e o que dizer a cada um.</h1>
        <p>Envie suas vendas. A plataforma separa a base em segmentos de comportamento e escreve a campanha
        de cada um: e-mail, WhatsApp, push e oferta.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# BOTÕES DE AÇÃO (CTA)
# -----------------------------------------------------------------------------
with st.container(key="hero_acoes"):
    col_demo, col_entrar = st.columns(2)
    with col_demo:
        if st.button("Ver demonstração", type="primary", icon=":material/monitoring:", use_container_width=True):
            st.switch_page("app.py")
    with col_entrar:
        if st.button("Entrar", icon=":material/login:", use_container_width=True):
            st.switch_page("paginas/login.py")

# -----------------------------------------------------------------------------
# A BASE DE DEMONSTRAÇÃO EM SEGMENTOS
# -----------------------------------------------------------------------------
resumo_demo = carregar_resumo_demo()
if resumo_demo is not None:
    st.markdown(painel_da_base(resumo_demo), unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# COMO FUNCIONA (PILARES DA SOLUÇÃO)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <section class="etapas">
        <h2>Como funciona</h2>
        <ol>
            <li>
                <h3>Análise RFM</h3>
                <p>Cada cliente é medido em três pilares: <b>Recência</b> (dias desde a última compra),
                <b>Frequência</b> (total de pedidos) e <b>Monetário</b> (gasto total).</p>
            </li>
            <li>
                <h3>Clusterização K-Means</h3>
                <p>Um algoritmo de aprendizado não supervisionado agrupa a base automaticamente,
                revelando padrões de comportamento.</p>
            </li>
            <li>
                <h3>IA generativa e CRM</h3>
                <p>Para cada grupo, uma LLM (via Groq) escreve o diagnóstico comportamental,
                a ação recomendada e as mensagens prontas para envio.</p>
            </li>
        </ol>
    </section>
    <footer class="rodape">
        <span>Python, Pandas, Scikit-Learn, Groq API, Plotly e Streamlit</span>
        <span>Projeto end-to-end de machine learning</span>
    </footer>
    """,
    unsafe_allow_html=True,
)
