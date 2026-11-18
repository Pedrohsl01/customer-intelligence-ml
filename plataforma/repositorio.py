"""Acesso ao banco (Supabase/PostgREST) com isolamento por empresa.

Duas travas independentes:
1. Row Level Security no Postgres (a principal — vale mesmo se o app errar);
2. todo acesso a dados passa por `_da_empresa`, que exige o `empresa_id` e
   aplica `.eq("empresa_id", ...)` em toda consulta.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

TAMANHO_PAGINA = 1000  # limite padrão de linhas por resposta do PostgREST no Supabase
CAMPOS_EDITAVEIS_EMPRESA = {"nome", "setor", "tom_de_voz", "moeda"}  # `plano` só via service_role


def _da_empresa(client, tabela: str, empresa_id: str, colunas: str = "*"):
    if not empresa_id:
        raise ValueError("empresa_id é obrigatório em consultas de dados")
    return client.table(tabela).select(colunas).eq("empresa_id", empresa_id)


def _todas_as_paginas(consulta) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    inicio = 0
    while True:
        pagina = consulta.range(inicio, inicio + TAMANHO_PAGINA - 1).execute().data or []
        linhas.extend(pagina)
        if len(pagina) < TAMANHO_PAGINA:
            return linhas
        inicio += TAMANHO_PAGINA


# --- Empresas e membros -------------------------------------------------------

def empresas_do_usuario(client, usuario_id: str) -> list[dict[str, Any]]:
    """Empresas em que o usuário é membro, com o papel dele em cada uma."""
    resposta = (
        client.table("membros")
        .select("papel, empresas(id, nome, setor, tom_de_voz, moeda, plano)")
        .eq("usuario_id", usuario_id)
        .execute()
    )
    empresas = []
    for linha in resposta.data or []:
        empresa = dict(linha.get("empresas") or {})
        if empresa:
            empresa["papel"] = linha["papel"]
            empresas.append(empresa)
    return sorted(empresas, key=lambda e: e["nome"].lower())


def criar_empresa(client, nome: str, setor: str | None, tom_de_voz: str | None, moeda: str) -> str:
    """Cria a empresa via RPC (quem chama vira admin) e devolve o id."""
    resposta = client.rpc(
        "criar_empresa",
        {"p_nome": nome, "p_setor": setor, "p_tom_de_voz": tom_de_voz, "p_moeda": moeda},
    ).execute()
    return resposta.data


def atualizar_empresa(client, empresa_id: str, campos: dict[str, Any]) -> None:
    proibidos = set(campos) - CAMPOS_EDITAVEIS_EMPRESA
    if proibidos:
        raise ValueError(f"Campos não editáveis: {sorted(proibidos)}")
    client.table("empresas").update(campos).eq("id", empresa_id).execute()


# --- Segmentação --------------------------------------------------------------

def ultima_execucao(client, empresa_id: str) -> dict[str, Any] | None:
    resposta = (
        _da_empresa(client, "execucoes_segmentacao", empresa_id)
        .eq("status", "concluida")
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
    )
    return (resposta.data or [None])[0]


def buscar_execucao(client, empresa_id: str, execucao_id: str) -> dict[str, Any] | None:
    resposta = _da_empresa(client, "execucoes_segmentacao", empresa_id).eq("id", execucao_id).limit(1).execute()
    return (resposta.data or [None])[0]


def clientes_segmentados(client, empresa_id: str, execucao_id: str) -> pd.DataFrame:
    consulta = (
        _da_empresa(client, "clientes_segmentados", empresa_id,
                    "cliente_id, recency, frequency, monetary, cluster, segmento")
        .eq("execucao_id", execucao_id)
        .order("cliente_id")
    )
    df = pd.DataFrame(_todas_as_paginas(consulta),
                      columns=["cliente_id", "recency", "frequency", "monetary", "cluster", "segmento"])
    df["monetary"] = pd.to_numeric(df["monetary"])
    return df


def resumo_segmentos(client, empresa_id: str, execucao_id: str) -> pd.DataFrame:
    resposta = _da_empresa(client, "resumo_segmentos", empresa_id).eq("execucao_id", execucao_id).execute()
    return pd.DataFrame(resposta.data or [])


def estrategias(client, empresa_id: str, execucao_id: str) -> dict[str, dict]:
    resposta = (
        _da_empresa(client, "estrategias_ia", empresa_id, "segmento, persona")
        .eq("execucao_id", execucao_id)
        .execute()
    )
    return {linha["segmento"]: linha["persona"] for linha in resposta.data or []}


# --- Importação de dados (escrita) --------------------------------------------
# Toda linha gravada recebe o empresa_id aqui, nunca vindo do arquivo enviado.

TAMANHO_LOTE = 2000  # linhas por requisição de escrita
COLUNAS_TRANSACAO = ["fatura_id", "cliente_id", "data_compra", "quantidade", "preco_unitario",
                     "produto_codigo", "produto_descricao", "pais"]


def _registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → lista de dicts serializável em JSON (NaN vira null, datas viram ISO)."""
    import json

    return json.loads(df.to_json(orient="records", date_format="iso"))


def _inserir_em_lotes(client, tabela: str, registros: list[dict[str, Any]], ao_progredir=None) -> None:
    total = len(registros)
    for inicio in range(0, total, TAMANHO_LOTE):
        client.table(tabela).insert(registros[inicio:inicio + TAMANHO_LOTE], returning="minimal").execute()
        if ao_progredir:
            ao_progredir(min(inicio + TAMANHO_LOTE, total), total)


