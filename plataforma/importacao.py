"""Importação de vendas de uma empresa e execução do motor RFM + K-Means.

Fluxo de `processar_base`:
1. converte as colunas do arquivo para o formato padrão e limpa os dados;
2. grava as transações na tabela `transacoes` da empresa;
3. recalcula o RFM com TODAS as transações da empresa, aplica log1p +
   StandardScaler e roda o K-Means só com os clientes dela;
4. grava uma nova execução em `execucoes_segmentacao` + `clientes_segmentados`.

O dashboard só lê execuções com status "concluida", então uma falha no meio
nunca deixa dados pela metade visíveis.
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from customer_intel.contatos import extrair_contatos
from customer_intel.limpeza import COLUNAS_OBRIGATORIAS, COLUNAS_OPCIONAIS, limpar_transacoes, mapear_colunas
from customer_intel.produtos import produtos_por_segmento
from customer_intel.rfm import calcular_rfm
from customer_intel.segmentacao import ResultadoSegmentacao, segmentar
from plataforma import repositorio

SUBSTITUIR = "substituir"
ACRESCENTAR = "acrescentar"

EXTENSOES = ("csv", "xlsx")
LIMITE_LINHAS = 1_000_000

ROTULOS = {
    "fatura_id": "Número do pedido / nota",
    "cliente_id": "Código do cliente",
    "data_compra": "Data da compra",
    "quantidade": "Quantidade",
    "preco_unitario": "Preço unitário",
    "produto_codigo": "Código do produto",
    "produto_descricao": "Descrição do produto",
    "pais": "País",
    "cliente_nome": "Nome do cliente",
    "cliente_email": "E-mail do cliente",
    "cliente_telefone": "Telefone / WhatsApp do cliente",
}

# Nomes comuns em exportações de e-commerce/ERP, já sem acentos e em minúsculas.
SINONIMOS = {
    "fatura_id": ["fatura_id", "invoiceno", "invoice", "invoice_id", "pedido", "pedido_id", "id_pedido",
                  "numero_pedido", "order_id", "orderid", "order", "nota", "nota_fiscal", "nf", "fatura"],
    "cliente_id": ["cliente_id", "customerid", "customer_id", "customer", "id_cliente", "cliente",
                   "codigo_cliente", "cod_cliente", "cpf", "cnpj", "cpf_cnpj", "email"],
    "data_compra": ["data_compra", "invoicedate", "invoice_date", "data", "data_pedido", "data_venda",
                    "order_date", "date", "created_at", "dt_compra", "dt_venda"],
    "quantidade": ["quantidade", "quantity", "qtd", "qtde", "qty", "itens", "unidades"],
    "preco_unitario": ["preco_unitario", "unitprice", "unit_price", "preco", "price", "valor_unitario",
                       "vl_unitario", "preco_unit"],
    "produto_codigo": ["produto_codigo", "stockcode", "sku", "codigo_produto", "cod_produto", "product_id",
                       "id_produto"],
    "produto_descricao": ["produto_descricao", "description", "descricao", "produto", "product", "nome_produto",
                          "product_name"],
    "pais": ["pais", "country"],
    "cliente_nome": ["cliente_nome", "nome_cliente", "nome", "customer_name", "name", "first_name",
                     "nome_completo", "razao_social"],
    "cliente_email": ["cliente_email", "email_cliente", "email", "e_mail", "customer_email", "mail"],
    "cliente_telefone": ["cliente_telefone", "telefone", "celular", "whatsapp", "fone", "phone", "mobile",
                         "telefone_cliente", "tel"],
}


class ErroImportacao(Exception):
    """Erro com mensagem pronta para ser mostrada ao usuário."""


@dataclass
class ResultadoImportacao:
    importacao_id: str
    execucao_id: str
    relatorio: dict
    linhas_ja_importadas: int
    transacoes_gravadas: int
    segmentacao: ResultadoSegmentacao


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "_" for c in sem_acento.lower()).strip("_")


def ler_arquivo(nome: str, conteudo: bytes) -> pd.DataFrame:
    """Lê CSV ou XLSX como texto (sem o pandas adivinhar tipos e estragar IDs e datas)."""
    extensao = nome.rsplit(".", 1)[-1].lower()
    try:
        if extensao == "xlsx":
            df = pd.read_excel(io.BytesIO(conteudo), dtype=str)
        elif extensao == "csv":
            for encoding in ("utf-8-sig", "latin-1"):
                try:
                    df = pd.read_csv(io.BytesIO(conteudo), dtype=str, sep=None, engine="python", encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            raise ErroImportacao("Formato não suportado. Envie um arquivo .csv ou .xlsx.")
    except ErroImportacao:
        raise
    except Exception as erro:
        raise ErroImportacao(f"Não foi possível ler o arquivo: {erro}") from erro

    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise ErroImportacao("O arquivo não tem nenhuma linha de dados.")
    if len(df) > LIMITE_LINHAS:
        raise ErroImportacao(f"O arquivo tem {len(df):,} linhas; o limite é {LIMITE_LINHAS:,}.")
    return df


def sugerir_mapeamento(colunas: list[str]) -> dict[str, str | None]:
    """Para cada coluna padrão, a coluna do arquivo que parece corresponder (ou None)."""
    normalizadas = {_normalizar(c): c for c in reversed(colunas)}
    sugestao: dict[str, str | None] = {}
    usadas: set[str] = set()
    for padrao in COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS:
        achada = next((normalizadas[s] for s in SINONIMOS[padrao]
                       if s in normalizadas and normalizadas[s] not in usadas), None)
        sugestao[padrao] = achada
        if achada:
            usadas.add(achada)
    return sugestao


def _remover_ja_importadas(novas: pd.DataFrame, existentes: pd.DataFrame) -> pd.DataFrame:
    """Evita duplicar vendas quando o mesmo arquivo (ou um período sobreposto) é enviado de novo."""
    if existentes.empty:
        return novas
    chaves = ["fatura_id", "cliente_id", "data_compra", "quantidade", "preco_unitario"]
    if "produto_codigo" in novas.columns:
        chaves.append("produto_codigo")

    def assinatura(df: pd.DataFrame) -> pd.Series:
        partes = df[chaves].copy()
        partes["data_compra"] = partes["data_compra"].dt.strftime("%Y-%m-%dT%H:%M:%S")
        partes["quantidade"] = partes["quantidade"].astype(float).round(3)
        partes["preco_unitario"] = partes["preco_unitario"].astype(float).round(4)
        return partes.astype("string").fillna("").agg("|".join, axis=1)

    return novas[~assinatura(novas).isin(set(assinatura(existentes)))].reset_index(drop=True)


def processar_base(client, empresa_id: str, bruto: pd.DataFrame, mapeamento: dict[str, str], arquivo_nome: str,
                   k: int = 4, modo: str = SUBSTITUIR, dia_primeiro: bool = False,
                   ao_progredir: Callable[[str, float], None] | None = None) -> ResultadoImportacao:
    """Executa a importação completa. `mapeamento` é {coluna do arquivo: coluna padrão}."""
    if modo not in (SUBSTITUIR, ACRESCENTAR):
        raise ValueError(f"Modo inválido: {modo}")

    def progresso(etapa: str, fracao: float) -> None:
        if ao_progredir:
            ao_progredir(etapa, fracao)

    # 1. Padronizar e limpar (nada é gravado se o arquivo não servir)
    progresso("Limpando os dados", 0.05)
    try:
        padrao = mapear_colunas(bruto, mapeamento)
    except ValueError as erro:
        raise ErroImportacao(str(erro)) from erro
    novas, relatorio = limpar_transacoes(padrao, dia_primeiro=dia_primeiro)
    novas["quantidade"] = novas["quantidade"].round(3)
    novas["preco_unitario"] = novas["preco_unitario"].round(4)
    novas = novas[novas["preco_unitario"] > 0].reset_index(drop=True)
    if novas.empty:
        raise ErroImportacao("Nenhuma linha válida após a limpeza. Confira o mapeamento das colunas "
                             "e o formato das datas e dos valores.")

    existentes = pd.DataFrame()
    linhas_ja_importadas = 0
    if modo == ACRESCENTAR:
        progresso("Lendo as vendas já importadas", 0.10)
        existentes = repositorio.transacoes_da_empresa(client, empresa_id)
        antes = len(novas)
        novas = _remover_ja_importadas(novas, existentes)
        linhas_ja_importadas = antes - len(novas)
        if novas.empty:
            raise ErroImportacao("Todas as vendas deste arquivo já tinham sido importadas.")

    # 2. Segmentar ANTES de gravar: se não houver clientes suficientes, nada muda no banco.
    progresso("Calculando RFM e segmentos", 0.15)
    base = novas if existentes.empty else pd.concat([existentes, novas], ignore_index=True)
    base["valor"] = base["quantidade"] * base["preco_unitario"]
    base["eh_devolucao"] = base["quantidade"] < 0
    data_referencia = base["data_compra"].max() + pd.Timedelta(days=1)
    rfm = calcular_rfm(base, data_referencia)
    try:
        segmentacao = segmentar(rfm, k=k)
    except ValueError as erro:
        raise ErroImportacao(str(erro)) from erro
    produtos = produtos_por_segmento(base, segmentacao.clientes)

    # 3. Gravar transações
    importacao_id = repositorio.criar_importacao(client, empresa_id, arquivo_nome, mapeamento)
    execucao_id = None
    try:
        repositorio.inserir_transacoes(
            client, empresa_id, importacao_id, novas,
            ao_progredir=lambda feito, total: progresso("Gravando as vendas", 0.20 + 0.55 * feito / total),
        )
        if modo == SUBSTITUIR:
            repositorio.apagar_transacoes_de_outras_importacoes(client, empresa_id, importacao_id)
        contatos = extrair_contatos(novas)
        if not contatos.empty:
            progresso("Gravando os contatos", 0.78)
            repositorio.salvar_contatos(client, empresa_id, contatos)
        repositorio.finalizar_importacao(client, empresa_id, importacao_id, "concluida", relatorio.to_dict())

        # 4. Gravar a segmentação
        execucao_id = repositorio.criar_execucao(
            client, empresa_id, data_referencia.date().isoformat(), k,
            {"modo": modo, "importacao_id": importacao_id, "transformacao": "log1p+StandardScaler"},
            produtos_por_segmento=produtos,
        )
        repositorio.inserir_clientes_segmentados(
            client, empresa_id, execucao_id, segmentacao.clientes,
            ao_progredir=lambda feito, total: progresso("Gravando os segmentos", 0.80 + 0.18 * feito / total),
        )
        repositorio.finalizar_execucao(
            client, empresa_id, execucao_id, "concluida",
            silhouette=segmentacao.silhouette, inertia=segmentacao.inertia,
            total_clientes=len(segmentacao.clientes), concluido_em=pd.Timestamp.now(tz="UTC").isoformat(),
        )
    except Exception as erro:
        _registrar_falha(client, empresa_id, importacao_id, execucao_id, str(erro))
        raise ErroImportacao("Falha ao gravar os dados no banco. Nenhuma segmentação foi alterada; "
                             f"tente novamente. Detalhe: {erro}") from erro

    progresso("Concluído", 1.0)
    return ResultadoImportacao(
        importacao_id=importacao_id,
        execucao_id=execucao_id,
        relatorio=relatorio.to_dict(),
        linhas_ja_importadas=linhas_ja_importadas,
        transacoes_gravadas=len(novas),
        segmentacao=segmentacao,
    )


def _registrar_falha(client, empresa_id: str, importacao_id: str, execucao_id: str | None, erro: str) -> None:
    """Melhor esforço: marca os registros como erro e desfaz as vendas da importação incompleta."""
    try:
        if execucao_id:
            repositorio.finalizar_execucao(client, empresa_id, execucao_id, "erro", erro=erro[:500])
        else:
            # Falhou antes de existir uma execução: as vendas novas ficariam sem segmentação.
            repositorio.apagar_transacoes_da_importacao(client, empresa_id, importacao_id)
            repositorio.finalizar_importacao(client, empresa_id, importacao_id, "erro", erro=erro[:500])
    except Exception:
        pass
