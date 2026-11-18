-- Contatos dos clientes (dados pessoais) para a lista de disparo de campanhas.
-- Um registro por cliente da empresa, atualizado a cada importação que traga contatos.
-- Nunca é enviado à LLM.
create table public.contatos_clientes (
    empresa_id     uuid not null references public.empresas (id) on delete cascade,
    cliente_id     text not null,
    nome           text check (length(nome) <= 120),
    email          text check (email ~ '^[^@\s]+@[^@\s]+\.[a-z]{2,}$'),
    telefone       text check (telefone ~ '^\d{12,15}$'),
    atualizado_em  timestamptz not null default now(),
    primary key (empresa_id, cliente_id)
);

alter table public.contatos_clientes enable row level security;
revoke all on public.contatos_clientes from anon;

create policy contatos_clientes_select on public.contatos_clientes for select to authenticated
    using (empresa_id in (select private.empresas_do_usuario()));
create policy contatos_clientes_insert on public.contatos_clientes for insert to authenticated
    with check (empresa_id in (select private.empresas_do_usuario(array['admin', 'analista'])));
create policy contatos_clientes_update on public.contatos_clientes for update to authenticated
    using (empresa_id in (select private.empresas_do_usuario(array['admin', 'analista'])))
    with check (empresa_id in (select private.empresas_do_usuario(array['admin', 'analista'])));
create policy contatos_clientes_delete on public.contatos_clientes for delete to authenticated
    using (empresa_id in (select private.empresas_do_usuario(array['admin', 'analista'])));

create trigger contatos_clientes_empresa_fixa before update of empresa_id on public.contatos_clientes
    for each row execute function private.bloquear_troca_de_empresa();
