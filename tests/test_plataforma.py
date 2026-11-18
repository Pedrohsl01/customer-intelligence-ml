import pytest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from plataforma import opcoes, repositorio
from tests.fake_supabase import FakeSupabase

HOME = str(Path(__file__).resolve().parent.parent / "home.py")
EMPRESA_A, EMPRESA_B = "empresa-a", "empresa-b"
EXEC_A, EXEC_B = "exec-a", "exec-b"


def _banco():
    clientes = [
        {"empresa_id": EMPRESA_A, "execucao_id": EXEC_A, "cliente_id": f"A{i:04d}", "recency": i % 300,
         "frequency": 1 + i % 9, "monetary": 100.0 + i, "cluster": i % 2,
         "segmento": "Clientes VIP" if i % 2 else "Clientes Inativos"}
        for i in range(2500)
    ] + [
        {"empresa_id": EMPRESA_B, "execucao_id": EXEC_B, "cliente_id": "B1", "recency": 1, "frequency": 1,
         "monetary": 9.0, "cluster": 0, "segmento": "Clientes VIP"}
    ]
    return FakeSupabase({
        "empresas": [{"id": EMPRESA_A, "nome": "Loja A", "plano": "free"}],
        "execucoes_segmentacao": [
            {"id": EXEC_A, "empresa_id": EMPRESA_A, "status": "concluida", "criado_em": "2026-11-01"},
            {"id": EXEC_B, "empresa_id": EMPRESA_B, "status": "concluida", "criado_em": "2026-11-02"},
        ],
        "clientes_segmentados": clientes,
        "resumo_segmentos": [
            {"empresa_id": EMPRESA_A, "execucao_id": EXEC_A, "segmento": "Clientes VIP",
             "quantidade_clientes": 1250, "monetary_medio": 1350.0},
            {"empresa_id": EMPRESA_A, "execucao_id": EXEC_A, "segmento": "Clientes Inativos",
             "quantidade_clientes": 1250, "monetary_medio": 1349.0},
        ],
        "estrategias_ia": [
            {"empresa_id": EMPRESA_A, "execucao_id": EXEC_A, "segmento": "Clientes VIP",
             "persona": {"persona_nome": "Fã da Loja A", "descricao_persona": "d",
                         "estrategia_retencao": "e", "copy_notificacao_push": "p"}},
        ],
    })


# --- repositório --------------------------------------------------------------

def test_toda_consulta_de_dados_filtra_por_empresa():
    banco = _banco()
    execucao = repositorio.ultima_execucao(banco, EMPRESA_A)
    repositorio.clientes_segmentados(banco, EMPRESA_A, execucao["id"])
    repositorio.resumo_segmentos(banco, EMPRESA_A, execucao["id"])
    repositorio.estrategias(banco, EMPRESA_A, execucao["id"])
    assert banco.consultas
    for consulta in banco.consultas:
        assert ("empresa_id", EMPRESA_A) in consulta.filtros, consulta.tabela


def test_ultima_execucao_nao_vaza_execucao_de_outra_empresa():
    assert repositorio.ultima_execucao(_banco(), EMPRESA_A)["id"] == EXEC_A


def test_consulta_sem_empresa_e_recusada():
    with pytest.raises(ValueError, match="empresa_id"):
        repositorio.clientes_segmentados(_banco(), "", EXEC_A)


def test_clientes_segmentados_le_todas_as_paginas():
    df = repositorio.clientes_segmentados(_banco(), EMPRESA_A, EXEC_A)
    assert len(df) == 2500 and df["cliente_id"].is_unique
    assert not df["cliente_id"].str.startswith("B").any()


def test_atualizar_empresa_nao_permite_alterar_plano():
    with pytest.raises(ValueError, match="plano"):
        repositorio.atualizar_empresa(_banco(), EMPRESA_A, {"plano": "enterprise"})


def test_criar_empresa_usa_rpc():
    banco = _banco()
    novo_id = repositorio.criar_empresa(banco, "Loja C", "Pet Shop", "Formal", "BRL")
    assert novo_id and banco.chamadas_rpc[0][0] == "criar_empresa"


