"""Fase 5: contatos, mensagens personalizadas, lista de disparo, e-mail de teste e simulador de retorno."""

import io
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from customer_intel.contatos import extrair_contatos, normalizar_email, normalizar_telefone
from plataforma import campanhas, estrategias, importacao
from tests.fake_llm import FakeLLM
from tests.fake_supabase import FakeSupabase
from tests.test_importacao import MAPA, _vendas

HOME = str(Path(__file__).resolve().parent.parent / "home.py")
EMPRESA = {"id": "empresa-a", "nome": "Moda da Ana", "setor": "Moda Feminina", "tom_de_voz": "Urgente",
           "moeda": "BRL", "plano": "free", "papel": "admin"}
PERSONA = {
    "persona_nome": "P", "descricao_persona": "D", "estrategia_retencao": "E",
    "copy_notificacao_push": "{nome}, sua oferta acaba {validade}!",
    "oferta_sugerida": "15% OFF de retorno", "oferta_justificativa": "J",
    "email_assunto": "{nome}, voltamos com novidades",
    "email_corpo_html": '<p>Olá, {nome}!</p><p><a href="{link}">Ver oferta</a></p>',
    "mensagem_whatsapp": "Olá, {nome}! Só até {validade}: {link}",
}


def _vendas_com_contatos():
    df = _vendas()
    clientes = sorted(df["Cliente"].unique())
    nomes = {c: f"joão  silva {i}" for i, c in enumerate(clientes)}
    df["Nome"] = df["Cliente"].map(nomes)
    df["E-mail"] = df["Cliente"].map(lambda c: f"{c}@Exemplo.com")
    df["Celular"] = "(11) 98765-4321"
    df.loc[df.index[0], "E-mail"] = "invalido"
    return df


MAPA_CONTATOS = {**MAPA, "Nome": "cliente_nome", "E-mail": "cliente_email", "Celular": "cliente_telefone"}


# --- contatos -----------------------------------------------------------------

def test_normalizacao_de_contatos():
    assert normalizar_email(" Ana@Loja.COM ") == "ana@loja.com"
    assert normalizar_email("sem-arroba") is None
    assert normalizar_telefone("(11) 98765-4321") == "5511987654321"
    assert normalizar_telefone("+55 11 98765-4321") == "5511987654321"
    assert normalizar_telefone("1234") is None


def test_extrair_contatos_usa_o_valor_valido_mais_recente():
    df = pd.DataFrame({
        "cliente_id": ["a", "a", "b"],
        "data_compra": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-01-01"]),
        "cliente_email": ["velho@x.com", "novo@x.com", None],
        "cliente_nome": [None, "  maria  souza ", None],
    })
    contatos = extrair_contatos(df).set_index("cliente_id")
    assert contatos.loc["a", "email"] == "novo@x.com" and contatos.loc["a", "nome"] == "Maria Souza"
    assert "b" not in contatos.index  # sem nenhum contato válido


def test_importacao_grava_contatos_da_empresa():
    banco = FakeSupabase()
    importacao.processar_base(banco, EMPRESA["id"], _vendas_com_contatos(), MAPA_CONTATOS, "v.csv", dia_primeiro=True)
    contatos = banco.tabelas["contatos_clientes"]
    assert len(contatos) == 120
    assert all(c["empresa_id"] == EMPRESA["id"] for c in contatos)
    exemplo = next(c for c in contatos if c["cliente_id"] == "cli1")
    assert exemplo["email"] == "cli1@exemplo.com" and exemplo["telefone"] == "5511987654321"
    assert exemplo["nome"].startswith("João Silva")


def test_sugestao_reconhece_colunas_de_contato():
    sugestao = importacao.sugerir_mapeamento(["Pedido", "Cód Cliente", "Nome", "E-mail", "WhatsApp", "Data"])
    assert sugestao["cliente_nome"] == "Nome"
    assert sugestao["cliente_email"] == "E-mail"
    assert sugestao["cliente_telefone"] == "WhatsApp"


# --- personalização e lista ---------------------------------------------------

