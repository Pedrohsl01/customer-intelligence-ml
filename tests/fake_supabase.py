"""Cliente Supabase falso, em memória, para testar o app sem rede.

Imita o encadeamento do supabase-py (table().select().eq()...execute()) e
registra os filtros de cada consulta para os testes conferirem o isolamento.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace


class _Consulta:
    def __init__(self, banco: "FakeSupabase", tabela: str):
        self.banco, self.tabela = banco, tabela
        self.filtros: list[tuple[str, object]] = []
        self.filtros_diferente: list[tuple[str, object]] = []
        self.operacao, self.valores = "select", None
        self.ordem, self.limite, self.intervalo = None, None, None

    def select(self, colunas="*"):
        self.colunas = colunas
        return self

    def update(self, valores):
        self.operacao, self.valores = "update", valores
        return self

    def insert(self, valores, returning="representation"):
        self.operacao = "insert"
        self.valores = valores if isinstance(valores, list) else [valores]
        return self

    def upsert(self, valores, on_conflict="id", returning="representation"):
        self.operacao = "upsert"
        self.valores = valores if isinstance(valores, list) else [valores]
        self.conflito = [c.strip() for c in on_conflict.split(",")]
        return self

    def delete(self):
        self.operacao = "delete"
        return self

    def neq(self, coluna, valor):
        self.filtros_diferente.append((coluna, valor))
        return self

    def eq(self, coluna, valor):
        self.filtros.append((coluna, valor))
        return self

    def order(self, coluna, desc=False):
        self.ordem = (coluna, desc)
        return self

    def limit(self, n):
        self.limite = n
        return self

    def range(self, inicio, fim):
        self.intervalo = (inicio, fim)
        return self

    def execute(self):
        self.banco.consultas.append(self)
        if self.banco.falhar_em == (self.operacao, self.tabela):
            raise RuntimeError("falha simulada de rede")
        if self.operacao == "insert":
            self.banco.relogio += 1
            novas = [{"id": str(uuid.uuid4()), "criado_em": f"2027-01-01T00:00:{self.banco.relogio:06d}", **v}
                     for v in self.valores]
            self.banco.tabelas.setdefault(self.tabela, []).extend(novas)
            return SimpleNamespace(data=[dict(n) for n in novas])
        if self.operacao == "upsert":
            tabela = self.banco.tabelas.setdefault(self.tabela, [])
            for valor in self.valores:
                existente = next((l for l in tabela if all(l.get(c) == valor.get(c) for c in self.conflito)), None)
                if existente:
                    existente.update(valor)
                else:
                    tabela.append({"id": str(uuid.uuid4()), **valor})
            return SimpleNamespace(data=[])
        origem = self.banco.resumo() if self.tabela == "resumo_segmentos" else self.banco.tabelas.get(self.tabela, [])
        linhas = [l for l in origem
                  if all(l.get(c) == v for c, v in self.filtros)
                  and all(l.get(c) != v for c, v in self.filtros_diferente)]
        if self.operacao == "delete":
            apagar = {id(l) for l in linhas}
            self.banco.tabelas[self.tabela] = [l for l in origem if id(l) not in apagar]
            return SimpleNamespace(data=[])
        if self.operacao == "update":
            for linha in linhas:
                linha.update(self.valores)
            return SimpleNamespace(data=linhas)
        if self.ordem:
            linhas = sorted(linhas, key=lambda l: l.get(self.ordem[0]), reverse=self.ordem[1])
        if self.intervalo:
            linhas = linhas[self.intervalo[0]:self.intervalo[1] + 1]
        if self.limite is not None:
            linhas = linhas[:self.limite]
        return SimpleNamespace(data=[dict(l) for l in linhas])


class _Auth:
    def __init__(self):
        self.sessao = SimpleNamespace(access_token="token")

    def get_session(self):
        return self.sessao

    def sign_out(self):
        self.sessao = None


class FakeSupabase:
    def __init__(self, tabelas: dict[str, list[dict]] | None = None):
        self.tabelas = tabelas or {}
        self.consultas: list[_Consulta] = []
        self.chamadas_rpc: list[tuple[str, dict]] = []
        self.auth = _Auth()
        self.relogio = 0
        self.falhar_em: tuple[str, str] | None = None  # ex.: ("insert", "clientes_segmentados")

    def resumo(self) -> list[dict]:
        """Imita a view resumo_segmentos a partir de clientes_segmentados."""
        if "resumo_segmentos" in self.tabelas:
            return self.tabelas["resumo_segmentos"]
        grupos: dict[tuple, list[dict]] = {}
        for linha in self.tabelas.get("clientes_segmentados", []):
            grupos.setdefault((linha["empresa_id"], linha["execucao_id"], linha["segmento"]), []).append(linha)
        from statistics import median

        return [{"empresa_id": e, "execucao_id": x, "segmento": s, "quantidade_clientes": len(ls),
                 "recency_mediana": median(l["recency"] for l in ls),
                 "frequency_mediana": median(l["frequency"] for l in ls),
                 "monetary_mediano": median(l["monetary"] for l in ls),
                 "monetary_total": sum(l["monetary"] for l in ls),
                 "ticket_medio": sum(l["monetary"] for l in ls) / sum(l["frequency"] for l in ls),
                 "monetary_medio": sum(l["monetary"] for l in ls) / len(ls)}
                for (e, x, s), ls in grupos.items()]

    def table(self, nome):
        return _Consulta(self, nome)

    def rpc(self, funcao, parametros):
        self.chamadas_rpc.append((funcao, parametros))
        novo_id = str(uuid.uuid4())
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=novo_id))
