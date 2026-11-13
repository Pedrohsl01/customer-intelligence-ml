from pathlib import Path

import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
import os

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# Dicionário de cores para os gráficos (usado no Plotly)
# -----------------------------------------------------------------------------
CORES_SEGMENTOS = {
    "Clientes VIP": "#00CC96",          # Verde destaque (ou #EF553B / #636EFA)
    "Clientes Promissores": "#636EFA",  # Azul
    "Clientes Regulares": "#AB63FA",    # Roxo
    "Clientes Inativos": "#EF553B"      # Vermelho/Laranja alerta
}

# -----------------------------------------------------------------------------
# Carregar CSS personalizado
# -----------------------------------------------------------------------------

def carregar_css():
    # 1. Obtém o diretório onde o próprio script app.py está localizado
    diretorio_atual = Path(__file__).resolve().parent
    
    # 2. Lista de possíveis caminhos onde o style.css pode estar
    caminhos_possiveis = [
        diretorio_atual / "assets" / "style.css",          # Se estiver em assets/style.css na mesma pasta de app.py
        diretorio_atual / "app" / "assets" / "style.css",    # Se estiver em app/assets/style.css
        Path("assets/style.css").resolve(),               # Em relação ao diretório de execução atual
        Path("app/assets/style.css").resolve()            # Em relação ao diretório de execução atual com app/
    ]
    
    css_encontrado = None
    for caminho in caminhos_possiveis:
        if caminho.exists() and caminho.is_file():
            css_encontrado = caminho
            break
            
    if css_encontrado:
        with open(css_encontrado, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"⚠️ Arquivo style.css não foi localizado. Locais testados: {[str(c) for c in caminhos_possiveis]}")

# Chame a função logo após o st.set_page_config()
carregar_css()

# -----------------------------------------------------------------------------
# CARREGAMENTO DOS ARTEFATOS (CACHE PARA ALTA PERFORMANCE)
# -----------------------------------------------------------------------------
@st.cache_data
def carregar_dados():
    def buscar_caminho(nome_arquivo):
        # Procura na raiz, na pasta atual ou dentro de notebooks/
        caminhos = [
            nome_arquivo,
            os.path.join("..", nome_arquivo),
            os.path.join("notebooks", nome_arquivo),
            os.path.join("data", nome_arquivo)
        ]
        for caminho in caminhos:
            if os.path.exists(caminho):
                return caminho
        raise FileNotFoundError(f"Arquivo '{nome_arquivo}' não foi encontrado em nenhuma das pastas do projeto.")

    path_rfm = buscar_caminho("rfm_segmented_customers.csv")
    path_resumo = buscar_caminho("resumo_clusters_rfm.csv")
    path_personas = buscar_caminho("personas.json")

    rfm = pd.read_csv(path_rfm)
    resumo = pd.read_csv(path_resumo)
    with open(path_personas, "r", encoding="utf-8") as f:
        personas = json.load(f)
        
    return rfm, resumo, personas

# Executa a função primeiro para garantir que df_rfm exista!
# TENTATIVA DE CARREGAR OS ARTEFATOS, CASO OCORRA ERRO, EXIBE MENSAGEM E PARA A EXECUÇÃO
try:
    df_rfm, df_resumo, dict_personas = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar os artefatos: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# BARRA LATERAL (SIDEBAR) - FILTROS
# -----------------------------------------------------------------------------
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=70)
st.sidebar.title("Customer Intelligence")
st.sidebar.markdown("---")

lista_segmentos = ["Todos"] + sorted(list(df_rfm["Segmento"].unique()))
segmento_selecionado = st.sidebar.radio(
    "Selecione um Segmento de Cliente:",
    options=lista_segmentos
)

# st.sidebar.markdown("---")
# st.sidebar.info("""
# **Tech Stack:**
# - **ML:** Scikit-Learn (K-Means)
# - **Data:** Pandas & Plotly
# - **GenAI:** Groq API (Llama 3.1)
# - **UI:** Streamlit
# """)

# Opção de saída
if st.sidebar.button("⏏️ Sair", use_container_width=True):
    st.switch_page("views_home.py")

# -----------------------------------------------------------------------------
# CABEÇALHO E MÉTRICAS GERAIS
# -----------------------------------------------------------------------------
st.title("🛍️ Dashboard de Inteligência de Clientes & CRM")
st.caption("Segmentação por Aprendizado de Máquina (RFM + K-Means) e Geração Automatizada de Personas via IA Generativa.")

st.markdown("---")