def test_personalizar_troca_marcadores_e_mantem_os_desconhecidos():
    texto = "Olá, {nome}! Até {validade}. Cupom {cupom}"
    assert campanhas.personalizar(texto, {"nome": "João", "validade": "domingo"}) == \
        "Olá, João! Até domingo. Cupom {cupom}"
    assert campanhas.marcadores_pendentes("Cupom {cupom}", "{ link }") == ["cupom", "link"]


def test_lista_de_disparo_personaliza_linha_a_linha():
    clientes = pd.DataFrame({"CustomerID": [1.0, 2.0, 3.0], "Recency": [10, 20, 30],
                             "Frequency": [1, 2, 3], "Monetary": [10.123, 20.0, 30.0]})
    contatos = pd.DataFrame({"cliente_id": ["1", "2"], "nome": ["João Silva", None],
                             "email": ["joao@x.com", "b@x.com"], "telefone": ["5511987654321", None]})
    lista = campanhas.montar_lista_disparo(clientes, contatos, PERSONA, "Clientes Inativos",
                                           {"validade": "domingo", "link": "https://loja.test"})
    assert list(lista.columns) == campanhas.COLUNAS_LISTA
    assert lista["cliente_id"].tolist() == ["1", "2", "3"]
    assert lista.loc[0, "mensagem_whatsapp"] == "Olá, João! Só até domingo: https://loja.test"
    assert lista.loc[1, "mensagem_push"] == "cliente, sua oferta acaba domingo!"  # sem nome → fallback
    assert lista.loc[0, "corpo_email_html"] == '<p>Olá, João!</p><p><a href="https://loja.test">Ver oferta</a></p>'
    assert lista.loc[2, "email"] is None and lista.loc[0, "valor_gasto"] == 10.12

    csv = campanhas.csv_para_disparo(lista)
    assert csv.startswith(b"\xef\xbb\xbf")
    relido = pd.read_csv(io.BytesIO(csv), encoding="utf-8-sig", dtype=str)
    assert relido.loc[0, "assunto_email"] == "João, voltamos com novidades"


def test_persona_antiga_usa_push_no_whatsapp():
    mensagens = campanhas.mensagens_da_persona({"copy_notificacao_push": "Volte!"})
    assert mensagens["mensagem_whatsapp"] == "Volte!" and mensagens["corpo_email_html"] == ""


# --- simulador ----------------------------------------------------------------

def test_simulador_de_retorno():
    sim = campanhas.simular_retorno(1622, 10, ticket=250.0, compras_por_cliente=1, desconto_pct=15)
    assert sim.clientes_recuperados == 162
    assert sim.receita_bruta == 40500.0 and sim.custo_desconto == 6075.0 and sim.receita_liquida == 34425.0
    assert campanhas.desconto_da_oferta("15% OFF de retorno") == 15.0
    assert campanhas.desconto_da_oferta("Frete grátis acima de R$ 199") == 0.0


def test_ticket_medio_por_pedido():
    df = pd.DataFrame({"Monetary": [100.0, 300.0], "Frequency": [1, 3]})
    assert campanhas.ticket_medio(df) == 100.0


# --- e-mail de teste ----------------------------------------------------------

