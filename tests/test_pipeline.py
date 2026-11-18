import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from customer_intel import calcular_rfm, executar_pipeline, limpar_transacoes, mapear_colunas, nomear_segmentos
from customer_intel.personas import ContextoEmpresa, construir_prompt, gerar_persona


def _transacoes(linhas):
    colunas = ["fatura_id", "cliente_id", "data_compra", "quantidade", "preco_unitario"]
    return pd.DataFrame(linhas, columns=colunas)


def test_mapear_colunas_exige_obrigatorias():
    df = pd.DataFrame({"Nota": ["1"], "Cliente": ["a"]})
    with pytest.raises(ValueError, match="obrigatórias"):
        mapear_colunas(df, {"Nota": "fatura_id", "Cliente": "cliente_id"})


def test_limpeza_remove_invalidos_e_mantem_devolucoes():
    df = _transacoes([
        ["1", "A", "2024-01-01", 2, 10.0],
        ["1", "A", "2024-01-01", 2, 10.0],   # duplicata exata
        ["2", None, "2024-01-02", 1, 5.0],   # sem cliente
        ["3", "B", "2024-01-03", 1, 0.0],    # preço zero
        ["C4", "A", "2024-01-04", -1, 10.0],  # devolução
        ["5", "B", "data ruim", 1, 5.0],     # data inválida
    ])
    limpo, rel = limpar_transacoes(df)
    assert rel.linhas_lidas == 6
    assert (rel.duplicadas, rel.sem_cliente, rel.preco_invalido, rel.data_invalida) == (1, 1, 1, 1)
    assert rel.linhas_validas == 2 and rel.devolucoes == 1


def test_ids_float_viram_texto_sem_sufixo():
    df = _transacoes([["536365", 17850.0, "2024-01-01", 1, 1.0]])
    limpo, _ = limpar_transacoes(df)
    assert limpo.loc[0, "cliente_id"] == "17850"


def test_rfm_usa_monetary_liquido_e_descarta_quem_devolveu_tudo():
    df = _transacoes([
        ["1", "A", "2024-01-01", 10, 10.0],   # A compra 100
        ["C1", "A", "2024-01-05", -3, 10.0],  # A devolve 30 → líquido 70
        ["2", "A", "2024-01-10", 1, 10.0],    # A compra 10 → líquido 80, 2 faturas
        ["3", "B", "2024-01-02", 5, 10.0],    # B compra 50
        ["C3", "B", "2024-01-03", -5, 10.0],  # B devolve tudo → descartado
    ])
    limpo, _ = limpar_transacoes(df)
    rfm = calcular_rfm(limpo, pd.Timestamp("2024-01-11")).set_index("cliente_id")
    assert list(rfm.index) == ["A"]
    assert rfm.loc["A", "monetary"] == 80
    assert rfm.loc["A", "frequency"] == 2  # devolução não conta como compra
    assert rfm.loc["A", "recency"] == 1


def test_nomeacao_independe_da_ordem_dos_clusters():
    # centróides padronizados (R, F, M) no estilo dos 4 clusters do Online Retail
    centroides = np.array([
        [-1.2, 1.5, 1.4],   # recente, frequente, alto valor
        [1.0, -0.9, -0.9],  # antigo, pouco frequente
        [-0.8, -0.3, -0.5],  # recente, pouco frequente
        [0.3, 0.4, 0.4],    # antigo, frequente
    ])
    esperado = ["Clientes VIP", "Clientes Inativos", "Clientes Promissores", "Clientes em Risco"]
    assert [nomear_segmentos(centroides)[i] for i in range(4)] == esperado

    permutacao = [2, 0, 3, 1]
    nomes = nomear_segmentos(centroides[permutacao])
    assert [nomes[i] for i in range(4)] == [esperado[p] for p in permutacao]