def criar_importacao(client, empresa_id: str, arquivo_nome: str, mapeamento: dict[str, str]) -> str:
    resposta = client.table("importacoes").insert({
        "empresa_id": empresa_id, "arquivo_nome": arquivo_nome,
        "mapeamento": mapeamento, "status": "processando",
    }).execute()
    return resposta.data[0]["id"]


def finalizar_importacao(client, empresa_id: str, importacao_id: str, status: str,
                         relatorio: dict | None = None, erro: str | None = None) -> None:
    (client.table("importacoes")
     .update({"status": status, "relatorio_limpeza": relatorio, "erro": erro})
     .eq("empresa_id", empresa_id).eq("id", importacao_id).execute())


def inserir_transacoes(client, empresa_id: str, importacao_id: str, transacoes: pd.DataFrame,
                       ao_progredir=None) -> None:
    colunas = [c for c in COLUNAS_TRANSACAO if c in transacoes.columns]
    df = transacoes[colunas].copy()
    df["empresa_id"] = empresa_id
    df["importacao_id"] = importacao_id
    _inserir_em_lotes(client, "transacoes", _registros(df), ao_progredir)


def transacoes_da_empresa(client, empresa_id: str) -> pd.DataFrame:
    """Todas as transações já gravadas da empresa (para recalcular o RFM ao acrescentar dados)."""
    colunas = ["fatura_id", "cliente_id", "data_compra", "quantidade", "preco_unitario",
               "produto_codigo", "produto_descricao"]
    consulta = _da_empresa(client, "transacoes", empresa_id, ", ".join(colunas)).order("id")
    df = pd.DataFrame(_todas_as_paginas(consulta), columns=colunas)
    df["data_compra"] = pd.to_datetime(df["data_compra"], utc=True, format="ISO8601").dt.tz_localize(None)
    df["quantidade"] = pd.to_numeric(df["quantidade"])
    df["preco_unitario"] = pd.to_numeric(df["preco_unitario"])
    return df


def apagar_transacoes_de_outras_importacoes(client, empresa_id: str, importacao_id: str) -> None:
    """Usado no modo "substituir": só depois que a nova importação foi gravada com sucesso."""
    (client.table("transacoes").delete()
     .eq("empresa_id", empresa_id).neq("importacao_id", importacao_id).execute())


def apagar_transacoes_da_importacao(client, empresa_id: str, importacao_id: str) -> None:
    """Desfaz uma importação que falhou no meio."""
    (client.table("transacoes").delete()
     .eq("empresa_id", empresa_id).eq("importacao_id", importacao_id).execute())


def criar_execucao(client, empresa_id: str, data_referencia: str, k: int, parametros: dict,
                   produtos_por_segmento: dict | None = None) -> str:
    resposta = client.table("execucoes_segmentacao").insert({
        "empresa_id": empresa_id, "data_referencia": data_referencia, "k": k,
        "parametros": parametros, "produtos_por_segmento": produtos_por_segmento or {},
        "status": "processando",
    }).execute()
    return resposta.data[0]["id"]


def inserir_clientes_segmentados(client, empresa_id: str, execucao_id: str, clientes: pd.DataFrame,
                                 ao_progredir=None) -> None:
    df = clientes[["cliente_id", "recency", "frequency", "monetary", "cluster", "segmento"]].copy()
    df["empresa_id"] = empresa_id
    df["execucao_id"] = execucao_id
    _inserir_em_lotes(client, "clientes_segmentados", _registros(df), ao_progredir)


def finalizar_execucao(client, empresa_id: str, execucao_id: str, status: str, **campos) -> None:
    (client.table("execucoes_segmentacao")
     .update({"status": status, **campos})
     .eq("empresa_id", empresa_id).eq("id", execucao_id).execute())


def salvar_estrategias(client, empresa_id: str, execucao_id: str, personas: list) -> None:
    """Grava (ou substitui) uma persona por segmento da execução. `personas`: lista de PersonaGerada."""
    linhas = [{
        "empresa_id": empresa_id, "execucao_id": execucao_id, "segmento": p.segmento, "persona": p.persona,
        "modelo": p.modelo, "versao_prompt": p.versao_prompt,
        "tokens_entrada": p.tokens_entrada, "tokens_saida": p.tokens_saida,
    } for p in personas]
    client.table("estrategias_ia").upsert(linhas, on_conflict="execucao_id,segmento").execute()


# --- Contatos dos clientes (dados pessoais) -----------------------------------

def salvar_contatos(client, empresa_id: str, contatos: pd.DataFrame) -> None:
    """Grava ou atualiza um contato por cliente. Campos vazios no arquivo novo não apagam os anteriores."""
    for campo in ("nome", "email", "telefone"):
        grupo = contatos.loc[contatos[campo].notna(), ["cliente_id", campo]].copy()
        if grupo.empty:
            continue
        grupo["empresa_id"] = empresa_id
        registros = _registros(grupo)
        for inicio in range(0, len(registros), TAMANHO_LOTE):
            (client.table("contatos_clientes")
             .upsert(registros[inicio:inicio + TAMANHO_LOTE], on_conflict="empresa_id,cliente_id",
                     returning="minimal")
             .execute())


def contatos(client, empresa_id: str) -> pd.DataFrame:
    consulta = _da_empresa(client, "contatos_clientes", empresa_id, "cliente_id, nome, email, telefone").order("cliente_id")
    return pd.DataFrame(_todas_as_paginas(consulta), columns=["cliente_id", "nome", "email", "telefone"])
