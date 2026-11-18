"""Segmentação K-Means sobre a matriz RFM e nomeação automática dos segmentos.

No SaaS cada empresa tem clusters próprios, então os nomes não podem ser
atribuídos à mão (o número de cada cluster no K-Means é arbitrário). Os nomes
vêm de regras aplicadas aos centróides no espaço padronizado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = ["recency", "frequency", "monetary"]

# Nome por quadrante: (compra recente?, compra com frequência?)
NOMES_QUADRANTE = {
    (True, True): "Clientes Fiéis",
    (True, False): "Clientes Promissores",
    (False, True): "Clientes em Risco",
    (False, False): "Clientes Inativos",
}
NOME_TOPO = "Clientes VIP"


@dataclass
class ResultadoSegmentacao:
    clientes: pd.DataFrame  # rfm + cluster + segmento
    resumo: pd.DataFrame  # uma linha por segmento
    k: int
    silhouette: float
    inertia: float
    scaler: StandardScaler = field(repr=False)
    modelo: KMeans = field(repr=False)


def _preparar(rfm: pd.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    scaler = StandardScaler()
    matriz = scaler.fit_transform(np.log1p(rfm[FEATURES]))
    return matriz, scaler


def avaliar_k(rfm: pd.DataFrame, ks: range = range(2, 11), random_state: int = 42) -> pd.DataFrame:
    """Inércia (cotovelo) e silhouette para cada K — exibido para justificar a escolha."""
    matriz, _ = _preparar(rfm)
    linhas = []
    for k in ks:
        modelo = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        rotulos = modelo.fit_predict(matriz)
        linhas.append({"k": k, "inertia": modelo.inertia_, "silhouette": silhouette_score(matriz, rotulos)})
    return pd.DataFrame(linhas)


def nomear_segmentos(centroides: np.ndarray) -> dict[int, str]:
    """Atribui um nome a cada cluster a partir dos centróides padronizados (R, F, M).

    1. Cada cluster recebe o nome do seu quadrante: recência abaixo da média
       (compra recente) × frequência acima da média.
    2. O cluster de melhor pontuação (-R + F + M) entre os recentes e frequentes
       vira "Clientes VIP".
    3. Nomes repetidos recebem um sufixo ordenado pela pontuação ("... 1", "... 2").
    """
    centroides = np.asarray(centroides)
    recency, frequency, monetary = centroides[:, 0], centroides[:, 1], centroides[:, 2]
    pontuacao = -recency + frequency + monetary

    nomes = {i: NOMES_QUADRANTE[(bool(recency[i] < 0), bool(frequency[i] > 0))] for i in range(len(centroides))}

    candidatos_vip = [i for i, nome in nomes.items() if nome == NOMES_QUADRANTE[(True, True)]]
    if candidatos_vip:
        nomes[max(candidatos_vip, key=lambda i: pontuacao[i])] = NOME_TOPO

    for nome in set(nomes.values()):
        grupo = sorted((i for i in nomes if nomes[i] == nome), key=lambda i: -pontuacao[i])
        if len(grupo) > 1:
            for posicao, i in enumerate(grupo, start=1):
                nomes[i] = f"{nome} {posicao}"
    return nomes


def resumir_segmentos(clientes: pd.DataFrame) -> pd.DataFrame:
    """Estatísticas por segmento. Medianas são o valor principal: RFM é muito assimétrico."""
    resumo = clientes.groupby(["cluster", "segmento"], as_index=False).agg(
        quantidade_clientes=("cliente_id", "count"),
        recency_media=("recency", "mean"),
        recency_mediana=("recency", "median"),
        frequency_media=("frequency", "mean"),
        frequency_mediana=("frequency", "median"),
        monetary_medio=("monetary", "mean"),
        monetary_mediano=("monetary", "median"),
        monetary_total=("monetary", "sum"),
    )
    resumo["ticket_medio"] = resumo["monetary_total"] / clientes.groupby("cluster")["frequency"].sum().reindex(
        resumo["cluster"]
    ).to_numpy()
    resumo["participacao_clientes"] = resumo["quantidade_clientes"] / resumo["quantidade_clientes"].sum()
    resumo["participacao_receita"] = resumo["monetary_total"] / resumo["monetary_total"].sum()
    return resumo.sort_values("monetary_mediano", ascending=False).reset_index(drop=True)


def segmentar(rfm: pd.DataFrame, k: int = 4, random_state: int = 42) -> ResultadoSegmentacao:
    """Treina o K-Means e devolve clientes segmentados, resumo e métricas."""
    if len(rfm) <= k:
        raise ValueError(f"São necessários mais de {k} clientes para segmentar em {k} grupos (recebidos: {len(rfm)}).")

    matriz, scaler = _preparar(rfm)
    modelo = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    rotulos = modelo.fit_predict(matriz)
    nomes = nomear_segmentos(modelo.cluster_centers_)

    clientes = rfm.copy()
    clientes["cluster"] = rotulos
    clientes["segmento"] = clientes["cluster"].map(nomes)

    return ResultadoSegmentacao(
        clientes=clientes,
        resumo=resumir_segmentos(clientes),
        k=k,
        silhouette=float(silhouette_score(matriz, rotulos)),
        inertia=float(modelo.inertia_),
        scaler=scaler,
        modelo=modelo,
    )
