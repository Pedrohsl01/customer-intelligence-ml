"""Transforma a campanha gerada pela IA em ações: mensagens personalizadas por cliente,
lista para ferramentas de disparo, e-mail de teste e simulação de retorno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from customer_intel.contatos import normalizar_email
from customer_intel.personas import sanitizar_html

NOME_PADRAO = "cliente"
MARCADOR = re.compile(r"\{\s*([a-zA-Z_]+)\s*\}")
DESCONTO_NA_OFERTA = re.compile(r"(\d{1,2}(?:[.,]\d+)?)\s*%")

# Colunas do CSV de disparo, na ordem em que aparecem
COLUNAS_LISTA = ["cliente_id", "nome", "email", "telefone", "segmento", "oferta", "assunto_email",
                 "corpo_email_html", "mensagem_whatsapp", "mensagem_push",
                 "dias_desde_ultima_compra", "compras", "valor_gasto"]


class ErroEnvio(Exception):
    """Erro com mensagem pronta para ser mostrada ao usuário."""


def primeiro_nome(nome: str | None) -> str:
    if nome is None or pd.isna(nome) or not str(nome).strip():
        return NOME_PADRAO
    return str(nome).strip().split()[0].title()


def personalizar(texto: str | None, valores: dict[str, str]) -> str:
    """Troca marcadores como {nome}, {validade} e {link}. Marcadores sem valor ficam como estão."""
    if not texto:
        return ""

    def trocar(m: re.Match) -> str:
        valor = valores.get(m.group(1).lower())
        return str(valor) if valor not in (None, "") else m.group(0)

    return MARCADOR.sub(trocar, texto)


def marcadores_pendentes(*textos: str) -> list[str]:
    """Marcadores que continuam no texto depois da personalização (ex.: algo que a empresa não preencheu)."""
    encontrados = {m.lower() for t in textos if t for m in MARCADOR.findall(t)}
    return sorted(encontrados)


def mensagens_da_persona(persona: dict) -> dict[str, str]:
    """Textos de cada canal. Personas antigas (só push) usam a copy do push também no WhatsApp."""
    push = persona.get("copy_notificacao_push", "")
    return {
        "oferta": persona.get("oferta_sugerida", ""),
        "assunto_email": persona.get("email_assunto", ""),
        "corpo_email_html": persona.get("email_corpo_html", ""),
        "mensagem_whatsapp": persona.get("mensagem_whatsapp") or push,
        "mensagem_push": push,
    }


def montar_lista_disparo(clientes: pd.DataFrame, contatos: pd.DataFrame, persona: dict, segmento: str,
                         valores_fixos: dict[str, str]) -> pd.DataFrame:
    """Uma linha por cliente do segmento, com as mensagens já personalizadas.

    `clientes`: colunas CustomerID, Recency, Frequency, Monetary (formato do dashboard).
    `contatos`: colunas cliente_id, nome, email, telefone (pode estar vazio).
    `valores_fixos`: marcadores iguais para todos (ex.: validade, link).
    """
    lista = pd.DataFrame({
        "cliente_id": clientes["CustomerID"].astype(str).str.replace(r"\.0$", "", regex=True),
        "dias_desde_ultima_compra": clientes["Recency"].to_numpy(),
        "compras": clientes["Frequency"].to_numpy(),
        "valor_gasto": clientes["Monetary"].round(2).to_numpy(),
    })
    contatos = contatos[["cliente_id", "nome", "email", "telefone"]].astype({"cliente_id": str})
    lista = lista.merge(contatos, on="cliente_id", how="left")
    lista["segmento"] = segmento

    textos = mensagens_da_persona(persona)
    nomes = lista["nome"].map(primeiro_nome)
    for coluna, texto in textos.items():
        if MARCADOR.search(texto or ""):
            lista[coluna] = [personalizar(texto, {**valores_fixos, "nome": n}) for n in nomes]
        else:
            lista[coluna] = texto
    return lista[COLUNAS_LISTA].astype(object).where(lista[COLUNAS_LISTA].notna(), None)


def csv_para_disparo(lista: pd.DataFrame) -> bytes:
    """CSV em UTF-8 com BOM (abre certo no Excel e importa no RD Station, Mailchimp e disparadores)."""
    return lista.to_csv(index=False).encode("utf-8-sig")


# --- Simulador de retorno -----------------------------------------------------

@dataclass
class Simulacao:
    clientes_recuperados: int
    receita_bruta: float
    custo_desconto: float
    receita_liquida: float


def desconto_da_oferta(oferta: str | None) -> float:
    """Percentual citado na oferta ("15% OFF de retorno" → 15). 0 se não houver."""
    achado = DESCONTO_NA_OFERTA.search(oferta or "")
    return float(achado.group(1).replace(",", ".")) if achado else 0.0


def ticket_medio(clientes: pd.DataFrame) -> float:
    compras = clientes["Frequency"].sum()
    return float(clientes["Monetary"].sum() / compras) if compras else 0.0


def simular_retorno(total_clientes: int, taxa_recuperacao_pct: float, ticket: float,
                    compras_por_cliente: float = 1.0, desconto_pct: float = 0.0) -> Simulacao:
    recuperados = round(total_clientes * taxa_recuperacao_pct / 100)
    bruta = recuperados * compras_por_cliente * ticket
    custo = bruta * desconto_pct / 100
    return Simulacao(recuperados, round(bruta, 2), round(custo, 2), round(bruta - custo, 2))


# --- E-mail de teste (Resend) ---------------------------------------------------

URL_RESEND = "https://api.resend.com/emails"


def enviar_email_teste(api_key: str, remetente: str, destinatario: str, assunto: str, corpo_html: str,
                       http_client=None) -> str:
    """Envia UM e-mail de teste e devolve o id do envio. `http_client` permite testar sem rede."""
    destino = normalizar_email(destinatario)
    if not destino:
        raise ErroEnvio("E-mail de destino inválido.")
    corpo = sanitizar_html(corpo_html or "")
    if not corpo:
        raise ErroEnvio("Esta campanha não tem corpo de e-mail para enviar.")

    import httpx

    cliente_http = http_client or httpx
    try:
        resposta = cliente_http.post(
            URL_RESEND,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"from": remetente, "to": [destino], "subject": f"[Teste] {assunto}".strip()[:120], "html": corpo},
            timeout=15,
        )
    except Exception as erro:
        raise ErroEnvio("Não foi possível conectar ao serviço de e-mail. Tente novamente.") from erro

    if resposta.status_code >= 400:
        try:
            detalhe = resposta.json().get("message", "")
        except Exception:
            detalhe = ""
        if resposta.status_code in (401, 403):
            raise ErroEnvio("O serviço de e-mail recusou o envio. Confira a chave do Resend e, sem domínio "
                            "verificado, envie apenas para o e-mail dono da conta Resend."
                            + (f" Detalhe: {detalhe}" if detalhe else ""))
        if resposta.status_code == 429:
            raise ErroEnvio("Limite de envios do serviço de e-mail atingido. Aguarde e tente novamente.")
        raise ErroEnvio(f"O serviço de e-mail recusou o envio ({resposta.status_code}). {detalhe}".strip())
    return (resposta.json() or {}).get("id", "")
