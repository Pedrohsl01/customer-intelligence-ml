"""Fase 4: produtos por segmento no prompt e pacote de campanha multicanal."""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from customer_intel.personas import (CHAVES_OBRIGATORIAS, ContextoEmpresa, construir_prompt, sanitizar_html,
                                     validar_persona)
from customer_intel.produtos import produtos_por_segmento
from plataforma import estrategias, importacao
from tests.fake_llm import FakeLLM
from tests.fake_supabase import FakeSupabase
from tests.test_importacao import MAPA, _vendas

HOME = str(Path(__file__).resolve().parent.parent / "home.py")
EMPRESA = {"id": "empresa-a", "nome": "Pet da Bia", "setor": "Pet Shop", "tom_de_voz": "Urgente",
           "moeda": "BRL", "plano": "free", "papel": "admin"}
MAPA_COM_PRODUTO = {**MAPA, "Produto": "produto_descricao"}


def _vendas_com_produto():
    df = _vendas()
    catalogo = ["Ração Premium 10kg", "Areia Higiênica", "Coleira Antipulgas", "Brinquedo Mordedor"]
    df["Produto"] = [catalogo[i % len(catalogo)] for i in range(len(df))]
    return df


def _persona_completa(**extra):
    base = {c: "texto" for c in CHAVES_OBRIGATORIAS}
    base["email_corpo_html"] = "<p>Olá</p>"
    return {**base, **extra}


# --- produtos por segmento ----------------------------------------------------

def test_produtos_por_segmento_ordena_por_unidades_e_ignora_devolucoes():
    transacoes = pd.DataFrame({
        "cliente_id": ["a", "a", "b", "b", "c"],
        "produto_descricao": ["Ração", "Coleira", "Ração", "Ração", "Areia"],
        "quantidade": [5, 1, 3, -2, 9],
        "preco_unitario": [10.0, 30.0, 10.0, 10.0, 4.0],
    })
    clientes = pd.DataFrame({"cliente_id": ["a", "b", "c"], "segmento": ["VIP", "VIP", "Inativos"]})
    resultado = produtos_por_segmento(transacoes, clientes)
    assert [p["produto"] for p in resultado["VIP"]] == ["Ração", "Coleira"]
    assert resultado["VIP"][0] == {"produto": "Ração", "quantidade": 8.0, "receita": 80.0, "clientes": 2}
    assert resultado["Inativos"][0]["produto"] == "Areia"


def test_produtos_por_segmento_sem_coluna_de_produto():
    transacoes = pd.DataFrame({"cliente_id": ["a"], "quantidade": [1], "preco_unitario": [1.0]})
    assert produtos_por_segmento(transacoes, pd.DataFrame({"cliente_id": ["a"], "segmento": ["X"]})) == {}


def test_importacao_grava_produtos_por_segmento_na_execucao():
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas_com_produto(), MAPA_COM_PRODUTO,
                                          "v.csv", dia_primeiro=True)
    produtos = banco.tabelas["execucoes_segmentacao"][0]["produtos_por_segmento"]
    assert set(produtos) == set(resultado.segmentacao.clientes["segmento"])
    assert all(1 <= len(lista) <= 5 for lista in produtos.values())


# --- prompt -------------------------------------------------------------------

def test_prompt_inclui_produtos_do_segmento_e_contexto_da_empresa():
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas_com_produto(), MAPA_COM_PRODUTO,
                                          "v.csv", dia_primeiro=True)
    llm = FakeLLM()
    estrategias.gerar_e_salvar(banco, llm, EMPRESA, resultado.execucao_id)
    for prompt in llm.prompts:
        assert "Pet da Bia" in prompt and "Pet Shop" in prompt and "Urgente" in prompt
        assert "produtos_mais_comprados" in prompt and "Ração Premium 10kg" in prompt
        assert "email_corpo_html" in prompt and "mensagem_whatsapp" in prompt and "oferta_sugerida" in prompt


