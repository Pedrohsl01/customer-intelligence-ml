from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from plataforma import importacao
from tests.fake_supabase import FakeSupabase

HOME = str(Path(__file__).resolve().parent.parent / "home.py")
EMPRESA_A, EMPRESA_B = "empresa-a", "empresa-b"
MAPA = {"Pedido": "fatura_id", "Cliente": "cliente_id", "Data": "data_compra",
        "Qtd": "quantidade", "Preço": "preco_unitario"}


def _vendas(n_clientes=120, semente=0, prefixo="cli", ano=2024) -> pd.DataFrame:
    """Arquivo no estilo de um ERP brasileiro: tudo texto, data dd/mm/aaaa e decimal com vírgula."""
    rng = np.random.default_rng(semente)
    linhas = []
    for c in range(n_clientes):
        for f in range(int(rng.integers(1, 10))):
            dia = pd.Timestamp(f"{ano}-01-01") + pd.Timedelta(days=int(rng.integers(0, 360)))
            preco = f"{rng.uniform(5, 300):.2f}".replace(".", ",")
            linhas.append([f"{prefixo}{c}-{f}", f"{prefixo}{c}", dia.strftime("%d/%m/%Y"),
                           str(int(rng.integers(1, 8))), preco])
    return pd.DataFrame(linhas, columns=list(MAPA))


def _banco_com_empresa_b() -> FakeSupabase:
    return FakeSupabase({"transacoes": [
        {"id": "tb1", "empresa_id": EMPRESA_B, "importacao_id": "imp-b", "fatura_id": "B1", "cliente_id": "X",
         "data_compra": "2024-01-01T00:00:00+00:00", "quantidade": 1, "preco_unitario": 9.0},
    ]})


def _processar(banco, df, **kwargs):
    return importacao.processar_base(banco, EMPRESA_A, df, MAPA, "vendas.csv", dia_primeiro=True, **kwargs)


# --- leitura e mapeamento -----------------------------------------------------

def test_sugestao_de_mapeamento_para_o_online_retail():
    colunas = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]
    assert importacao.sugerir_mapeamento(colunas) == {
        "fatura_id": "InvoiceNo", "cliente_id": "CustomerID", "data_compra": "InvoiceDate",
        "quantidade": "Quantity", "preco_unitario": "UnitPrice", "produto_codigo": "StockCode",
        "produto_descricao": "Description", "pais": "Country",
        "cliente_nome": None, "cliente_email": None, "cliente_telefone": None,
    }


def test_sugestao_de_mapeamento_em_portugues_com_acentos():
    sugestao = importacao.sugerir_mapeamento(["Número Pedido", "Código Cliente", "Data", "Qtd", "Preço"])
    assert sugestao["fatura_id"] == "Número Pedido" and sugestao["cliente_id"] == "Código Cliente"
    assert sugestao["preco_unitario"] == "Preço" and sugestao["pais"] is None


def test_ler_csv_com_ponto_e_virgula_e_latin1():
    conteudo = "Pedido;Cliente;Preço\n001;17850;10,50\n".encode("latin-1")
    df = importacao.ler_arquivo("vendas.csv", conteudo)
    assert list(df.columns) == ["Pedido", "Cliente", "Preço"]
    assert df.loc[0, "Pedido"] == "001" and df.loc[0, "Cliente"] == "17850"  # IDs preservados como texto


def test_ler_arquivo_recusa_formato_desconhecido():
    with pytest.raises(importacao.ErroImportacao, match="Formato"):
        importacao.ler_arquivo("vendas.pdf", b"x")


# --- processar_base -----------------------------------------------------------

def test_processar_grava_tudo_com_o_empresa_id_e_nao_toca_em_outra_empresa():
    banco = _banco_com_empresa_b()
    resultado = _processar(banco, _vendas())

    novas = [t for t in banco.tabelas["transacoes"] if t["empresa_id"] == EMPRESA_A]
    assert len(novas) == resultado.transacoes_gravadas > 0
    assert all(t["importacao_id"] == resultado.importacao_id for t in novas)
    assert [t["id"] for t in banco.tabelas["transacoes"] if t["empresa_id"] == EMPRESA_B] == ["tb1"]

    segmentados = banco.tabelas["clientes_segmentados"]
    assert len(segmentados) == 120
    assert {s["empresa_id"] for s in segmentados} == {EMPRESA_A}
    assert {s["execucao_id"] for s in segmentados} == {resultado.execucao_id}

    execucao = banco.tabelas["execucoes_segmentacao"][0]
    assert execucao["status"] == "concluida" and execucao["total_clientes"] == 120 and execucao["k"] == 4
    assert banco.tabelas["importacoes"][0]["status"] == "concluida"
    assert banco.tabelas["importacoes"][0]["relatorio_limpeza"]["linhas_validas"] == len(novas)

    # formato brasileiro foi entendido: 31/12 é dezembro e o preço tem centavos
    assert all(isinstance(t["preco_unitario"], float) for t in novas)
    assert max(t["data_compra"] for t in novas) > "2024-06"


