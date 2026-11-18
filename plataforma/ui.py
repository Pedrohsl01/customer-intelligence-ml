"""Componentes visuais reutilizados pelas páginas (somente apresentação).

Todo texto dinâmico — inclusive o que vem da LLM ou do cadastro da empresa —
passa por `html.escape` antes de entrar em HTML.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Cores da interface (as mesmas de assets/theme.css)
TEXTO = "#E8ECF4"
TEXTO_SUAVE = "#9AA6BD"
LINHA = "rgba(148, 163, 184, 0.16)"
AMBAR = "#F2B544"
FONTE = '"Schibsted Grotesk", "Segoe UI", system-ui, sans-serif'

# Mapa FIXO de cores dos segmentos (usado nos gráficos Plotly, no cartão de persona e na landing).
CORES_SEGMENTOS = {
    "Clientes VIP": "#00CC96",          # Verde destaque
    "Clientes Promissores": "#636EFA",  # Azul
    "Clientes Regulares": "#AB63FA",    # Roxo
    "Clientes Fiéis": "#AB63FA",        # Roxo (nome gerado pelo pipeline novo)
    "Clientes em Risco": "#FFA15A",     # Laranja
    "Clientes Inativos": "#EF553B",     # Vermelho/Laranja alerta
}

LIMITE_PUSH = 140

MARCA_SVG = (
    '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">'
    '<rect width="28" height="28" rx="7" fill="#F2B544"/>'
    '<rect x="6" y="7" width="16" height="3" rx="1.5" fill="#1A1304"/>'
    '<rect x="6" y="12.5" width="11" height="3" rx="1.5" fill="#1A1304"/>'
    '<rect x="6" y="18" width="6" height="3" rx="1.5" fill="#1A1304"/>'
    "</svg>"
)


def carregar_css(nome: str) -> None:
    """Injeta assets/<nome> na página atual."""
    caminho = ASSETS / nome
    if caminho.is_file():
        st.markdown(f"<style>{caminho.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"Arquivo de estilo não encontrado: {caminho}")


def _html(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


def marca(nome: str, modo: str | None = None) -> str:
    """Logo + nome (da plataforma ou da empresa logada) para o topo e a sidebar."""
    linha_modo = f'<span class="marca__modo">{escape(modo)}</span>' if modo else ""
    return f'<div class="marca">{MARCA_SVG}<div class="marca__nome">{escape(nome)}{linha_modo}</div></div>'


def cabecalho(titulo: str, descricao: str = "") -> None:
    paragrafo = f"<p>{escape(descricao)}</p>" if descricao else ""
    _html(f'<div class="cabecalho"><h1>{escape(titulo)}</h1>{paragrafo}</div>')


def secao(titulo: str, descricao: str = "") -> None:
    paragrafo = f"<p>{escape(descricao)}</p>" if descricao else ""
    _html(f'<div class="secao"><h2>{escape(titulo)}</h2>{paragrafo}</div>')


def cartao_persona(segmento: str, cor: str, persona: dict, produtos: list[dict] | None = None) -> None:
    """Persona do segmento: diagnóstico comportamental, ação recomendada e, se houver, oferta e produtos."""
    blocos = [
        '<div class="persona__bloco"><h4>Diagnóstico comportamental</h4>'
        f"<p>{escape(persona.get('descricao_persona', 'N/A'))}</p></div>",
        '<div class="persona__bloco persona__bloco--acao"><h4>Ação recomendada</h4>'
        f"<p>{escape(persona.get('estrategia_retencao', 'N/A'))}</p></div>",
    ]
    if persona.get("oferta_sugerida"):
        justificativa = persona.get("oferta_justificativa", "")
        blocos.append(
            '<div class="persona__bloco"><h4>Oferta sugerida</h4>'
            f'<p class="persona__oferta">{escape(persona["oferta_sugerida"])}</p>'
            + (f"<p>{escape(justificativa)}</p>" if justificativa else "")
            + "</div>"
        )
    if produtos:
        itens = "".join(f"<li>{escape(str(p['produto']))}</li>" for p in produtos)
        blocos.append(
            '<div class="persona__bloco"><h4>Produtos mais comprados pelo segmento</h4>'
            f'<ul class="persona__produtos">{itens}</ul></div>'
        )
    _html(
        f'<section class="persona" style="--cor-segmento: {escape(cor)}">'
        f'<span class="persona__segmento"><i></i>{escape(segmento)}</span>'
        f'<h3 class="persona__nome">{escape(persona.get("persona_nome", "N/A"))}</h3>'
        + "".join(blocos)
        + "</section>"
    )


def previa_push(mensagem: str, remetente: str, titulo: str = "Prévia da mensagem push") -> None:
    """Notificação como aparece na tela de bloqueio, com quebra de linha e contagem de caracteres."""
    mensagem = (mensagem or "N/A").strip()
    tamanho = len(mensagem)
    excedeu = " push__contagem--excedeu" if tamanho > LIMITE_PUSH else ""
    aviso = " (acima do recomendado: pode ser cortada no celular)" if tamanho > LIMITE_PUSH else ""
    _html(
        '<div class="push">'
        f'<p class="push__titulo">{escape(titulo)}</p>'
        '<div class="push__tela"><p class="push__hora">9:41</p>'
        '<div class="push__notificacao">'
        f'<div class="push__app"><span class="push__icone"></span><b>{escape(remetente)}</b><span>agora</span></div>'
        f'<p class="push__mensagem">{escape(mensagem)}</p>'
        "</div></div>"
        f'<p class="push__contagem{excedeu}">{tamanho} de {LIMITE_PUSH} caracteres{aviso}</p>'
        "</div>"
    )


def previa_whatsapp(mensagem: str, remetente: str = "Sua loja") -> None:
    """Conversa do WhatsApp como o cliente vê: cabeçalho com a empresa e o balão recebido."""
    inicial = escape((remetente or "?").strip()[:1].upper())
    _html(
        '<div class="whats">'
        f'<div class="whats__topo"><span class="whats__avatar">{inicial}</span>'
        f'<span><b>{escape(remetente)}</b><small>conta comercial</small></span></div>'
        '<div class="whats__conversa">'
        f'<p class="whats__balao">{escape((mensagem or "").strip())}<span class="whats__hora">9:41</span></p>'
        "</div></div>"
    )


def roi(frase: str) -> None:
    _html(f'<p class="roi__frase">{escape(frase)}</p>')


def assunto_email(assunto: str) -> None:
    _html(f'<p class="email__assunto"><span>Assunto</span>{escape(assunto or "")}</p>')


def rodape(texto: str) -> None:
    _html(f'<div class="rodape">{escape(texto)}</div>')


def estilizar_grafico(fig, altura: int = 380):
    """Integra um gráfico Plotly ao cartão: fundo transparente, tipografia e grades discretas.
    Não altera dados nem as cores dos segmentos."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, color=TEXTO_SUAVE, size=13),
        title=dict(font=dict(family=FONTE, color=TEXTO, size=16), x=0, xanchor="left", pad=dict(l=4)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    title_text="", bgcolor="rgba(0,0,0,0)", font=dict(color=TEXTO)),
        margin=dict(l=8, r=8, t=72, b=8),
        height=altura,
        hoverlabel=dict(bgcolor="#1B2236", bordercolor=LINHA, font=dict(family=FONTE, color=TEXTO)),
    )
    fig.update_xaxes(gridcolor=LINHA, zerolinecolor=LINHA, linecolor=LINHA,
                     tickfont=dict(color=TEXTO_SUAVE), title_font=dict(color=TEXTO_SUAVE))
    fig.update_yaxes(gridcolor=LINHA, zerolinecolor=LINHA, linecolor=LINHA,
                     tickfont=dict(color=TEXTO_SUAVE), title_font=dict(color=TEXTO_SUAVE))
    return fig
