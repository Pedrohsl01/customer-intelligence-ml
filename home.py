import streamlit as st
from pathlib import Path

# 1. Configuração global da página (DEVE SER A PRIMEIRA LINHA DO STREAMLIT)
st.set_page_config(
    page_title="Customer Intelligence",
    page_icon="🛍️",
    layout="wide"
)



# 2. Definição das rotas apontando para arquivos distintos
home_page = st.Page("views_home.py", title="Início", icon="🏠", default=True)
app_page = st.Page("app.py", title="Customer Intelligence", icon="📊")

# 3. Navegação
pg = st.navigation([home_page, app_page])
pg.run()
