import pytest

from plataforma import estrategias


def _llm_real_proibida():
    raise AssertionError("Teste tentou usar a LLM real")


@pytest.fixture(autouse=True)
def ia_desligada(monkeypatch):
    """Nenhum teste chama a API real da Groq, mesmo que a máquina tenha a chave configurada.
    Os testes que precisam de IA trocam por um FakeLLM."""
    monkeypatch.setattr(estrategias, "ia_disponivel", lambda: False)
    monkeypatch.setattr(estrategias, "cliente_llm", _llm_real_proibida)
