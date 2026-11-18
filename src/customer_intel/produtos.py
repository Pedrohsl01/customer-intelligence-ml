"""Produtos mais comprados por segmento — contexto para as campanhas geradas pela IA."""

from __future__ import annotations

import pandas as pd

TAMANHO_MAXIMO_NOME = 80


def produtos_por_segmento(transacoes: pd.DataFrame, clientes: pd.DataFrame, top: int = 5) -> dict[str, list[dict]]:
    """Para cada segmento, os `top` produtos com mais unidades compradas (devoluções não contam).

    `transacoes`: saída de `limpar_transacoes`; `clientes`: saída de `segmentar`
    (colunas cliente_id e segmento). Devolve {} se o arquivo não tinha colunas de produto.
    """
    tem_descricao = "produto_descricao" in transacoes.columns
    tem_codigo = "produto_codigo" in transacoes.columns
    if not tem_descricao and not tem_codigo:
        return {}

    compras = transacoes[transacoes["quantidade"] > 0].copy()
    nome = compras["produto_descricao"] if tem_descricao else pd.Series(pd.NA, index=compras.index, dtype="string")
    if tem_codigo:
        nome = nome.fillna(compras["produto_codigo"])
    compras["produto"] = nome.astype("string").str.strip().str.slice(0, TAMANHO_MAXIMO_NOME)
    compras = compras[compras["produto"].notna() & (compras["produto"] != "")]
    if compras.empty:
        return {}

    compras["valor"] = compras["quantidade"] * compras["preco_unitario"]
    compras = compras.merge(clientes[["cliente_id", "segmento"]], on="cliente_id", how="inner")
    ranking = (
        compras.groupby(["segmento", "produto"], as_index=False)
        .agg(quantidade=("quantidade", "sum"), receita=("valor", "sum"), clientes=("cliente_id", "nunique"))
        .sort_values(["segmento", "quantidade", "receita"], ascending=[True, False, False])
    )
    return {
        segmento: [
            {"produto": linha.produto, "quantidade": round(float(linha.quantidade), 3),
             "receita": round(float(linha.receita), 2), "clientes": int(linha.clientes)}
            for linha in grupo.head(top).itertuples()
        ]
        for segmento, grupo in ranking.groupby("segmento")
    }
