-- =============================================================================
-- Customer Intelligence SaaS — schema multi-tenant inicial (Supabase)
--
-- Isolamento: toda tabela de dados tem `empresa_id` e Row Level Security.
-- Um usuário só enxerga linhas das empresas em que é membro (tabela `membros`).
--
-- Papéis por empresa:
--   admin    → gerencia membros e configurações da empresa + tudo de analista
--   analista → importa dados, executa segmentações e gera estratégias
--   leitor   → apenas leitura
--
-- ATENÇÃO: a chave `service_role` ignora RLS. Use-a só em processos de
-- servidor (worker) e sempre filtrando por empresa_id explicitamente.
-- =============================================================================

create schema if not exists private;  -- não exposto pela API do Supabase
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

-- -----------------------------------------------------------------------------
-- Tabelas
-- -----------------------------------------------------------------------------

create table public.empresas (
    id          uuid primary key default gen_random_uuid(),
    nome        text not null check (length(trim(nome)) between 2 and 120),
    setor       text check (length(setor) <= 80),
    tom_de_voz  text check (length(tom_de_voz) <= 500),  -- vai para o prompt da IA
    moeda       char(3) not null default 'BRL' check (moeda ~ '^[A-Z]{3}$'),
    plano       text not null default 'free' check (plano in ('free', 'pro', 'enterprise')),
    criado_em   timestamptz not null default now()
);

-- Dados de exibição do usuário. Login, e-mail e senha ficam em auth.users (Supabase Auth).
create table public.perfis (
    id          uuid primary key references auth.users (id) on delete cascade,
    nome        text not null,
    cargo       text,
    criado_em   timestamptz not null default now()
);

create table public.membros (
    empresa_id  uuid not null references public.empresas (id) on delete cascade,
    usuario_id  uuid not null references auth.users (id) on delete cascade,
    papel       text not null default 'leitor' check (papel in ('admin', 'analista', 'leitor')),
    criado_em   timestamptz not null default now(),
    primary key (empresa_id, usuario_id)
);
create index membros_usuario_idx on public.membros (usuario_id);

-- Cada upload de arquivo. Permite auditar e desfazer uma importação.
create table public.importacoes (
    id                uuid primary key default gen_random_uuid(),
    empresa_id        uuid not null references public.empresas (id) on delete cascade,
    arquivo_nome      text not null,
    mapeamento        jsonb not null default '{}',   -- coluna do arquivo → coluna padrão
    relatorio_limpeza jsonb,                         -- RelatorioLimpeza.to_dict()
    status            text not null default 'pendente'
                      check (status in ('pendente', 'processando', 'concluida', 'erro')),
    erro              text,
    criado_por        uuid references auth.users (id) on delete set null default auth.uid(),
    criado_em         timestamptz not null default now(),
    unique (empresa_id, id)
);

create table public.transacoes (
    id                bigint generated always as identity primary key,
    empresa_id        uuid not null references public.empresas (id) on delete cascade,
    importacao_id     uuid not null,
    fatura_id         text not null,
    cliente_id        text not null,  -- código do cliente no sistema da empresa
    data_compra       timestamptz not null,
    quantidade        numeric(14, 3) not null check (quantidade <> 0),
    preco_unitario    numeric(14, 4) not null check (preco_unitario > 0),
    valor             numeric(16, 2) generated always as (quantidade * preco_unitario) stored,
    eh_devolucao      boolean generated always as (quantidade < 0) stored,
    produto_codigo    text,
    produto_descricao text,
    pais              text,
    foreign key (empresa_id, importacao_id)
        references public.importacoes (empresa_id, id) on delete cascade
);
create index transacoes_cliente_idx    on public.transacoes (empresa_id, cliente_id);
create index transacoes_data_idx       on public.transacoes (empresa_id, data_compra);
create index transacoes_importacao_idx on public.transacoes (empresa_id, importacao_id);

-- Cada execução do pipeline (RFM + K-Means). Mantém histórico de segmentações.
create table public.execucoes_segmentacao (
    id               uuid primary key default gen_random_uuid(),
    empresa_id       uuid not null references public.empresas (id) on delete cascade,
    data_referencia  date not null,
    k                smallint not null check (k between 2 and 12),
    silhouette       double precision,
    inertia          double precision,
    total_clientes   integer,
    parametros       jsonb not null default '{}',
    artefato_modelo  text,  -- caminho no Supabase Storage (scaler + kmeans)
    status           text not null default 'pendente'
                     check (status in ('pendente', 'processando', 'concluida', 'erro')),
    erro             text,
    criado_por       uuid references auth.users (id) on delete set null default auth.uid(),
    criado_em        timestamptz not null default now(),
    concluido_em     timestamptz,
    unique (empresa_id, id)
);
create index execucoes_empresa_idx on public.execucoes_segmentacao (empresa_id, criado_em desc);

