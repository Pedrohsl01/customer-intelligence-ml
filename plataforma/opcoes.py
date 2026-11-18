"""Opções de cadastro da empresa usadas nos formulários e no prompt da IA."""

from __future__ import annotations

NICHOS = [
    "Moda Feminina",
    "Moda Masculina",
    "Eletrônicos",
    "Supermercado",
    "Casa e Decoração",
    "Beleza e Cosméticos",
    "Esportes e Lazer",
    "Pet Shop",
    "Livros e Papelaria",
    "Presentes e Artesanato",
]
OUTRO = "Outro"

TONS_DE_VOZ = {
    "Formal": "Linguagem profissional e respeitosa, sem gírias nem emojis.",
    "Jovem/Descontraído": "Linguagem leve e próxima, pode usar emojis e expressões informais.",
    "Urgente": "Mensagens diretas que destacam prazo e escassez, com chamada clara para ação.",
}

MOEDAS = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}

LIMITE_TOM_DE_VOZ = 500  # mesmo limite da coluna empresas.tom_de_voz


def montar_tom_de_voz(preset: str, detalhes: str = "") -> str:
    """Texto salvo em empresas.tom_de_voz: '<preset>. <detalhes>'."""
    detalhes = detalhes.strip()
    texto = f"{preset}. {detalhes}" if detalhes else preset
    return texto[:LIMITE_TOM_DE_VOZ]


def separar_tom_de_voz(texto: str | None) -> tuple[str, str]:
    """Inverso de `montar_tom_de_voz`, para preencher o formulário de edição."""
    texto = (texto or "").strip()
    for preset in TONS_DE_VOZ:
        if texto == preset:
            return preset, ""
        if texto.startswith(f"{preset}. "):
            return preset, texto[len(preset) + 2:]
    return next(iter(TONS_DE_VOZ)), texto


def simbolo_moeda(codigo: str | None) -> str:
    return MOEDAS.get((codigo or "").upper(), codigo or "")
