import streamlit as st

from plataforma import sessao, ui

# 1. Configuração global da página (DEVE SER A PRIMEIRA CHAMADA DO STREAMLIT)
st.set_page_config(
    page_title="Customer Intelligence",
    page_icon="🛍️",
    layout="wide"
)

# Tema visual comum a todas as páginas (cada página soma o próprio CSS)
ui.carregar_css("theme.css")

# 2. Renova o token do Supabase (ou desloga se a sessão expirou)
sessao.validar_sessao()

# 3. Rotas conforme o estado do usuário
dashboard = st.Page("app.py", title="Customer Intelligence", icon=":material/monitoring:")

if sessao.usuario() is None:
    paginas = [
        st.Page("views_home.py", title="Início", icon=":material/home:", default=True),
        st.Page("paginas/login.py", title="Entrar", icon=":material/login:"),
        dashboard,  # sem login, o dashboard mostra a demonstração com dados públicos
    ]
elif sessao.empresa_atual() is None:
    paginas = [st.Page("paginas/empresa.py", title="Cadastrar empresa", icon=":material/domain:", default=True)]
else:
    paginas = [
        st.Page("app.py", title="Dashboard", icon=":material/monitoring:", default=True),
        st.Page("paginas/importar.py", title="Importar dados", icon=":material/upload_file:"),
        st.Page("paginas/empresa.py", title="Minha empresa", icon=":material/domain:"),
    ]

# 4. Barra lateral comum a quem está logado: empresa atual e saída
if usuario := sessao.usuario():
    with st.sidebar:
        st.caption(f"Conectado como **{usuario['nome']}**")
        empresas = sessao.empresas()
        if len(empresas) > 1:
            ids = [e["id"] for e in empresas]
            atual = sessao.empresa_atual()
            escolhida = st.selectbox(
                "Empresa",
                ids,
                index=ids.index(atual["id"]) if atual else 0,
                format_func=lambda i: next(e["nome"] for e in empresas if e["id"] == i),
            )
            if atual is None or escolhida != atual["id"]:
                sessao.selecionar_empresa(escolhida)
                st.rerun()
        if st.button("Sair", icon=":material/logout:", use_container_width=True):
            sessao.sair()
            st.rerun()
        st.divider()

pg = st.navigation(paginas)
pg.run()