def test_substituir_remove_as_vendas_antigas_da_empresa():
    banco = _banco_com_empresa_b()
    _processar(banco, _vendas(prefixo="antigo"))
    resultado = _processar(banco, _vendas(prefixo="novo", semente=1), modo=importacao.SUBSTITUIR)

    da_empresa = [t for t in banco.tabelas["transacoes"] if t["empresa_id"] == EMPRESA_A]
    assert {t["importacao_id"] for t in da_empresa} == {resultado.importacao_id}
    assert all(t["cliente_id"].startswith("novo") for t in da_empresa)
    assert any(t["empresa_id"] == EMPRESA_B for t in banco.tabelas["transacoes"])
    assert len(banco.tabelas["execucoes_segmentacao"]) == 2  # histórico de execuções preservado


def test_acrescentar_soma_clientes_e_ignora_vendas_repetidas():
    banco = FakeSupabase()
    _processar(banco, _vendas(n_clientes=60, prefixo="a"))
    total_antes = len(banco.tabelas["transacoes"])

    misto = pd.concat([_vendas(n_clientes=60, prefixo="a"), _vendas(n_clientes=50, prefixo="b", semente=2)])
    resultado = _processar(banco, misto, modo=importacao.ACRESCENTAR)

    assert resultado.linhas_ja_importadas == total_antes
    assert len(banco.tabelas["transacoes"]) == total_antes + resultado.transacoes_gravadas
    assert len(resultado.segmentacao.clientes) == 110  # RFM recalculado com a base inteira


def test_acrescentar_o_mesmo_arquivo_nao_duplica():
    banco = FakeSupabase()
    _processar(banco, _vendas())
    total = len(banco.tabelas["transacoes"])
    with pytest.raises(importacao.ErroImportacao, match="já tinham sido importadas"):
        _processar(banco, _vendas(), modo=importacao.ACRESCENTAR)
    assert len(banco.tabelas["transacoes"]) == total
    assert len(banco.tabelas["importacoes"]) == 1


def test_poucos_clientes_nao_grava_nada():
    banco = FakeSupabase()
    with pytest.raises(importacao.ErroImportacao, match="mais de 4 clientes"):
        _processar(banco, _vendas(n_clientes=3))
    assert banco.tabelas == {}


def test_mapeamento_errado_gera_erro_amigavel():
    banco = FakeSupabase()
    mapa_errado = {**MAPA, "Data": "preco_unitario", "Preço": "data_compra"}
    with pytest.raises(importacao.ErroImportacao, match="Nenhuma linha válida"):
        importacao.processar_base(banco, EMPRESA_A, _vendas(), mapa_errado, "v.csv")
    assert banco.tabelas == {}


def test_falha_ao_gravar_vendas_desfaz_a_importacao():
    banco = FakeSupabase()
    banco.falhar_em = ("insert", "transacoes")
    with pytest.raises(importacao.ErroImportacao, match="Falha ao gravar"):
        _processar(banco, _vendas())
    assert banco.tabelas.get("transacoes", []) == []
    assert banco.tabelas["importacoes"][0]["status"] == "erro"
    assert "execucoes_segmentacao" not in banco.tabelas


def test_falha_ao_gravar_segmentos_nao_publica_execucao():
    banco = FakeSupabase()
    banco.falhar_em = ("insert", "clientes_segmentados")
    with pytest.raises(importacao.ErroImportacao):
        _processar(banco, _vendas())
    assert banco.tabelas["execucoes_segmentacao"][0]["status"] == "erro"  # dashboard só lê "concluida"


# --- tela (Streamlit AppTest) -------------------------------------------------

def _app(banco, papel="analista"):
    empresa = {"id": EMPRESA_A, "nome": "Loja A", "setor": "Pet Shop", "tom_de_voz": "Formal",
               "moeda": "BRL", "plano": "free", "papel": papel}
    at = AppTest.from_file(HOME, default_timeout=120)
    at.session_state["_supabase_client"] = banco
    at.session_state["usuario"] = {"id": "u1", "email": "ana@loja-a.test", "nome": "Ana"}
    at.session_state["empresas"] = [empresa]
    at.session_state["empresa_atual_id"] = EMPRESA_A
    return at


def test_leitor_nao_importa():
    at = _app(FakeSupabase(), papel="leitor")
    at.switch_page("paginas/importar.py").run()
    assert not at.exception
    assert any("Somente administradores e analistas" in i.value for i in at.info)
    assert len(at.file_uploader) == 0


def test_upload_processa_e_dashboard_mostra_a_base_da_empresa():
    banco = _banco_com_empresa_b()
    at = _app(banco)
    at.switch_page("paginas/importar.py").run()
    assert not at.exception

    csv = _vendas().to_csv(index=False, sep=";").encode("utf-8")
    at.file_uploader[0].set_value(("vendas.csv", csv, "text/csv")).run()
    assert not at.exception
    # colunas sugeridas automaticamente e formato de data detectado como Dia/Mês/Ano
    sugeridas = {s.label: s.value for s in at.selectbox}
    assert sugeridas["Número do pedido / nota *"] == "Pedido"
    assert sugeridas["Código do cliente *"] == "Cliente"
    assert sugeridas["Data da compra *"] == "Data"
    assert sugeridas["Quantidade *"] == "Qtd"
    assert sugeridas["Preço unitário *"] == "Preço"
    assert sugeridas["País"] == "— não tem —"
    assert at.radio[0].value == "Dia/Mês/Ano"

    botao = next(b for b in at.button if "Processar Base" in b.label)
    botao.click().run()
    assert not at.exception
    assert any("120 clientes segmentados" in s.value for s in at.success)

    at.switch_page("app.py").run()
    assert not at.exception
    assert at.metric[0].value == "120"
    assert at.metric[3].value.startswith("R$")
