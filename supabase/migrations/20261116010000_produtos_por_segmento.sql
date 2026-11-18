-- Produtos mais comprados por segmento, calculados na importação e usados como
-- contexto das campanhas geradas pela IA.
-- Formato: {"<segmento>": [{"produto": text, "quantidade": number, "receita": number, "clientes": int}, ...]}
alter table public.execucoes_segmentacao
    add column produtos_por_segmento jsonb not null default '{}';
