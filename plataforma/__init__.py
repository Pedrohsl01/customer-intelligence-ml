"""Camada SaaS do app Streamlit: autenticação (Supabase Auth), sessão e acesso ao banco."""

import sys
from pathlib import Path

# O pipeline (`customer_intel`) fica em src/. Garante o import mesmo sem `pip install -e .`
# (ex.: `streamlit run home.py` direto ou deploy no Streamlit Cloud).
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
