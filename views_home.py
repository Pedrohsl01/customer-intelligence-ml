# views_home.py
import streamlit as st
from pathlib import Path

# -----------------------------------------------------------------------------
# Carregar CSS main
# -----------------------------------------------------------------------------
def carregar_css_main():
    # Encontra o arquivo main.css independente de onde o script estiver
    diretorio_atual = Path(__file__).resolve().parent
    caminhos_possiveis = [
        diretorio_atual / "assets" / "main.css",
        diretorio_atual / "app" / "assets" / "main.css",
        Path("assets/main.css").resolve(),
    ]
    
    for caminho in caminhos_possiveis:
        if caminho.exists():
            with open(caminho, "r", encoding="utf-8") as f:
                st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
            break

# Aplica o CSS exclusivo da Home
carregar_css_main()

# ----------------------------------------------------------------------------- <<<----
# -----------------------------------------------------------------------------
# HERO SECTION (CABEÇALHO PRINCIPAL)
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-container">
        <h1 class="hero-title">🛍️ Customer Intelligence Platform</h1>
        <p class="hero-subtitle">
            Segmentação Avançada de Clientes por Aprendizado de Máquina & Geração Automatizada de Personas via IA Generativa
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# -----------------------------------------------------------------------------
# BOTÃO DE AÇÃO PRINCIPAL (CTA)
# -----------------------------------------------------------------------------
col_space1, col_btn, col_space2 = st.columns([1, 2, 1])
with col_btn:
    if st.button("🚀 Acessar Dashboard Interativo", use_container_width=True):
        st.switch_page("app.py")

st.markdown("---")

# -----------------------------------------------------------------------------
# PILARES DA SOLUÇÃO (CARDS INFORMATIVOS)
# -----------------------------------------------------------------------------
st.subheader("💡 O que você encontrará no Dashboard?")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
        <div class="feature-card">
            <h3>📊 Análise RFM</h3>
            <p>Mapeamento detalhado dos clientes com base nos pilares de <b>Recência</b> (dias da última compra), <b>Frequência</b> (total de pedidos) e <b>Monetário</b> (gasto total).</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        """
        <div class="feature-card">
            <h3>🤖 Clusterização K-Means</h3>
            <p>Agrupamento automático da base através de algoritmos de Aprendizado Não-Supervisionado para identificação de padrões comportamentais.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col3:
    st.markdown(
        """
        <div class="feature-card">
            <h3>🎯 IA Generativa & CRM</h3>
            <p>Diagnósticos comportamentais detalhados e sugestões automáticas de copies de notificação push geradas por LLM (Llama 3.1 via Groq).</p>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# RODAPÉ DE TECH STACK
# -----------------------------------------------------------------------------
st.markdown("---")
col_tech1, col_tech2 = st.columns([2, 1])

with col_tech1:
    st.caption("⚙️ **Tecnologias Utilizadas:** Python | Pandas | Scikit-Learn | Groq API (Llama 3.1) | Plotly | Streamlit")

with col_tech2:
    st.caption("📌 **Projeto End-to-End de Machine Learning**")