create table public.clientes_segmentados (
    empresa_id   uuid not null,
    execucao_id  uuid not null,
    cliente_id   text not null,
    recency      integer not null check (recency >= 0),
    frequency    integer not null check (frequency > 0),
    monetary     numeric(16, 2) not null check (monetary > 0),
    cluster      smallint not null,
    segmento     text not null,
    primary key (execucao_id, cliente_id),
    foreign key (empresa_id, execucao_id)
        references public.execucoes_segmentacao (empresa_id, id) on delete cascade
);
create index clientes_segmentados_segmento_idx
    on public.clientes_segmentados (empresa_id, execucao_id, segmento);

create table public.estrategias_ia (
    id              uuid primary key default gen_random_uuid(),
    empresa_id      uuid not null,
    execucao_id     uuid not null,
    segmento        text not null,
    persona         jsonb not null check (
                        persona ?& array['persona_nome', 'descricao_persona',
                                         'estrategia_retencao', 'copy_notificacao_push']),
    modelo          text not null,
    versao_prompt   text not null,
    tokens_entrada  integer,
    tokens_saida    integer,
    criado_em       timestamptz not null default now(),
    unique (execucao_id, segmento),
    foreign key (empresa_id, execucao_id)
        references public.execucoes_segmentacao (empresa_id, id) on delete cascade
);
create index estrategias_empresa_idx on public.estrategias_ia (empresa_id, criado_em desc);

-- Resumo por segmento (medianas: RFM é muito assimétrico).
-- security_invoker = true → a view respeita o RLS de quem consulta.
create view public.resumo_segmentos with (security_invoker = true) as
select
    empresa_id,
    execucao_id,
    segmento,
    count(*)                                                    as quantidade_clientes,
    percentile_cont(0.5) within group (order by recency)        as recency_mediana,
    percentile_cont(0.5) within group (order by frequency)      as frequency_mediana,
    percentile_cont(0.5) within group (order by monetary)       as monetary_mediano,
    avg(monetary)                                               as monetary_medio,
    sum(monetary)                                               as monetary_total,
    sum(monetary) / nullif(sum(frequency), 0)                   as ticket_medio
from public.clientes_segmentados
group by empresa_id, execucao_id, segmento;

-- -----------------------------------------------------------------------------
-- Funções auxiliares de autorização
-- SECURITY DEFINER para ler `membros` sem recursão de RLS. Nas policies são
-- usadas como `empresa_id in (select ...)`, o que faz o Postgres avaliar a
-- função uma vez por consulta (e não uma vez por linha).
-- -----------------------------------------------------------------------------

create function private.empresas_do_usuario(papeis text[] default null)
returns setof uuid
language sql stable security definer set search_path = ''
as $$
    select m.empresa_id
    from public.membros m
    where m.usuario_id = (select auth.uid())
      and (papeis is null or m.papel = any (papeis));
$$;

revoke all on function private.empresas_do_usuario(text[]) from public, anon;
grant execute on function private.empresas_do_usuario(text[]) to authenticated;

-- -----------------------------------------------------------------------------
-- Row Level Security
-- -----------------------------------------------------------------------------

alter table public.empresas              enable row level security;
alter table public.perfis                enable row level security;
alter table public.membros               enable row level security;
alter table public.importacoes           enable row level security;
alter table public.transacoes            enable row level security;
alter table public.execucoes_segmentacao enable row level security;
alter table public.clientes_segmentados  enable row level security;
alter table public.estrategias_ia        enable row level security;

-- Nada é acessível sem login.
revoke all on public.empresas, public.perfis, public.membros, public.importacoes,
              public.transacoes, public.execucoes_segmentacao, public.clientes_segmentados,
              public.estrategias_ia, public.resumo_segmentos
    from anon;

-- empresas: membros leem; só admin altera. Criação só pela função criar_empresa().
create policy empresas_select on public.empresas for select to authenticated
    using (id in (select private.empresas_do_usuario()));
create policy empresas_update on public.empresas for update to authenticated
    using (id in (select private.empresas_do_usuario(array['admin'])))
    with check (id in (select private.empresas_do_usuario(array['admin'])));

-- O plano é cobrança: não pode ser alterado pelo cliente, só pelo service_role.
-- (Revogar só a coluna não basta quando há grant na tabela inteira, que é o
-- padrão do Supabase; por isso revoga-se tudo e concede-se coluna a coluna.)
revoke update on public.empresas from authenticated;
grant update (nome, setor, tom_de_voz, moeda) on public.empresas to authenticated;

-- perfis: cada um edita o seu; vê o dos colegas de empresa.
create policy perfis_select on public.perfis for select to authenticated
    using (
        id = (select auth.uid())
        or id in (select m.usuario_id from public.membros m
                  where m.empresa_id in (select private.empresas_do_usuario()))
    );
create policy perfis_update on public.perfis for update to authenticated
    using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- membros: colegas se veem; só admin adiciona, altera papel ou remove.
