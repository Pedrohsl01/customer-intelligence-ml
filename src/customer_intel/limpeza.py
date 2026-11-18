"""Padronização e limpeza de transações enviadas por uma empresa (tenant).

Cada empresa exporta os dados com nomes de colunas diferentes. `mapear_colunas`
converte para o formato padrão e `limpar_transacoes` aplica as regras validadas
no notebook 01, mantendo as devoluções (marcadas em `eh_devolucao`) para que o
valor monetário possa ser calculado de forma líquida.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

# Colunas do formato padrão (espelham a tabela `transacoes` do banco).
COLUNAS_OBRIGATORIAS = ["fatura_id", "cliente_id", "data_compra", "quantidade", "preco_unitario"]
COLUNAS_OPCIONAIS = ["produto_codigo", "produto_descricao", "pais",
                     "cliente_nome", "cliente_email", "cliente_telefone"]
COLUNAS_PADRAO = COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS

# Mapeamento do dataset público "Online Retail" (UCI), usado no portfólio.
MAPEAMENTO_ONLINE_RETAIL = {
    "InvoiceNo": "fatura_id",
    "CustomerID": "cliente_id",
    "InvoiceDate": "data_compra",
    "Quantity": "quantidade",
    "UnitPrice": "preco_unitario",
    "StockCode": "produto_codigo",
    "Description": "produto_descricao",
    "Country": "pais",
}


@dataclass
class RelatorioLimpeza:
    """Quantas linhas cada regra removeu — exibido ao usuário após o upload."""

    linhas_lidas: int = 0
    sem_cliente: int = 0
    data_invalida: int = 0
    preco_invalido: int = 0
    quantidade_zero: int = 0
    duplicadas: int = 0
    linhas_validas: int = 0
    devolucoes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def mapear_colunas(df: pd.DataFrame, mapeamento: dict[str, str]) -> pd.DataFrame:
    """Renomeia as colunas da empresa para o formato padrão e valida as obrigatórias."""
    destinos = list(mapeamento.values())
    repetidos = {c for c in destinos if destinos.count(c) > 1}
    if repetidos:
        raise ValueError(f"Mais de uma coluna mapeada para: {sorted(repetidos)}")

    ausentes_origem = [c for c in mapeamento if c not in df.columns]
    if ausentes_origem:
        raise ValueError(f"Colunas não encontradas no arquivo: {ausentes_origem}")

    df = df.rename(columns=mapeamento)
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas obrigatórias sem mapeamento: {faltando}")

    presentes = [c for c in COLUNAS_PADRAO if c in df.columns]
    return df[presentes].copy()


def _normalizar_id(serie: pd.Series) -> pd.Series:
    """IDs como texto sem o sufixo '.0' que o pandas cria ao ler inteiros com nulos."""
    texto = serie.astype("string").str.strip()
    texto = texto.str.replace(r"\.0$", "", regex=True)
    return texto.mask(texto == "")


def converter_numeros(serie: pd.Series) -> pd.Series:
    """Converte para número aceitando o formato brasileiro ("1.234,56")."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie
    # Remove só símbolo de moeda e espaços; qualquer outra coisa (ex.: uma data) vira inválido.
    texto = serie.astype("string").str.replace(r"R\$|US\$|[$£€\s]", "", regex=True)
    if texto.str.contains(r",\d{1,2}$", na=False).any():   # vírgula decimal: 1.234,56
        texto = texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    elif texto.str.contains(",", na=False).any():          # vírgula de milhar: 1,234.56
        texto = texto.str.replace(",", "", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def detectar_dia_primeiro(serie: pd.Series, amostra: int = 2000) -> bool | None:
    """Descobre se datas como "03/04/2024" são dia/mês ou mês/dia.

    Retorna True (dia primeiro), False (mês primeiro) ou None quando a amostra
    é ambígua ou a coluna não está nesse formato (ex.: ISO "2024-04-03").
    """
    if pd.api.types.is_datetime64_any_dtype(serie):
        return None
    partes = serie.dropna().astype("string").head(amostra).str.extract(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
    partes = partes.dropna().astype(int)
    if partes.empty:
        return None
    if (partes[0] > 12).any():
        return True
    if (partes[1] > 12).any():
        return False
    return None


def converter_datas(serie: pd.Series, dia_primeiro: bool = False) -> pd.Series:
    """Converte para datetime. `dia_primeiro` só vale para datas que não começam pelo ano:
    aplicado a datas ISO ("2024-04-03"), o pandas trocaria mês e dia."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    texto = serie.astype("string").str.strip()
    # Só aceita o que tem cara de data (03/04/2024, 2024-04-03, "3 abr 2024"): sem isso o
    # parser converteria números soltos (ex.: uma coluna de preço mapeada por engano).
    parece_data = texto.str.contains(r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}|[A-Za-z]{3}", na=False)
    texto = texto.where(parece_data)
    comeca_pelo_ano = texto.str.match(r"^\d{4}[-/]", na=False).mean() > 0.5
    if comeca_pelo_ano:
        datas = pd.to_datetime(texto, errors="coerce", format="ISO8601")
    else:
        datas = pd.to_datetime(texto, errors="coerce", format="mixed", dayfirst=dia_primeiro)
    if getattr(datas.dt, "tz", None) is not None:
        datas = datas.dt.tz_convert("UTC").dt.tz_localize(None)
    return datas


def limpar_transacoes(df: pd.DataFrame, dia_primeiro: bool = False) -> tuple[pd.DataFrame, RelatorioLimpeza]:
    """Aplica as regras de limpeza ao DataFrame já no formato padrão.

    Regras:
    - remove linhas sem cliente, com data inválida, preço <= 0 ou quantidade 0;
    - remove duplicatas exatas (registros repetidos no sistema de origem);
    - mantém devoluções (quantidade negativa), marcando `eh_devolucao`.
    """
    relatorio = RelatorioLimpeza(linhas_lidas=len(df))
    df = df.copy()

    df["fatura_id"] = _normalizar_id(df["fatura_id"])
    df["cliente_id"] = _normalizar_id(df["cliente_id"])
    df["data_compra"] = converter_datas(df["data_compra"], dia_primeiro)
    df["quantidade"] = converter_numeros(df["quantidade"])
    df["preco_unitario"] = converter_numeros(df["preco_unitario"])

    def remover(mascara: pd.Series, campo: str) -> None:
        nonlocal df
        setattr(relatorio, campo, int(mascara.sum()))
        df = df[~mascara]

    remover(df["cliente_id"].isna() | df["fatura_id"].isna(), "sem_cliente")
    remover(df["data_compra"].isna(), "data_invalida")
    remover(df["preco_unitario"].isna() | (df["preco_unitario"] <= 0), "preco_invalido")
    remover(df["quantidade"].isna() | (df["quantidade"] == 0), "quantidade_zero")

    duplicadas = df.duplicated(keep="first")
    relatorio.duplicadas = int(duplicadas.sum())
    df = df[~duplicadas].copy()

    df["eh_devolucao"] = df["quantidade"] < 0
    df["valor"] = df["quantidade"] * df["preco_unitario"]

    relatorio.linhas_validas = len(df)
    relatorio.devolucoes = int(df["eh_devolucao"].sum())
    return df.reset_index(drop=True), relatorio