def test_prompt_sem_produtos_pede_para_nao_inventar():
    prompt = construir_prompt({"segmento": "Clientes VIP"}, ContextoEmpresa(nome="Loja"))
    assert "sem inventar nomes de produtos" in prompt
    assert "{validade}" in prompt and "{link}" in prompt  # marcadores chegam literais à LLM


# --- validação da resposta ----------------------------------------------------

def test_sanitizador_remove_scripts_eventos_e_links_perigosos():
    sujo = ('<p onclick="x()">Oi <strong>amiga</strong></p><script>alert(1)</script>'
            '<a href="javascript:alert(1)">a</a><a href="https://loja.test/x?a=1&b=2">b</a>'
            '<img src=x onerror=alert(1)><style>p{}</style>5 < 6')
    limpo = sanitizar_html(sujo)
    assert limpo == ('<p>Oi <strong>amiga</strong></p><a>a</a>'
                     '<a href="https://loja.test/x?a=1&amp;b=2">b</a>5 &lt; 6')


def test_validacao_exige_o_pacote_completo():
    incompleta = _persona_completa()
    del incompleta["mensagem_whatsapp"]
    with pytest.raises(ValueError, match="mensagem_whatsapp"):
        validar_persona(incompleta)
    with pytest.raises(ValueError, match="email_corpo_html"):
        validar_persona(_persona_completa(email_corpo_html="<script>x</script>"))


def test_validacao_limita_o_tamanho_do_push():
    persona = validar_persona(_persona_completa(copy_notificacao_push="x" * 500))
    assert len(persona["copy_notificacao_push"]) == 140


def test_persona_gravada_tem_html_limpo():
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas(), MAPA, "v.csv", dia_primeiro=True)
    estrategias.gerar_e_salvar(banco, FakeLLM(), EMPRESA, resultado.execucao_id)
    for linha in banco.tabelas["estrategias_ia"]:
        assert set(CHAVES_OBRIGATORIAS) <= set(linha["persona"])
        assert "<script" not in linha["persona"]["email_corpo_html"]


# --- dashboard ----------------------------------------------------------------

def test_dashboard_mostra_campanha_multicanal_e_produtos(monkeypatch):
    monkeypatch.setattr(estrategias, "ia_disponivel", lambda: True)
    monkeypatch.setattr(estrategias, "cliente_llm", lambda: FakeLLM())
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas_com_produto(), MAPA_COM_PRODUTO,
                                          "v.csv", dia_primeiro=True)
    estrategias.gerar_e_salvar(banco, FakeLLM(), EMPRESA, resultado.execucao_id)

    at = AppTest.from_file(HOME, default_timeout=120)
    at.session_state["_supabase_client"] = banco
    at.session_state["usuario"] = {"id": "u1", "email": "bia@pet.test", "nome": "Bia"}
    at.session_state["empresas"] = [EMPRESA]
    at.session_state["empresa_atual_id"] = EMPRESA["id"]
    at.run()
    gravada = banco.tabelas["estrategias_ia"][0]
    at.sidebar.radio[0].set_value(gravada["segmento"]).run()
    assert not at.exception

    textos = " ".join(m.value for m in at.markdown)
    assert gravada["persona"]["oferta_sugerida"] in textos
    assert gravada["persona"]["email_assunto"] in textos
    assert "Produtos mais comprados pelo segmento" in textos
    assert [t.label for t in at.tabs] == ["Push", "WhatsApp", "E-mail"]
    assert gravada["persona"]["mensagem_whatsapp"].replace("{validade}", "domingo") in textos


def test_demo_continua_funcionando_com_personas_antigas():
    at = AppTest.from_file(HOME, default_timeout=120).run()
    at.switch_page("app.py").run()
    at.sidebar.radio[0].set_value("Clientes VIP").run()
    assert not at.exception
    # personas do portfólio só têm a copy de push: a aba de e-mail explica como gerar o pacote completo
    assert [t.label for t in at.tabs] == ["Push", "WhatsApp", "E-mail"]
    assert any("Esta persona não tem e-mail" in c.value for c in at.caption)
