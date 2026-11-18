from pathlib import Path

import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
import os

from plataforma import campanhas, estrategias, opcoes, repositorio, sessao, ui
from plataforma.config import config_resend

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
# Mapa fixo: os valores ficam em plataforma/ui.py para a landing e o cartão de persona usarem os mesmos.
CORES_SEGMENTOS = ui.CORES_SEGMENTOS

# -----------------------------------------------------------------------------
# Carregar CSS personalizado
# -----------------------------------------------------------------------------

ui.carregar_css("style.css")

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


def carregar_dados_da_empresa(empresa_id):
    """Última segmentação concluída da empresa logada, no formato usado pelos gráficos.

    O cache fica na sessão do usuário (não em st.cache_data, que é global entre
    usuários) e é invalidado quando muda a empresa ou a execução.
    """
    client = sessao.cliente()
    execucao = repositorio.ultima_execucao(client, empresa_id)
    if execucao is None:
        return None

    chave = ("dados_empresa", empresa_id, execucao["id"])
    if st.session_state.get("_cache_dashboard_chave") != chave:
        clientes = repositorio.clientes_segmentados(client, empresa_id, execucao["id"]).rename(columns={
            "cliente_id": "CustomerID", "recency": "Recency", "frequency": "Frequency",
            "monetary": "Monetary", "segmento": "Segmento", "cluster": "Cluster",
        })
        resumo = repositorio.resumo_segmentos(client, empresa_id, execucao["id"]).rename(columns={
            "segmento": "Segmento", "quantidade_clientes": "Quantidade_Clientes", "monetary_medio": "Monetary",
        })
        personas = repositorio.estrategias(client, empresa_id, execucao["id"])
        st.session_state["_cache_dashboard_chave"] = chave
        st.session_state["_cache_dashboard_produtos"] = execucao.get("produtos_por_segmento") or {}
        st.session_state["_cache_dashboard_contatos"] = repositorio.contatos(client, empresa_id)
        st.session_state["_cache_dashboard_dados"] = (clientes, resumo, personas)
    return st.session_state["_cache_dashboard_dados"]


# -----------------------------------------------------------------------------
# ORIGEM DOS DADOS: empresa logada (Supabase) ou demonstração (arquivos públicos)
# -----------------------------------------------------------------------------
empresa = sessao.empresa_atual()
modo_demo = empresa is None
simbolo = "£" if modo_demo else opcoes.simbolo_moeda(empresa.get("moeda"))

try:
    if modo_demo:
        df_rfm, df_resumo, dict_personas = carregar_dados()
    else:
        dados_empresa = carregar_dados_da_empresa(empresa["id"])
        if dados_empresa is None:
            ui.cabecalho(empresa["nome"])
            st.info("Sua empresa ainda não tem nenhuma segmentação concluída. "
                    "Assim que os dados de vendas forem importados, os segmentos e as personas aparecem aqui.")
            st.page_link("paginas/importar.py", label="Importar dados de vendas", icon=":material/upload_file:")
            st.stop()
        df_rfm, df_resumo, dict_personas = dados_empresa
