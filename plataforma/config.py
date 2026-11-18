"""Leitura das credenciais do Supabase (st.secrets ou variáveis de ambiente)."""

from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class ConfigSupabase:
    url: str
    anon_key: str  # chave pública ("anon"/"publishable"). NUNCA usar a service_role no app.


def _secret(secao: str, chave: str) -> str | None:
    try:
        return st.secrets[secao][chave]
    except Exception:  # arquivo de secrets ausente ou chave inexistente
        return None


def config_supabase() -> ConfigSupabase | None:
    url = _secret("supabase", "url") or os.getenv("SUPABASE_URL")
    chave = _secret("supabase", "anon_key") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not chave:
        return None
    return ConfigSupabase(url=url, anon_key=chave)


def chave_groq() -> str | None:
    """Chave da Groq do servidor: [groq] api_key, GROQ_API_KEY nos secrets ou variável de ambiente."""
    chave = _secret("groq", "api_key")
    if not chave:
        try:
            chave = st.secrets["GROQ_API_KEY"]
        except Exception:
            chave = None
    if not chave and not os.getenv("GROQ_API_KEY"):
        try:  # desenvolvimento local: aproveita o .env já usado pelos notebooks
            from dotenv import find_dotenv, load_dotenv

            load_dotenv(find_dotenv(usecwd=True))
        except Exception:
            pass
    return chave or os.getenv("GROQ_API_KEY") or None


REMETENTE_TESTE_RESEND = "Customer Intelligence <onboarding@resend.dev>"


def config_resend() -> tuple[str, str] | None:
    """(api_key, remetente) do Resend para o envio de e-mail de teste, ou None se não configurado.

    Sem domínio verificado no Resend, use o remetente de teste deles (onboarding@resend.dev):
    ele só entrega para o e-mail dono da conta do Resend.
    """
    chave = _secret("resend", "api_key") or os.getenv("RESEND_API_KEY")
    if not chave:
        return None
    remetente = _secret("resend", "remetente") or os.getenv("RESEND_REMETENTE") or REMETENTE_TESTE_RESEND
    return chave, remetente
