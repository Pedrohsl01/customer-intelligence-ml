from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from plataforma import estrategias, importacao
from tests.fake_llm import FakeLLM
from tests.fake_supabase import FakeSupabase
from tests.test_importacao import MAPA, _vendas

HOME = str(Path(__file__).resolve().parent.parent / "home.py")
EMPRESA = {"id": "empresa-a", "nome": "Moda da Ana", "setor": "Moda Feminina",
           "tom_de_voz": "Jovem/Descontraído. Chame a cliente de amiga.",
           "moeda": "BRL", "plano": "free", "papel": "analista"}


def _banco_segmentado():
    banco = FakeSupabase()
    resultado = importacao.processar_base(banco, EMPRESA["id"], _vendas(), MAPA, "v.csv", dia_primeiro=True)
    return banco, resultado


def test_gera_uma_persona_por_segmento_e_grava_para_a_empresa():
    banco, resultado = _banco_segmentado()
    geradas = estrategias.gerar_e_salvar(banco, FakeLLM(), EMPRESA, resultado.execucao_id)

    gravadas = banco.tabelas["estrategias_ia"]
    assert len(geradas) == len(gravadas) == 4
    assert {g["segmento"] for g in gravadas} == set(resultado.segmentacao.clientes["segmento"])
    assert all(g["empresa_id"] == EMPRESA["id"] and g["execucao_id"] == resultado.execucao_id for g in gravadas)
    assert all(g["tokens_entrada"] == 300 and g["modelo"] and g["versao_prompt"] for g in gravadas)


def test_prompt_leva_nicho_tom_de_voz_e_so_dados_agregados():
    banco, resultado = _banco_segmentado()
    llm = FakeLLM()
    estrategias.gerar_e_salvar(banco, llm, EMPRESA, resultado.execucao_id)

    prompt = llm.prompts[0]
    assert "Moda da Ana" in prompt and "Moda Feminina" in prompt and "BRL" in prompt
    assert "Jovem/Descontraído" in prompt and "Chame a cliente de amiga." in prompt
    assert "ticket_medio_por_compra" in prompt and "participacao_na_receita_pct" in prompt
    # nenhum identificador individual de cliente vai para a LLM
    import re

    assert resultado.segmentacao.clientes["cliente_id"].str.fullmatch(r"cli\d+").all()
    assert not any(re.search(r"cli\d", p) for p in llm.prompts)


def test_gerar_de_novo_substitui_em_vez_de_duplicar():
    banco, resultado = _banco_segmentado()
    llm = FakeLLM()
    estrategias.gerar_e_salvar(banco, llm, EMPRESA, resultado.execucao_id)
    estrategias.gerar_e_salvar(banco, llm, EMPRESA, resultado.execucao_id)
    gravadas = banco.tabelas["estrategias_ia"]
    assert len(gravadas) == 4
    assert {g["persona"]["persona_nome"] for g in gravadas} == {f"Persona {n}" for n in range(5, 9)}


def test_falha_da_llm_nao_grava_personas_pela_metade():
    banco, resultado = _banco_segmentado()
    with pytest.raises(estrategias.ErroEstrategias, match="não conseguiu gerar"):
        estrategias.gerar_e_salvar(banco, FakeLLM(falhar=True), EMPRESA, resultado.execucao_id)
    assert "estrategias_ia" not in banco.tabelas


def test_leituras_para_gerar_personas_filtram_por_empresa():
    banco, resultado = _banco_segmentado()
    banco.consultas.clear()
    estrategias.gerar_e_salvar(banco, FakeLLM(), EMPRESA, resultado.execucao_id)
    leituras = [c for c in banco.consultas if c.operacao == "select"]
    assert leituras and all(("empresa_id", EMPRESA["id"]) in c.filtros for c in leituras)


# --- telas --------------------------------------------------------------------

def _app(banco, papel="analista"):
    at = AppTest.from_file(HOME, default_timeout=120)
    at.session_state["_supabase_client"] = banco
    at.session_state["usuario"] = {"id": "u1", "email": "ana@moda.test", "nome": "Ana"}
    at.session_state["empresas"] = [{**EMPRESA, "papel": papel}]
    at.session_state["empresa_atual_id"] = EMPRESA["id"]
    return at


def _ligar_ia(monkeypatch, llm):
    monkeypatch.setattr(estrategias, "ia_disponivel", lambda: True)
    monkeypatch.setattr(estrategias, "cliente_llm", lambda: llm)


def _importar_pela_tela(at):
    at.switch_page("paginas/importar.py").run()
    at.file_uploader[0].set_value(("vendas.csv", _vendas().to_csv(index=False).encode(), "text/csv")).run()
    next(b for b in at.button if "Processar Base" in b.label).click().run()


def test_importacao_gera_personas_automaticamente(monkeypatch):
    _ligar_ia(monkeypatch, FakeLLM())
    banco = FakeSupabase()
    at = _app(banco)
    _importar_pela_tela(at)
    assert not at.exception
    assert len(banco.tabelas["estrategias_ia"]) == 4
    assert not at.warning

    at.switch_page("app.py").run()
    gravada = banco.tabelas["estrategias_ia"][0]
    at.sidebar.radio[0].set_value(gravada["segmento"]).run()
    assert not at.exception
    assert any(gravada["persona"]["persona_nome"] in m.value for m in at.markdown)


def test_importacao_sobrevive_a_falha_da_ia(monkeypatch):
    _ligar_ia(monkeypatch, FakeLLM(falhar=True))
    banco = FakeSupabase()
    at = _app(banco)
    _importar_pela_tela(at)
    assert not at.exception
    assert banco.tabelas["execucoes_segmentacao"][0]["status"] == "concluida"
    assert any("personas não" in w.value for w in at.warning)


def test_dashboard_gera_personas_pelo_botao(monkeypatch):
    banco, _ = _banco_segmentado()
    _ligar_ia(monkeypatch, FakeLLM())
    at = _app(banco).run()
    assert not at.exception
    assert any("ainda não tem personas" in i.value for i in at.info)

    next(b for b in at.button if "Gerar personas e campanhas com IA" in b.label).click().run()
    assert not at.exception
    assert len(banco.tabelas["estrategias_ia"]) == 4
    assert any("Gerar campanhas novamente" in b.label for b in at.button)


def test_leitor_nao_ve_botao_de_gerar(monkeypatch):
    banco, _ = _banco_segmentado()
    _ligar_ia(monkeypatch, FakeLLM())
    at = _app(banco, papel="leitor").run()
    assert not at.exception
    assert not any("Gerar" in b.label for b in at.button)
