"""Cadastro e edição da empresa: nicho e tom de voz alimentam o prompt da IA."""

import streamlit as st

from plataforma import opcoes, repositorio, sessao


def formulario_empresa(chave: str, empresa: dict | None, bloqueado: bool = False) -> dict | None:
    """Desenha o formulário e devolve os campos preenchidos quando enviado e válido."""
    empresa = empresa or {}
    setor_atual = empresa.get("setor") or opcoes.NICHOS[0]
    nichos = opcoes.NICHOS + [opcoes.OUTRO]
    indice_nicho = nichos.index(setor_atual) if setor_atual in opcoes.NICHOS else len(nichos) - 1
    preset_atual, detalhes_atuais = opcoes.separar_tom_de_voz(empresa.get("tom_de_voz"))
    moedas = list(opcoes.MOEDAS)

    with st.form(chave):
        nome = st.text_input("Nome da empresa", value=empresa.get("nome", ""), disabled=bloqueado)
        nicho = st.selectbox("Nicho", nichos, index=indice_nicho, disabled=bloqueado)
        outro_nicho = st.text_input(
            "Se escolheu “Outro”, qual é o nicho?",
            value="" if setor_atual in opcoes.NICHOS else setor_atual,
            disabled=bloqueado,
        )
        preset = st.radio(
            "Tom de voz das mensagens",
            list(opcoes.TONS_DE_VOZ),
            index=list(opcoes.TONS_DE_VOZ).index(preset_atual),
            captions=list(opcoes.TONS_DE_VOZ.values()),
            disabled=bloqueado,
        )
        detalhes = st.text_area(
            "Detalhes do tom de voz (opcional)",
            value=detalhes_atuais,
            max_chars=300,
            placeholder="Ex.: chamamos o cliente pelo primeiro nome e nunca usamos caixa alta.",
            disabled=bloqueado,
        )
        moeda = st.selectbox(
            "Moeda dos dados de vendas",
            moedas,
            index=moedas.index(empresa.get("moeda", "BRL")) if empresa.get("moeda") in moedas else 0,
            format_func=lambda m: f"{m} ({opcoes.MOEDAS[m]})",
            disabled=bloqueado,
        )
        enviado = st.form_submit_button("Salvar", type="primary", disabled=bloqueado)

    if not enviado:
        return None
    setor = outro_nicho.strip() if nicho == opcoes.OUTRO else nicho
    if len(nome.strip()) < 2:
        st.error("Informe o nome da empresa.")
        return None
    if not setor:
        st.error("Informe o nicho da empresa.")
        return None
    return {
        "nome": nome.strip(),
        "setor": setor[:80],
        "tom_de_voz": opcoes.montar_tom_de_voz(preset, detalhes),
        "moeda": moeda,
    }


empresa = sessao.empresa_atual()

if empresa is None:
    st.title("🏢 Cadastre sua empresa")
    st.caption("Você ainda não faz parte de nenhuma empresa. Crie a sua — você será o administrador. "
               "Para entrar numa empresa existente, peça um convite ao administrador dela.")
    if dados := formulario_empresa("form_nova_empresa", None):
        novo_id = repositorio.criar_empresa(sessao.cliente(), **dados)
        sessao.recarregar_empresas()
        sessao.selecionar_empresa(novo_id)
        st.rerun()
    st.stop()

st.title(f"🏢 {empresa['nome']}")
st.caption(f"Plano **{empresa['plano']}** · seu papel: **{empresa['papel']}**")

if not sessao.eh_admin():
    st.info("Somente administradores podem alterar os dados da empresa.")

if dados := formulario_empresa("form_editar_empresa", empresa, bloqueado=not sessao.eh_admin()):
    repositorio.atualizar_empresa(sessao.cliente(), empresa["id"], dados)
    sessao.recarregar_empresas()
    st.toast("Dados da empresa atualizados.", icon="✅")
    st.rerun()

with st.expander("Criar outra empresa"):
    if dados := formulario_empresa("form_outra_empresa", None):
        novo_id = repositorio.criar_empresa(sessao.cliente(), **dados)
        sessao.recarregar_empresas()
        sessao.selecionar_empresa(novo_id)
        st.rerun()
