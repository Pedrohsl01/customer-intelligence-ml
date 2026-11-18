"""Orquestração: dados brutos de uma empresa → clientes segmentados."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from customer_intel.limpeza import RelatorioLimpeza, limpar_transacoes, mapear_colunas
from customer_intel.rfm import calcular_rfm
from customer_intel.segmentacao import ResultadoSegmentacao, segmentar


@dataclass
class ResultadoPipeline:
    transacoes: pd.DataFrame
    relatorio_limpeza: RelatorioLimpeza
    data_referencia: pd.Timestamp
    segmentacao: ResultadoSegmentacao


def executar_pipeline(bruto: pd.DataFrame, mapeamento: dict[str, str] | None = None, k: int = 4,
                      data_referencia: pd.Timestamp | None = None) -> ResultadoPipeline:
    """Executa limpeza, RFM e segmentação. A geração de personas fica separada
    (`customer_intel.personas`) porque depende de API externa e tem custo."""
    padrao = mapear_colunas(bruto, mapeamento) if mapeamento else bruto
    transacoes, relatorio = limpar_transacoes(padrao)
    if transacoes.empty:
        raise ValueError("Nenhuma transação válida após a limpeza.")

    if data_referencia is None:
        data_referencia = transacoes["data_compra"].max() + pd.Timedelta(days=1)

    rfm = calcular_rfm(transacoes, data_referencia)
    return ResultadoPipeline(
        transacoes=transacoes,
        relatorio_limpeza=relatorio,
        data_referencia=data_referencia,
        segmentacao=segmentar(rfm, k=k),
    )
