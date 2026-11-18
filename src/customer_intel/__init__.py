"""Pipeline reutilizável de Customer Intelligence (limpeza → RFM → segmentação → personas).

Extraído dos notebooks para que o SaaS multi-tenant possa executá-lo a cada
importação de dados de uma empresa, sem depender do Jupyter.
"""

from customer_intel.limpeza import COLUNAS_PADRAO, RelatorioLimpeza, limpar_transacoes, mapear_colunas
from customer_intel.rfm import calcular_rfm
from customer_intel.segmentacao import ResultadoSegmentacao, avaliar_k, nomear_segmentos, segmentar
from customer_intel.pipeline import executar_pipeline

__all__ = [
    "COLUNAS_PADRAO",
    "RelatorioLimpeza",
    "ResultadoSegmentacao",
    "avaliar_k",
    "calcular_rfm",
    "executar_pipeline",
    "limpar_transacoes",
    "mapear_colunas",
    "nomear_segmentos",
    "segmentar",
]
