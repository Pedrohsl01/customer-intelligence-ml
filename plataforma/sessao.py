"""Sessão do usuário no Streamlit, autenticada pelo Supabase Auth.

O cliente Supabase guarda o token do usuário logado, por isso existe UM
cliente por sessão do navegador (em `st.session_state`). Nunca usar
`st.cache_resource` para ele: o cache é global e compartilharia o login de um
usuário com todos os outros.

Senhas nunca passam pelo nosso banco: o Supabase Auth faz o hash (bcrypt) e
emite um JWT, que o Postgres usa nas policies de RLS via `auth.uid()`.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from plataforma import repositorio
from plataforma.config import config_supabase

_CLIENTE = "_supabase_client"
_USUARIO = "usuario"
_EMPRESAS = "empresas"
_EMPRESA_ATUAL = "empresa_atual_id"

MENSAGENS_ERRO = {
    "invalid login credentials": "E-mail ou senha inválidos.",
    "email not confirmed": "Confirme seu e-mail pelo link que enviamos antes de entrar.",
    "user already registered": "Já existe uma conta com este e-mail.",
    "password should be at least": "A senha é muito curta.",
    "rate limit": "Muitas tentativas. Aguarde alguns minutos e tente novamente.",
}


class ErroAutenticacao(Exception):
    pass


def _traduzir(erro: Exception) -> str:
    texto = str(erro).lower()
    for trecho, mensagem in MENSAGENS_ERRO.items():
        if trecho in texto:
            return mensagem
    return "Não foi possível concluir a operação. Tente novamente."


def supabase_disponivel() -> bool:
    return _CLIENTE in st.session_state or config_supabase() is not None


def cliente():
    if _CLIENTE not in st.session_state:
        config = config_supabase()
        if config is None:
            raise RuntimeError("Supabase não configurado (defina [supabase] url e anon_key em secrets.toml).")
        from supabase import ClientOptions, create_client

        st.session_state[_CLIENTE] = create_client(
            config.url,
            config.anon_key,
            # Sem thread de refresh por sessão: o token é renovado em `validar_sessao()`.
            options=ClientOptions(auto_refresh_token=False, persist_session=True),
        )
    return st.session_state[_CLIENTE]


# --- Estado -------------------------------------------------------------------

def usuario() -> dict[str, Any] | None:
    return st.session_state.get(_USUARIO)


def empresas() -> list[dict[str, Any]]:
    return st.session_state.get(_EMPRESAS, [])


def empresa_atual() -> dict[str, Any] | None:
    empresa_id = st.session_state.get(_EMPRESA_ATUAL)
    return next((e for e in empresas() if e["id"] == empresa_id), None)


def selecionar_empresa(empresa_id: str) -> None:
    # Só aceita empresas em que o usuário é membro.
    if any(e["id"] == empresa_id for e in empresas()):
        st.session_state[_EMPRESA_ATUAL] = empresa_id


def eh_admin() -> bool:
    empresa = empresa_atual()
    return bool(empresa and empresa["papel"] == "admin")


def recarregar_empresas() -> None:
    lista = repositorio.empresas_do_usuario(cliente(), usuario()["id"])
    st.session_state[_EMPRESAS] = lista
    if empresa_atual() is None:
        st.session_state[_EMPRESA_ATUAL] = lista[0]["id"] if lista else None


def _limpar_estado() -> None:
    for chave in (_USUARIO, _EMPRESAS, _EMPRESA_ATUAL):
        st.session_state.pop(chave, None)


# --- Ações --------------------------------------------------------------------

def _iniciar(user) -> None:
    metadados = getattr(user, "user_metadata", None) or {}
    st.session_state[_USUARIO] = {
        "id": user.id,
        "email": user.email,
        "nome": metadados.get("nome") or user.email,
    }
    recarregar_empresas()


def entrar(email: str, senha: str) -> None:
    try:
        resposta = cliente().auth.sign_in_with_password({"email": email.strip(), "password": senha})
    except Exception as erro:
        raise ErroAutenticacao(_traduzir(erro)) from erro
    _iniciar(resposta.user)


def cadastrar(nome: str, email: str, senha: str) -> bool:
    """Cria a conta. Retorna True se já entrou; False se precisa confirmar o e-mail."""
    try:
        resposta = cliente().auth.sign_up(
            {"email": email.strip(), "password": senha, "options": {"data": {"nome": nome.strip()}}}
        )
    except Exception as erro:
        raise ErroAutenticacao(_traduzir(erro)) from erro
    if resposta.session is None:
        return False
    _iniciar(resposta.user)
    return True


def sair() -> None:
    if _CLIENTE in st.session_state:
        try:
            st.session_state[_CLIENTE].auth.sign_out()
        except Exception:
            pass  # token já expirado: basta limpar o estado local
        st.session_state.pop(_CLIENTE, None)
    _limpar_estado()


def validar_sessao() -> None:
    """Chamado a cada execução: renova o token se expirou e desloga se não for possível."""
    if usuario() is None:
        return
    try:
        sessao = cliente().auth.get_session()  # renova o access token se necessário
    except Exception:
        sessao = None
    if sessao is None:
        sair()
        st.session_state["aviso_sessao"] = "Sua sessão expirou. Entre novamente."