# Filtragem do dataframe base
if segmento_selecionado != "Todos":
    df_filtrado = df_rfm[df_rfm["Segmento"] == segmento_selecionado]
else:
    df_filtrado = df_rfm

# Exibição dos KPIs da base selecionada
col1, col2, col3, col4 = st.columns(4)

total_clientes = len(df_filtrado)
recencia_media = df_filtrado["Recency"].mean()
frequencia_media = df_filtrado["Frequency"].mean()
monetario_medio = df_filtrado["Monetary"].mean()

col1.metric("Total de Clientes", f"{total_clientes:,}")
col2.metric("Recência Média", f"{recencia_media:.1f} dias")
col3.metric("Frequência Média", f"{frequencia_media:.1f} compras")
col4.metric("Valor Monetário Médio", f"£ {monetario_medio:,.2f}")

st.markdown("---")

# -----------------------------------------------------------------------------
# SEÇÃO 1: ESTRATÉGIAS DE IA GENERATIVA (PERSONAS)
# -----------------------------------------------------------------------------
st.subheader("🤖 Personas & Estratégias Recomendadas pela IA")

if segmento_selecionado == "Todos":
    st.info("💡 **Selecione um segmento específico no menu lateral** para visualizar o diagnóstico comportamental e as estratégias exclusivas geradas pela LLM.")
else:
    persona_info = dict_personas.get(segmento_selecionado, {})
    
    if persona_info:
        col_persona1, col_persona2 = st.columns([1, 1])
        
        with col_persona1:
            st.markdown(f"### 🎯 Persona: **{persona_info.get('persona_nome', 'N/A')}**")
            st.markdown(f"**Descrição Comportamental:**\n{persona_info.get('descricao_persona', 'N/A')}")
            st.success(f"**Estratégia de Retenção Recomendada:**\n{persona_info.get('estrategia_retencao', 'N/A')}")
            
        with col_persona2:
            st.markdown("### 📱 Copy para Notificação Push (Mobile)")
            st.info(persona_info.get("copy_notificacao_push", "N/A"))
            st.caption("Esta mensagem foi formulada automaticamente com base nas estatísticas RFM do grupo para uso em campanhas de CRM.")
    else:
        st.warning("Nenhuma informação de IA encontrada para este segmento.")

st.markdown("---")

# -----------------------------------------------------------------------------
# SEÇÃO 2: VISUALIZAÇÃO INTERATIVA DOS CLUSTERS (PLOTLY)
# -----------------------------------------------------------------------------
st.subheader("📊 Análise Visual da Segmentação (K-Means)")

# Gráfico 1: Dispersão Recência vs Monetário
fig_dispersion = px.scatter(
    df_rfm,
    x="Recency",
    y="Monetary",
    color="Segmento",
    color_discrete_map=CORES_SEGMENTOS,  # ALTERAÇÃO 2: Aplica o mapa de cores fixo na dispersão
    size="Frequency",
    hover_data=["CustomerID"],
    log_y=True,
    title="Distribuição dos Clientes: Recência vs. Monetário (Escala Log)",
    labels={"Recency": "Recência (Dias)", "Monetary": "Valor Monetário (£)"},
    template="plotly_white"
)
st.plotly_chart(fig_dispersion, use_container_width=True)

col_chart1, col_chart2 = st.columns(2)

# Gráfico 2: Proporção da Base por Segmento
with col_chart1:
    fig_pie = px.pie(
        df_resumo,
        names="Segmento",
        values="Quantidade_Clientes",
        color="Segmento",                   
        color_discrete_map=CORES_SEGMENTOS, 
        title="Proporção de Clientes por Segmento",
        hole=0.4,
        template="plotly_white"
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# Gráfico 3: Comparativo Monetário Médio
with col_chart2:
    fig_bar = px.bar(
        df_resumo,
        x="Segmento",
        y="Monetary",
        color="Segmento",
        color_discrete_map=CORES_SEGMENTOS, 
        title="Valor Monetário Médio (£) por Cluster",
        labels={"Monetary": "Gasto Total Médio por Cliente (£)"}, 
        template="plotly_white"
    )
    st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# SEÇÃO 3: EXPLORADOR DA BASE DE DADOS
# -----------------------------------------------------------------------------
st.subheader("📋 Tabela de Clientes Segmentados")
st.dataframe(
    df_filtrado[["CustomerID", "Recency", "Frequency", "Monetary", "Segmento"]],
    use_container_width=True,
    hide_index=True
)

st.caption("Customer Intelligence Project | Desenvolvido em Python com Scikit-Learn, Groq & Streamlit.")