# --- opções -------------------------------------------------------------------

@pytest.mark.parametrize("preset, detalhes", [("Formal", ""), ("Urgente", "Sempre cite o prazo. Sem emojis.")])
def test_tom_de_voz_ida_e_volta(preset, detalhes):
    assert opcoes.separar_tom_de_voz(opcoes.montar_tom_de_voz(preset, detalhes)) == (preset, detalhes)


def test_tom_de_voz_respeita_limite_do_banco():
    assert len(opcoes.montar_tom_de_voz("Formal", "x" * 1000)) == opcoes.LIMITE_TOM_DE_VOZ


# --- app (Streamlit AppTest) --------------------------------------------------

def _app_logado(banco, empresas):
    at = AppTest.from_file(HOME, default_timeout=60)
    at.session_state["_supabase_client"] = banco
    at.session_state["usuario"] = {"id": "u1", "email": "ana@loja-a.test", "nome": "Ana"}
    at.session_state["empresas"] = empresas
    at.session_state["empresa_atual_id"] = empresas[0]["id"] if empresas else None
    return at


def test_visitante_ve_landing_page():
    at = AppTest.from_file(HOME, default_timeout=60).run()
    assert not at.exception
    assert at.button[0].label == "Ver demonstração"


def test_usuario_logado_ve_apenas_dados_da_propria_empresa():
    banco = _banco()
    empresa = {"id": EMPRESA_A, "nome": "Loja A", "setor": "Pet Shop", "tom_de_voz": "Formal",
               "moeda": "BRL", "plano": "free", "papel": "admin"}
    at = _app_logado(banco, [empresa]).run()
    assert not at.exception, at.exception
    assert at.metric[0].value == "2,500"
    assert at.metric[3].value.startswith("R$")
    tabela = at.dataframe[0].value
    assert len(tabela) == 2500 and not tabela["CustomerID"].str.startswith("B").any()

    at.sidebar.radio[0].set_value("Clientes VIP").run()
    assert any("Fã da Loja A" in m.value for m in at.markdown)


def test_empresa_sem_segmentacao_mostra_aviso():
    empresa = {"id": "empresa-nova", "nome": "Loja Nova", "moeda": "BRL", "plano": "free", "papel": "admin"}
    at = _app_logado(_banco(), [empresa]).run()
    assert not at.exception
    assert any("ainda não tem nenhuma segmentação" in i.value for i in at.info)


def test_usuario_sem_empresa_cai_no_cadastro_e_cria_empresa():
    banco = _banco()
    at = _app_logado(banco, []).run()
    assert not at.exception
    assert at.title[0].value == "🏢 Cadastre sua empresa"

    at.text_input[0].input("Moda da Ana")
    at.selectbox[0].set_value("Moda Feminina")
    at.radio[0].set_value("Jovem/Descontraído")
    at.text_area[0].input("Chame a cliente de 'amiga'.")
    at.button[0].click().run()

    funcao, parametros = banco.chamadas_rpc[0]
    assert funcao == "criar_empresa"
    assert parametros == {"p_nome": "Moda da Ana", "p_setor": "Moda Feminina",
                          "p_tom_de_voz": "Jovem/Descontraído. Chame a cliente de 'amiga'.", "p_moeda": "BRL"}


def test_leitor_nao_edita_empresa():
    empresa = {"id": EMPRESA_A, "nome": "Loja A", "setor": "Pet Shop", "tom_de_voz": "Formal",
               "moeda": "BRL", "plano": "free", "papel": "leitor"}
    at = _app_logado(_banco(), [empresa])
    at.switch_page("paginas/empresa.py").run()
    assert not at.exception
    assert at.text_input[0].disabled
    assert any("Somente administradores" in i.value for i in at.info)


def test_sessao_expirada_volta_para_login():
    banco = _banco()
    banco.auth.sessao = None
    empresa = {"id": EMPRESA_A, "nome": "Loja A", "moeda": "BRL", "plano": "free", "papel": "admin"}
    at = _app_logado(banco, [empresa]).run()
    assert not at.exception
    assert "usuario" not in at.session_state