class _HttpFalso:
    def __init__(self, status=200, corpo=None):
        self.status, self.corpo, self.chamadas = status, corpo or {"id": "email-123"}, []

    def post(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        return SimpleNamespace(status_code=self.status, json=lambda: self.corpo)


def test_envio_de_teste_chama_o_resend_com_html_limpo():
    http = _HttpFalso()
    id_envio = campanhas.enviar_email_teste("re_x", "Loja <onboarding@resend.dev>", "Ana@Loja.com",
                                            "Assunto", "<p>Oi</p><script>x()</script>", http_client=http)
    assert id_envio == "email-123"
    url, kwargs = http.chamadas[0]
    assert url == campanhas.URL_RESEND
    assert kwargs["headers"]["Authorization"] == "Bearer re_x"
    assert kwargs["json"] == {"from": "Loja <onboarding@resend.dev>", "to": ["ana@loja.com"],
                              "subject": "[Teste] Assunto", "html": "<p>Oi</p>"}


@pytest.mark.parametrize("status, trecho", [(403, "recusou o envio"), (429, "Limite"), (500, "500")])
def test_envio_de_teste_traduz_erros(status, trecho):
    with pytest.raises(campanhas.ErroEnvio, match=trecho):
        campanhas.enviar_email_teste("k", "r", "a@b.com", "s", "<p>x</p>",
                                     http_client=_HttpFalso(status, {"message": "x"}))


def test_envio_de_teste_recusa_destino_invalido():
    with pytest.raises(campanhas.ErroEnvio, match="inválido"):
        campanhas.enviar_email_teste("k", "r", "nao-e-email", "s", "<p>x</p>", http_client=_HttpFalso())


# --- dashboard ----------------------------------------------------------------

def _app_logado(banco):
    at = AppTest.from_file(HOME, default_timeout=120)
    at.session_state["_supabase_client"] = banco
    at.session_state["usuario"] = {"id": "u1", "email": "ana@moda.test", "nome": "Ana"}
    at.session_state["empresas"] = [EMPRESA]
    at.session_state["empresa_atual_id"] = EMPRESA["id"]
    return at


def _banco_pronto():
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas_com_contatos(), MAPA_CONTATOS,
                                          "v.csv", dia_primeiro=True)
    estrategias.gerar_e_salvar(banco, FakeLLM(), EMPRESA, resultado.execucao_id)
    for linha in banco.tabelas["estrategias_ia"]:
        linha["persona"] = dict(PERSONA)
    return banco


def test_dashboard_ativar_campanha_com_contatos(monkeypatch):
    monkeypatch.setattr("plataforma.config.config_resend", lambda: None)
    banco = _banco_pronto()
    at = _app_logado(banco).run()
    segmento = banco.tabelas["estrategias_ia"][0]["segmento"]
    at.sidebar.radio[0].set_value(segmento).run()
    assert not at.exception

    textos = " ".join(m.value for m in at.markdown)
    assert "Olá, João! Só até domingo: https://sualoja.com.br/oferta" in textos  # prévia com o nome real
    botao = next(b for b in at.get("download_button") if "disparo" in b.proto.label)
    assert botao.proto.label == "Baixar lista para disparo (.CSV)"
    assert any("com e-mail" in c.value for c in at.caption)
    assert any("Se 10% dos" in m.value for m in at.markdown)

    at.slider(key="roi_taxa").set_value(20).run()
    assert any("Se 20% dos" in m.value for m in at.markdown)


def test_dashboard_envia_teste_para_o_usuario_logado(monkeypatch):
    enviados = []
    monkeypatch.setattr("app.config_resend", lambda: ("re_x", "Loja <onboarding@resend.dev>"), raising=False)
    monkeypatch.setattr("plataforma.config.config_resend", lambda: ("re_x", "Loja <onboarding@resend.dev>"))
    monkeypatch.setattr(campanhas, "enviar_email_teste", lambda *a, **k: enviados.append(a) or "id")
    banco = _banco_pronto()
    at = _app_logado(banco).run()
    at.sidebar.radio[0].set_value(banco.tabelas["estrategias_ia"][0]["segmento"]).run()
    at.button(key="enviar_teste").click().run()
    assert not at.exception
    assert enviados and enviados[0][2] == "ana@moda.test"
    assert enviados[0][3].startswith("João")
    assert any("enviado para ana@moda.test" in s.value for s in at.success)


def test_demo_tem_lista_e_simulador_mas_nao_envia():
    at = AppTest.from_file(HOME, default_timeout=120).run()
    at.switch_page("app.py").run()
    at.sidebar.radio[0].set_value("Clientes Inativos").run()
    assert not at.exception
    assert any(b.proto.label == "Baixar lista para disparo (.CSV)" for b in at.get("download_button"))
    assert any("Disponível para empresas logadas" in c.value for c in at.caption)
    assert any("Se 10% dos Clientes Inativos" in m.value for m in at.markdown)