def test_nomes_repetidos_recebem_sufixo():
    centroides = np.array([[1.0, -1.0, -1.0], [0.5, -0.5, -0.2], [-1.0, 1.0, 1.0]])
    nomes = nomear_segmentos(centroides)
    assert sorted(nomes.values()) == ["Clientes Inativos 1", "Clientes Inativos 2", "Clientes VIP"]
    assert nomes[1] == "Clientes Inativos 1"  # melhor pontuação recebe o 1


def test_pipeline_ponta_a_ponta_sintetico():
    rng = np.random.default_rng(0)
    linhas = []
    for c in range(200):
        for f in range(int(rng.integers(1, 12))):
            dia = pd.Timestamp("2024-01-01") + pd.Timedelta(days=int(rng.integers(0, 365)))
            linhas.append([f"{c}-{f}", f"cli{c}", dia, int(rng.integers(1, 20)), float(rng.uniform(1, 50))])
    resultado = executar_pipeline(_transacoes(linhas), k=4)
    seg = resultado.segmentacao
    assert len(seg.clientes) == 200
    assert seg.clientes["segmento"].notna().all()
    assert seg.resumo["quantidade_clientes"].sum() == 200
    assert -1 <= seg.silhouette <= 1


def test_prompt_trunca_tom_de_voz_e_gerar_persona_valida_json():
    empresa = ContextoEmpresa(nome="Loja X", tom_de_voz="a" * 2000, moeda="BRL")
    prompt = construir_prompt({"segmento": "Clientes VIP"}, empresa)
    assert "a" * 501 not in prompt and "BRL" in prompt

    persona = {"persona_nome": "N", "descricao_persona": "D", "estrategia_retencao": "E",
               "copy_notificacao_push": "P", "oferta_sugerida": "O", "oferta_justificativa": "J",
               "email_assunto": "A", "email_corpo_html": "<p>C</p>", "mensagem_whatsapp": "W"}
    resposta = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(persona)))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: resposta)))
    gerada = gerar_persona(client, {"segmento": "Clientes VIP"}, empresa)
    assert gerada.persona == persona and gerada.tokens_entrada == 10


def test_gerar_persona_falha_com_json_incompleto():
    resposta = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"persona_nome": "N"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: resposta)))
    with pytest.raises(ValueError, match="sem as chaves"):
        gerar_persona(client, {"segmento": "X"}, ContextoEmpresa(nome="L"), max_tentativas=2, espera_s=0)


def test_limpeza_aceita_formato_brasileiro():
    from customer_intel.limpeza import detectar_dia_primeiro

    df = _transacoes([
        ["1", "A", "03/04/2024 10:00", "2", "1.234,56"],
        ["2", "B", "25/12/2024 08:30", "1", "10,5"],
    ])
    assert detectar_dia_primeiro(df["data_compra"]) is True
    limpo, rel = limpar_transacoes(df, dia_primeiro=True)
    assert rel.linhas_validas == 2
    assert limpo.loc[0, "data_compra"] == pd.Timestamp("2024-04-03 10:00")
    assert limpo.loc[0, "preco_unitario"] == 1234.56 and limpo.loc[1, "preco_unitario"] == 10.5


def test_dia_primeiro_nao_estraga_datas_iso():
    df = _transacoes([["1", "A", "2010-12-01 08:26:00", 1, 1.0], ["2", "B", "2011-01-13", 1, 1.0]])
    limpo, rel = limpar_transacoes(df, dia_primeiro=True)
    assert rel.data_invalida == 0
    assert limpo.loc[0, "data_compra"] == pd.Timestamp("2010-12-01 08:26:00")


def test_conversores_recusam_colunas_trocadas():
    from customer_intel.limpeza import converter_datas, converter_numeros

    assert converter_numeros(pd.Series(["03/04/2024", "2024-04-03"])).isna().all()
    assert converter_numeros(pd.Series(["R$ 1.234,56", "10,5", "-3"])).tolist() == [1234.56, 10.5, -3.0]
    assert converter_numeros(pd.Series(["£1,234.56", "10.5"])).tolist() == [1234.56, 10.5]
    assert converter_datas(pd.Series(["123,45", "7", "10.5"])).isna().all()
