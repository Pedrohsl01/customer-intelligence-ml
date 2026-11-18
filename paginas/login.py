"""Tela de login e cadastro (Supabase Auth)."""

import streamlit as st

from plataforma import sessao

TAMANHO_MINIMO_SENHA = 8

st.title("🔐 Acesse sua conta")

if aviso := st.session_state.pop("aviso_sessao", None):
    st.warning(aviso)

if not sessao.supabase_disponivel():
    st.error(
        "O login ainda não está configurado neste ambiente. Defina `[supabase] url` e `anon_key` "
        "em `.streamlit/secrets.toml` (veja `.streamlit/secrets.toml.example`)."
    )
    st.page_link("app.py", label="Ver a demonstração com dados públicos", icon="📊")
    st.stop()

aba_entrar, aba_cadastrar = st.tabs(["Entrar", "Criar conta"])

with aba_entrar:
    with st.form("form_login"):
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        enviar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if enviar:
        if not email or not senha:
            st.error("Preencha e-mail e senha.")
        else:
            try:
                sessao.entrar(email, senha)
                st.rerun()
            except sessao.ErroAutenticacao as erro:
                st.error(str(erro))

with aba_cadastrar:
    with st.form("form_cadastro"):
        nome = st.text_input("Seu nome", key="cad_nome")
        email_novo = st.text_input("E-mail corporativo", key="cad_email")
        senha_nova = st.text_input(f"Senha (mínimo {TAMANHO_MINIMO_SENHA} caracteres)", type="password", key="cad_senha")
        confirmacao = st.text_input("Confirme a senha", type="password", key="cad_confirmacao")
        criar = st.form_submit_button("Criar conta", type="primary", use_container_width=True)
    if criar:
        if not nome.strip() or not email_novo.strip():
            st.error("Preencha nome e e-mail.")
        elif len(senha_nova) < TAMANHO_MINIMO_SENHA:
            st.error(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")
        elif senha_nova != confirmacao:
            st.error("As senhas não conferem.")
        else:
            try:
                if sessao.cadastrar(nome, email_novo, senha_nova):
                    st.rerun()
                else:
                    st.success("Conta criada! Enviamos um link de confirmação para o seu e-mail.")
            except sessao.ErroAutenticacao as erro:
                st.error(str(erro))
