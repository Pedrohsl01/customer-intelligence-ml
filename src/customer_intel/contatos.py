"""Contatos dos clientes (nome, e-mail e telefone) para a lista de disparo.

São dados pessoais: ficam só no banco da empresa (protegidos por RLS) e nunca
são enviados à LLM.
"""

from __future__ import annotations

import re

import pandas as pd

COLUNAS_CONTATO = ["cliente_nome", "cliente_email", "cliente_telefone"]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def normalizar_email(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    email = str(valor).strip().lower()
    return email if _EMAIL.match(email) else None


def normalizar_telefone(valor, ddi_padrao: str = "55") -> str | None:
    """Só dígitos, com DDI (formato aceito pelos disparadores de WhatsApp). Ex.: 5511987654321."""
    if valor is None or pd.isna(valor):
        return None
    digitos = re.sub(r"\D", "", str(valor).removesuffix(".0"))
    digitos = digitos.lstrip("0")
    if len(digitos) in (10, 11):          # DDD + número, sem DDI
        digitos = ddi_padrao + digitos
    return digitos if 12 <= len(digitos) <= 15 else None


def normalizar_nome(valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    nome = " ".join(str(valor).split())
    return nome.title()[:120] if nome else None


def extrair_contatos(transacoes: pd.DataFrame) -> pd.DataFrame:
    """Um contato por cliente: o valor válido mais recente de cada campo.

    Devolve colunas cliente_id, nome, email, telefone (vazio se o arquivo não tinha contatos).
    """
    vazio = pd.DataFrame(columns=["cliente_id", "nome", "email", "telefone"])
    presentes = [c for c in COLUNAS_CONTATO if c in transacoes.columns]
    if not presentes:
        return vazio

    df = transacoes[["cliente_id", "data_compra", *presentes]].sort_values("data_compra")
    contatos = pd.DataFrame({"cliente_id": df["cliente_id"]})
    contatos["nome"] = df["cliente_nome"].map(normalizar_nome) if "cliente_nome" in df else None
    contatos["email"] = df["cliente_email"].map(normalizar_email) if "cliente_email" in df else None
    contatos["telefone"] = df["cliente_telefone"].map(normalizar_telefone) if "cliente_telefone" in df else None

    por_cliente = contatos.groupby("cliente_id", sort=True)[["nome", "email", "telefone"]].last()  # ignora nulos
    por_cliente = por_cliente.dropna(how="all").reset_index()
    return por_cliente.astype(object).where(por_cliente.notna(), None) if not por_cliente.empty else vazio
