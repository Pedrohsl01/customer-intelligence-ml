"""Cálculo da matriz RFM por cliente."""

from __future__ import annotations

import pandas as pd


def calcular_rfm(transacoes: pd.DataFrame, data_referencia: pd.Timestamp | None = None) -> pd.DataFrame:
    """Calcula Recency, Frequency e Monetary por cliente.

    - Recency: dias entre a última compra e a data de referência
      (padrão: um dia após a última transação da base).
    - Frequency: número de faturas de compra distintas (devoluções não contam).
    - Monetary: valor LÍQUIDO — compras menos devoluções. Clientes com valor
      líquido <= 0 (devolveram tudo) são descartados, pois não têm valor a segmentar.

    Espera o DataFrame retornado por `limpar_transacoes`.
    """
    if data_referencia is None:
        data_referencia = transacoes["data_compra"].max() + pd.Timedelta(days=1)

    compras = transacoes[~transacoes["eh_devolucao"]]

    rfm = compras.groupby("cliente_id").agg(
        ultima_compra=("data_compra", "max"),
        frequency=("fatura_id", "nunique"),
    )
    rfm["recency"] = (data_referencia - rfm["ultima_compra"]).dt.days
    rfm["monetary"] = transacoes.groupby("cliente_id")["valor"].sum().reindex(rfm.index)

    rfm = rfm[rfm["monetary"] > 0]
    rfm = rfm[["recency", "frequency", "monetary"]].reset_index()
    rfm["recency"] = rfm["recency"].astype(int)
    rfm["frequency"] = rfm["frequency"].astype(int)
    rfm["monetary"] = rfm["monetary"].round(2)
    return rfm