except Exception as e:
    st.error(f"Erro ao carregar os dados: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# BARRA LATERAL (SIDEBAR) - FILTROS
# -----------------------------------------------------------------------------
st.sidebar.markdown(
    ui.marca(empresa["nome"] if empresa else "Customer Intelligence",
             "Demonstração com o dataset Online Retail" if modo_demo else None),
    unsafe_allow_html=True,
)
if modo_demo:
    # Na demonstração a navegação automática fica oculta: a saída é pelo botão abaixo.
    st.markdown('<style>[data-testid="stSidebarNav"] { display: none; }</style>', unsafe_allow_html=True)

lista_segmentos = ["Todos"] + sorted(list(df_rfm["Segmento"].unique()))
segmento_selecionado = st.sidebar.radio(
    "Segmento de clientes",
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

# Opção de saída da demonstração (logado, o botão "Sair" fica no menu global em home.py)
if modo_demo and st.sidebar.button("Sair da demonstração", key="sair_demo", icon=":material/logout:",
                                   use_container_width=True):
    st.switch_page("views_home.py")

# -----------------------------------------------------------------------------
# CABEÇALHO E MÉTRICAS GERAIS
# -----------------------------------------------------------------------------
ui.cabecalho(
    "Inteligência de clientes e CRM",
    "Segmentação por aprendizado de máquina (RFM + K-Means) e personas geradas por IA generativa.",
)

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

col1.metric("Total de clientes", f"{total_clientes:,}")
col2.metric("Recência média", f"{recencia_media:.1f} dias")
col3.metric("Frequência média", f"{frequencia_media:.1f} compras")
col4.metric("Valor monetário médio", f"{simbolo} {monetario_medio:,.2f}")

# -----------------------------------------------------------------------------
# SEÇÃO 1: ESTRATÉGIAS DE IA GENERATIVA (PERSONAS)
# -----------------------------------------------------------------------------
ui.secao("Personas e estratégias recomendadas pela IA",
         "O diagnóstico de cada segmento e o que enviar para ele.")

if not modo_demo:
    if not dict_personas:
        st.info("Esta segmentação ainda não tem personas geradas pela IA.")
    if empresa["papel"] in ("admin", "analista"):
        if not estrategias.ia_disponivel():
            st.caption("A geração por IA não está configurada neste ambiente.")
        elif st.button(
            "Gerar campanhas novamente" if dict_personas else "Gerar personas e campanhas com IA",
            icon=":material/refresh:" if dict_personas else ":material/auto_awesome:",
            type="secondary" if dict_personas else "primary",
            help="Usa o nicho e o tom de voz cadastrados em “Minha empresa”. Só estatísticas agregadas "
                 "dos segmentos são enviadas à IA, nunca dados individuais de clientes.",
        ):
            execucao_id = st.session_state["_cache_dashboard_chave"][2]
            try:
                with st.spinner("Gerando personas e campanhas..."):
                    estrategias.gerar_e_salvar(sessao.cliente(), estrategias.cliente_llm(), empresa, execucao_id)
            except estrategias.ErroEstrategias as erro:
                st.error(str(erro))
            except Exception as erro:
                st.error(f"Não foi possível gravar as personas: {erro}")
            else:
                st.session_state.pop("_cache_dashboard_chave", None)
                st.rerun()

if segmento_selecionado == "Todos":
    st.info("**Selecione um segmento no menu lateral** para ver o diagnóstico comportamental e as "
            "estratégias geradas pela LLM para ele.", icon=":material/lightbulb:")
else:
    persona_info = dict_personas.get(segmento_selecionado, {})
    
    if persona_info:
        cor_segmento = CORES_SEGMENTOS.get(segmento_selecionado, ui.AMBAR)
        remetente = empresa["nome"] if empresa else "Sua loja"
        produtos_segmento = ({} if modo_demo else st.session_state.get("_cache_dashboard_produtos", {})).get(
            segmento_selecionado, [])
        col_persona1, col_persona2 = st.columns([3, 2], gap="large")

        with col_persona1:
            ui.cartao_persona(segmento_selecionado, cor_segmento, persona_info, produtos_segmento)

        # Contatos do segmento (só empresas logadas que importaram nome/e-mail/telefone)
        contatos_empresa = (pd.DataFrame(columns=["cliente_id", "nome", "email", "telefone"]) if modo_demo
                            else st.session_state.get("_cache_dashboard_contatos",
                                                      pd.DataFrame(columns=["cliente_id", "nome", "email", "telefone"])))
        ids_segmento = set(df_filtrado["CustomerID"].astype(str).str.replace(r"\.0$", "", regex=True))
        contatos_segmento = contatos_empresa[contatos_empresa["cliente_id"].astype(str).isin(ids_segmento)]
        nomes_reais = contatos_segmento["nome"].dropna()
        mensagens = campanhas.mensagens_da_persona(persona_info)

        with col_persona2:
            # Valores usados nas prévias e na lista de disparo
            with st.popover("Personalizar mensagens", icon=":material/tune:", use_container_width=True):
                nome_exemplo = st.text_input(
                    "Nome do cliente na prévia",
                    value=campanhas.primeiro_nome(nomes_reais.iloc[0]) if not nomes_reais.empty else "João",
                    key=f"prev_nome_{segmento_selecionado}",
                )
                validade = st.text_input("Validade da oferta ({validade})", value="domingo", key="prev_validade")
                link = st.text_input("Link da campanha ({link})", value="https://sualoja.com.br/oferta",
                                     key="prev_link")
            valores_fixos = {"validade": validade.strip(), "link": link.strip()}
            valores_prevista = {**valores_fixos, "nome": campanhas.primeiro_nome(nome_exemplo)}

            aba_push, aba_whatsapp, aba_email = st.tabs(["Push", "WhatsApp", "E-mail"])
            with aba_push:
                ui.previa_push(campanhas.personalizar(mensagens["mensagem_push"], valores_prevista) or "N/A",
                               remetente)
            with aba_whatsapp:
                ui.previa_whatsapp(campanhas.personalizar(mensagens["mensagem_whatsapp"], valores_prevista),
                                   remetente)
            with aba_email:
                if mensagens["corpo_email_html"]:
                    ui.assunto_email(campanhas.personalizar(mensagens["assunto_email"], valores_prevista))
                    with st.container(key="cartao_email"):
                        st.html(campanhas.personalizar(mensagens["corpo_email_html"], valores_prevista))
                    with st.expander("Ver o HTML para copiar"):
                        st.code(mensagens["corpo_email_html"], language="html")
                else:
                    st.caption("Esta persona não tem e-mail. Gere as campanhas novamente para criar o pacote completo.")
            pendentes = campanhas.marcadores_pendentes(
                *(campanhas.personalizar(t, valores_prevista) for t in mensagens.values()))
            st.caption("Textos gerados pela IA a partir das estatísticas do segmento. Revise antes de enviar."
                       + (f" Marcadores sem valor: {', '.join('{' + m + '}' for m in pendentes)}." if pendentes else ""))

        # ---------------------------------------------------------------------
        # ATIVAR CAMPANHA: lista para disparo, e-mail de teste e simulador de ROI
        # ---------------------------------------------------------------------
        ui.secao("Ativar campanha",
                 f"Leve a campanha de {segmento_selecionado} para a sua ferramenta de disparo e estime o retorno.")
        col_lista, col_teste = st.columns(2, gap="medium")

        with col_lista:
            with st.container(key="cartao_lista_disparo"):
                st.markdown("**Lista para disparo**")
                lista_disparo = campanhas.montar_lista_disparo(
                    df_filtrado, contatos_segmento, persona_info, segmento_selecionado, valores_fixos)
                com_email = int(lista_disparo["email"].notna().sum())
                com_telefone = int(lista_disparo["telefone"].notna().sum())
                st.caption(
                    f"{len(lista_disparo):,} clientes com a mensagem de cada canal já personalizada. "
                    + (f"{com_email:,} com e-mail e {com_telefone:,} com telefone."
                       if com_email or com_telefone else
                       "A base não tem contatos: importe um arquivo com nome, e-mail ou telefone para preenchê-los.")
                )
                st.download_button(
                    "Baixar lista para disparo (.CSV)",
                    data=campanhas.csv_para_disparo(lista_disparo),
                    file_name=f"disparo_{segmento_selecionado.lower().replace(' ', '_')}.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    type="primary",
                    use_container_width=True,
                    key="baixar_lista_disparo",
                )
                st.caption("Pronta para importar no RD Station, Mailchimp ou em disparadores de WhatsApp.")

        with col_teste:
            with st.container(key="cartao_envio_teste"):
                st.markdown("**Enviar teste para meu e-mail**")
                resend = config_resend()
                usuario_logado = sessao.usuario()
                if modo_demo:
                    st.caption("Disponível para empresas logadas: o e-mail chega na caixa de quem está logado.")
                elif empresa["papel"] not in ("admin", "analista"):
                    st.caption("Somente administradores e analistas podem enviar testes.")
                elif not mensagens["corpo_email_html"]:
                    st.caption("Esta persona não tem e-mail. Gere as campanhas novamente para criar o pacote completo.")
                elif resend is None:
                    st.caption("O envio de e-mail não está configurado neste ambiente (chave do Resend).")
                else:
                    envios = st.session_state.get("_envios_teste", 0)
                    st.caption(f"Envia o e-mail desta campanha para **{usuario_logado['email']}**, "
                               f"com o nome {campanhas.primeiro_nome(nome_exemplo)} na saudação.")
                    if st.button("Enviar teste", icon=":material/send:", use_container_width=True,
                                 disabled=envios >= 3, key="enviar_teste",
                                 help="Até 3 envios de teste por sessão."):
                        try:
                            campanhas.enviar_email_teste(
                                resend[0], resend[1], usuario_logado["email"],
                                campanhas.personalizar(mensagens["assunto_email"], valores_prevista),
                                campanhas.personalizar(mensagens["corpo_email_html"], valores_prevista),
                            )
                        except campanhas.ErroEnvio as erro:
                            st.error(str(erro))
                        else:
                            st.session_state["_envios_teste"] = envios + 1
                            st.success(f"E-mail de teste enviado para {usuario_logado['email']}.")
                    if envios >= 3:
                        st.caption("Limite de 3 envios de teste nesta sessão atingido.")

        # Simulador de retorno
        with st.container(key="cartao_roi"):
            st.markdown("**Simulador de retorno da campanha**")
            ticket_segmento = campanhas.ticket_medio(df_filtrado)
            col_taxa, col_ticket, col_compras, col_desconto = st.columns([2, 1, 1, 1])
            taxa = col_taxa.slider("Clientes que respondem à campanha (%)", 1, 50, 10, key="roi_taxa")
            ticket_informado = col_ticket.number_input(
                f"Ticket médio ({simbolo})", min_value=0.0, value=round(ticket_segmento, 2), step=10.0,
                key=f"roi_ticket_{segmento_selecionado}", help="Valor médio por pedido neste segmento.")
            compras_cliente = col_compras.number_input(
                "Compras por cliente", min_value=1, max_value=12, value=1, key="roi_compras")
            desconto = col_desconto.number_input(
                "Desconto (%)", min_value=0.0, max_value=90.0,
                value=campanhas.desconto_da_oferta(mensagens["oferta"]), step=5.0,
                key=f"roi_desconto_{segmento_selecionado}", help="Sugerido a partir da oferta da IA.")
            simulacao = campanhas.simular_retorno(len(df_filtrado), taxa, ticket_informado,
                                                  compras_cliente, desconto)
            ui.roi(f"Se {taxa}% dos {segmento_selecionado} ({simulacao.clientes_recuperados:,} clientes) comprarem "
                   f"com esta campanha, o faturamento estimado será de {simbolo} {simulacao.receita_liquida:,.2f}.")
            m1, m2, m3 = st.columns(3)
            m1.metric("Clientes que voltam a comprar", f"{simulacao.clientes_recuperados:,}")
            m2.metric("Faturamento bruto", f"{simbolo} {simulacao.receita_bruta:,.2f}")
            m3.metric("Custo do desconto", f"{simbolo} {simulacao.custo_desconto:,.2f}")
            st.caption("Estimativa simples: clientes × taxa × compras × ticket médio, menos o desconto. "
                       "Não considera clientes que comprariam mesmo sem a campanha.")
    else:
        st.warning("Nenhuma persona gerada para este segmento.")

# -----------------------------------------------------------------------------
# SEÇÃO 2: VISUALIZAÇÃO INTERATIVA DOS CLUSTERS (PLOTLY)
# -----------------------------------------------------------------------------
ui.secao("Análise visual da segmentação (K-Means)",
         "Cada ponto é um cliente; as cores identificam os segmentos em todos os gráficos.")

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
    title="Distribuição dos clientes: recência vs. monetário (escala log)",
    labels={"Recency": "Recência (dias)", "Monetary": f"Valor monetário ({simbolo})"},
    template="plotly_dark"
)
with st.container(key="cartao_grafico_dispersao"):
    st.plotly_chart(ui.estilizar_grafico(fig_dispersion, altura=460), use_container_width=True)

col_chart1, col_chart2 = st.columns(2, gap="medium")

# Gráfico 2: Proporção da Base por Segmento
with col_chart1:
    fig_pie = px.pie(
        df_resumo,
        names="Segmento",
        values="Quantidade_Clientes",
        color="Segmento",                   
        color_discrete_map=CORES_SEGMENTOS, 
        title="Proporção de clientes por segmento",
        hole=0.55,
        template="plotly_dark"
    )
    fig_pie.update_traces(marker=dict(line=dict(color="#151B2C", width=2)), textfont=dict(color="#0D1220"))
    with st.container(key="cartao_grafico_proporcao"):
        st.plotly_chart(ui.estilizar_grafico(fig_pie), use_container_width=True)

# Gráfico 3: Comparativo Monetário Médio
with col_chart2:
    fig_bar = px.bar(
        df_resumo,
        x="Segmento",
        y="Monetary",
        color="Segmento",
        color_discrete_map=CORES_SEGMENTOS, 
        title=f"Valor monetário médio ({simbolo}) por cluster",
        labels={"Monetary": f"Gasto total médio por cliente ({simbolo})"},
        template="plotly_dark"
    )
    fig_bar.update_layout(showlegend=False, bargap=0.35)
    fig_bar.update_traces(marker_line_width=0)
    with st.container(key="cartao_grafico_monetario"):
        st.plotly_chart(ui.estilizar_grafico(fig_bar), use_container_width=True)

# -----------------------------------------------------------------------------
# SEÇÃO 3: EXPLORADOR DA BASE DE DADOS
# -----------------------------------------------------------------------------
tabela_clientes = df_filtrado[["CustomerID", "Recency", "Frequency", "Monetary", "Segmento"]]
col_titulo_tabela, col_exportar = st.columns([3, 1], vertical_alignment="bottom")
with col_titulo_tabela:
    ui.secao("Tabela de clientes segmentados",
             f"{len(tabela_clientes):,} clientes" + ("" if segmento_selecionado == "Todos"
                                                      else f" em {segmento_selecionado}"))
with col_exportar:
    # Lista pronta para subir na ferramenta de disparo de campanhas
    st.download_button(
        "Exportar lista (CSV)",
        data=tabela_clientes.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"clientes_{segmento_selecionado.lower().replace(' ', '_')}.csv",
        mime="text/csv",
        icon=":material/download:",
        use_container_width=True,
    )
st.dataframe(
    tabela_clientes,
    use_container_width=True,
    hide_index=True
)

ui.rodape("Customer Intelligence. Desenvolvido em Python com Scikit-Learn, Groq e Streamlit.")