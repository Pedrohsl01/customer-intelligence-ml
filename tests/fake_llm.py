"""LLM falsa para os testes: imita `groq.Groq` sem rede e sem custo."""

from __future__ import annotations

import json
from types import SimpleNamespace


class FakeLLM:
    def __init__(self, falhar: bool = False):
        self.prompts: list[str] = []
        self.falhar = falhar
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, messages, **_):
        if self.falhar:
            raise RuntimeError("limite de requisições")
        self.prompts.append(messages[-1]["content"])
        n = len(self.prompts)
        persona = {
            "persona_nome": f"Persona {n}", "descricao_persona": "descrição",
            "estrategia_retencao": "estratégia", "copy_notificacao_push": f"push {n}",
            "oferta_sugerida": f"Oferta {n}", "oferta_justificativa": "porque sim",
            "email_assunto": f"Assunto {n}",
            "email_corpo_html": f"<p>Olá {{nome}}, <strong>corpo {n}</strong></p><script>alert(1)</script>",
            "mensagem_whatsapp": f"whats {n} até {{validade}}",
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(persona)))],
            usage=SimpleNamespace(prompt_tokens=300, completion_tokens=80),
        )