create policy membros_select on public.membros for select to authenticated
    using (empresa_id in (select private.empresas_do_usuario()));
create policy membros_insert on public.membros for insert to authenticated
    with check (empresa_id in (select private.empresas_do_usuario(array['admin'])));
create policy membros_update on public.membros for update to authenticated
    using (empresa_id in (select private.empresas_do_usuario(array['admin'])))
    with check (empresa_id in (select private.empresas_do_usuario(array['admin'])));
create policy membros_delete on public.membros for delete to authenticated
    using (empresa_id in (select private.empresas_do_usuario(array['admin'])));

-- Tabelas de dados: membros leem; admin e analista escrevem.
do $$
declare
    tabela text;
begin
    foreach tabela in array array['importacoes', 'transacoes', 'execucoes_segmentacao',
                                  'clientes_segmentados', 'estrategias_ia']
    loop
        execute format(
            'create policy %1$s_select on public.%1$I for select to authenticated
                 using (empresa_id in (select private.empresas_do_usuario()))', tabela);
        execute format(
            'create policy %1$s_insert on public.%1$I for insert to authenticated
                 with check (empresa_id in (select private.empresas_do_usuario(array[''admin'', ''analista''])))', tabela);
        execute format(
            'create policy %1$s_update on public.%1$I for update to authenticated
                 using (empresa_id in (select private.empresas_do_usuario(array[''admin'', ''analista''])))
                 with check (empresa_id in (select private.empresas_do_usuario(array[''admin'', ''analista''])))', tabela);
        execute format(
            'create policy %1$s_delete on public.%1$I for delete to authenticated
                 using (empresa_id in (select private.empresas_do_usuario(array[''admin'', ''analista''])))', tabela);
    end loop;
end
$$;

-- -----------------------------------------------------------------------------
-- Regras de integridade
-- -----------------------------------------------------------------------------

-- Uma linha nunca muda de empresa (evita "mover" dados entre tenants).
create function private.bloquear_troca_de_empresa()
returns trigger language plpgsql set search_path = ''
as $$
begin
    if new.empresa_id is distinct from old.empresa_id then
        raise exception 'empresa_id não pode ser alterado';
    end if;
    return new;
end;
$$;

do $$
declare
    tabela text;
begin
    foreach tabela in array array['membros', 'importacoes', 'transacoes', 'execucoes_segmentacao',
                                  'clientes_segmentados', 'estrategias_ia']
    loop
        execute format(
            'create trigger %1$s_empresa_fixa before update of empresa_id on public.%1$I
                 for each row execute function private.bloquear_troca_de_empresa()', tabela);
    end loop;
end
$$;

-- A empresa precisa manter ao menos um admin (exceto quando ela própria é excluída).
create function private.proteger_ultimo_admin()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    if old.papel = 'admin'
       and (tg_op = 'DELETE' or new.papel <> 'admin')
       and exists (select 1 from public.empresas e where e.id = old.empresa_id)
       and not exists (select 1 from public.membros m
                       where m.empresa_id = old.empresa_id
                         and m.papel = 'admin'
                         and m.usuario_id <> old.usuario_id)
    then
        raise exception 'A empresa precisa de pelo menos um admin';
    end if;
    return coalesce(new, old);
end;
$$;

create trigger membros_ultimo_admin before update or delete on public.membros
    for each row execute function private.proteger_ultimo_admin();

-- -----------------------------------------------------------------------------
-- Fluxos que precisam contornar o RLS de forma controlada
-- -----------------------------------------------------------------------------

-- Perfil criado automaticamente no cadastro (Supabase Auth).
create function private.criar_perfil()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
    insert into public.perfis (id, nome)
    values (new.id, coalesce(nullif(new.raw_user_meta_data ->> 'nome', ''), new.email, 'Usuário'));
    return new;
end;
$$;

create trigger ao_criar_usuario after insert on auth.users
    for each row execute function private.criar_perfil();

-- Cria a empresa e torna quem chamou o primeiro admin (o RLS sozinho não
-- permitiria: ninguém é membro de uma empresa que ainda não existe).
create function public.criar_empresa(p_nome text, p_setor text default null,
                                     p_tom_de_voz text default null, p_moeda text default 'BRL')
returns uuid
language plpgsql security definer set search_path = ''
as $$
declare
    v_usuario uuid := auth.uid();
    v_empresa uuid;
begin
    if v_usuario is null then
        raise exception 'Usuário não autenticado';
    end if;

    insert into public.empresas (nome, setor, tom_de_voz, moeda)
    values (p_nome, p_setor, p_tom_de_voz, p_moeda)
    returning id into v_empresa;

    insert into public.membros (empresa_id, usuario_id, papel)
    values (v_empresa, v_usuario, 'admin');

    return v_empresa;
end;
$$;

revoke all on function public.criar_empresa(text, text, text, text) from public, anon;
grant execute on function public.criar_empresa(text, text, text, text) to authenticated;
