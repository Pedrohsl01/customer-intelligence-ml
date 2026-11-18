"""Personas e pacotes de campanha (e-mail, WhatsApp, push e oferta) gerados por IA para os segmentos de uma empresa.

A chave da Groq é do servidor (secrets), nunca da empresa cliente. Só números
agregados por segmento vão para a LLM — nenhum dado individual de cliente.
O nicho e o tom de voz cadastrados pela empresa entram no prompt.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from customer_intel.personas import ContextoEmpresa, PersonaGerada, dados_do_segmento, gerar_persona
from plataforma import opcoes, repositorio
from plataforma.config import chave_groq


class ErroEstrategias(Exception):
    """Erro com mensagem pronta para ser mostrada ao usuário."""


def ia_disponivel() -> bool:
    return chave_groq() is not None


@st.cache_resource(show_spinner=False)
def _cliente_groq(chave: str):
    from groq import Groq

    return Groq(api_key=chave)


def cliente_llm():
    """Cliente da LLM (compartilhado: a chave é do servidor, não de um usuário)."""
    chave = chave_groq()
    if chave is None:
        raise ErroEstrategias("A geração por IA não está configurada neste ambiente (defina a chave da Groq nos secrets).")
    return _cliente_groq(chave)


def contexto_da_empresa(empresa: dict) -> ContextoEmpresa:
    preset, detalhes = opcoes.separar_tom_de_voz(empresa.get("tom_de_voz"))
    tom = f"{preset} — {opcoes.TONS_DE_VOZ[preset]}"
    if detalhes:
        tom += f" Orientações da empresa: {detalhes}"
    return ContextoEmpresa(
        nome=empresa["nome"],
        setor=empresa.get("setor"),
        tom_de_voz=tom,
        moeda=empresa.get("moeda") or "BRL",
    )


def _completar_resumo(resumo: pd.DataFrame) -> pd.DataFrame:
    """A view `resumo_segmentos` traz os totais; aqui entram as participações na base."""
    resumo = resumo.copy()
    for coluna in ("quantidade_clientes", "recency_mediana", "frequency_mediana",
                   "monetary_mediano", "monetary_total", "ticket_medio"):
        resumo[coluna] = pd.to_numeric(resumo[coluna])
    resumo["participacao_clientes"] = resumo["quantidade_clientes"] / resumo["quantidade_clientes"].sum()
    resumo["participacao_receita"] = resumo["monetary_total"] / resumo["monetary_total"].sum()
    return resumo.sort_values("monetary_mediano", ascending=False)


def gerar_e_salvar(client, llm, empresa: dict, execucao_id: str, ao_progredir=None) -> list[PersonaGerada]:
    """Gera uma persona por segmento da execução e grava em `estrategias_ia`.

    Gerar de novo substitui as personas anteriores da mesma execução (ex.: após
    a empresa mudar o tom de voz). Se a LLM falhar em algum segmento, nada é gravado.
    """
    resumo = repositorio.resumo_segmentos(client, empresa["id"], execucao_id)
    if resumo.empty:
        raise ErroEstrategias("Esta execução não tem segmentos para descrever.")
    resumo = _completar_resumo(resumo)
    contexto = contexto_da_empresa(empresa)
    execucao = repositorio.buscar_execucao(client, empresa["id"], execucao_id) or {}
    produtos = execucao.get("produtos_por_segmento") or {}

    geradas: list[PersonaGerada] = []
    for posicao, (_, linha) in enumerate(resumo.iterrows(), start=1):
        if ao_progredir:
            ao_progredir(linha["segmento"], posicao, len(resumo))
        try:
            geradas.append(gerar_persona(llm, dados_do_segmento(linha, produtos.get(linha["segmento"])), contexto))
        except Exception as erro:
            raise ErroEstrategias(f"A IA não conseguiu gerar a persona de “{linha['segmento']}”. "
                                  "Tente novamente em instantes.") from erro

    repositorio.salvar_estrategias(client, empresa["id"], execucao_id, geradas)
    return geradas
