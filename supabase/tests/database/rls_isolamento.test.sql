-- Testes de isolamento multi-tenant. Rodar com: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(14);

-- ---------------------------------------------------------------------------
-- Massa de teste (como postgres, que ignora RLS)
-- ---------------------------------------------------------------------------
insert into auth.users (id, email) values
    ('a0000000-0000-0000-0000-000000000001', 'admin.a@teste.local'),
    ('b0000000-0000-0000-0000-000000000001', 'admin.b@teste.local'),
    ('a0000000-0000-0000-0000-000000000002', 'leitor.a@teste.local');

insert into public.empresas (id, nome) values
    ('aaaaaaaa-0000-0000-0000-000000000000', 'Empresa A'),
    ('bbbbbbbb-0000-0000-0000-000000000000', 'Empresa B');

insert into public.membros (empresa_id, usuario_id, papel) values
    ('aaaaaaaa-0000-0000-0000-000000000000', 'a0000000-0000-0000-0000-000000000001', 'admin'),
    ('aaaaaaaa-0000-0000-0000-000000000000', 'a0000000-0000-0000-0000-000000000002', 'leitor'),
    ('bbbbbbbb-0000-0000-0000-000000000000', 'b0000000-0000-0000-0000-000000000001', 'admin');

insert into public.importacoes (id, empresa_id, arquivo_nome) values
    ('aaaaaaaa-1111-0000-0000-000000000000', 'aaaaaaaa-0000-0000-0000-000000000000', 'a.csv'),
    ('bbbbbbbb-1111-0000-0000-000000000000', 'bbbbbbbb-0000-0000-0000-000000000000', 'b.csv');

insert into public.transacoes (empresa_id, importacao_id, fatura_id, cliente_id, data_compra, quantidade, preco_unitario) values
    ('aaaaaaaa-0000-0000-0000-000000000000', 'aaaaaaaa-1111-0000-0000-000000000000', 'F1', 'C1', now(), 2, 10),
    ('aaaaaaaa-0000-0000-0000-000000000000', 'aaaaaaaa-1111-0000-0000-000000000000', 'F2', 'C2', now(), 1, 5),
    ('bbbbbbbb-0000-0000-0000-000000000000', 'bbbbbbbb-1111-0000-0000-000000000000', 'F1', 'X1', now(), 3, 7),
    ('bbbbbbbb-0000-0000-0000-000000000000', 'bbbbbbbb-1111-0000-0000-000000000000', 'F2', 'X2', now(), 1, 9),
    ('bbbbbbbb-0000-0000-0000-000000000000', 'bbbbbbbb-1111-0000-0000-000000000000', 'F3', 'X3', now(), 4, 1);

-- ---------------------------------------------------------------------------
-- Admin da empresa A
-- ---------------------------------------------------------------------------
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-0000-0000-000000000001","role":"authenticated"}', true);
set local role authenticated;

select is((select count(*) from public.empresas)::int, 1, 'admin A vê só a própria empresa');
select is((select count(*) from public.transacoes)::int, 2, 'admin A vê só as transações da empresa A');
select is((select count(*) from public.transacoes where empresa_id = 'bbbbbbbb-0000-0000-0000-000000000000')::int, 0,
          'filtrar explicitamente pela empresa B não retorna nada');

select throws_ok(
    $$insert into public.transacoes (empresa_id, importacao_id, fatura_id, cliente_id, data_compra, quantidade, preco_unitario)
      values ('bbbbbbbb-0000-0000-0000-000000000000', 'bbbbbbbb-1111-0000-0000-000000000000', 'F9', 'Z', now(), 1, 1)$$,
    '42501', null, 'admin A não insere dados na empresa B');

select is(
    (with alteradas as (update public.transacoes set quantidade = 99
                        where empresa_id = 'bbbbbbbb-0000-0000-0000-000000000000' returning 1)
     select count(*) from alteradas)::int,
    0, 'admin A não altera transações da empresa B');

select throws_ok(
    $$update public.membros set empresa_id = 'bbbbbbbb-0000-0000-0000-000000000000'
      where usuario_id = 'a0000000-0000-0000-0000-000000000002'$$,
    null, null, 'admin A não move um membro para a empresa B');

select throws_ok(
    $$update public.empresas set plano = 'enterprise'$$,
    '42501', null, 'cliente não altera o próprio plano');

select lives_ok(
    $$update public.empresas set tom_de_voz = 'descontraído'$$,
    'admin A altera o tom de voz da empresa');

select throws_ok(
    $$delete from public.membros where usuario_id = 'a0000000-0000-0000-0000-000000000001'$$,
    'P0001', 'A empresa precisa de pelo menos um admin', 'o último admin não pode sair');

-- ---------------------------------------------------------------------------
-- Leitor da empresa A
-- ---------------------------------------------------------------------------
reset role;
select set_config('request.jwt.claims', '{"sub":"a0000000-0000-0000-0000-000000000002","role":"authenticated"}', true);
set local role authenticated;

select is((select count(*) from public.transacoes)::int, 2, 'leitor A lê as transações da empresa A');

select throws_ok(
    $$insert into public.transacoes (empresa_id, importacao_id, fatura_id, cliente_id, data_compra, quantidade, preco_unitario)
      values ('aaaaaaaa-0000-0000-0000-000000000000', 'aaaaaaaa-1111-0000-0000-000000000000', 'F9', 'Z', now(), 1, 1)$$,
    '42501', null, 'leitor não insere transações');

-- ---------------------------------------------------------------------------
-- Admin da empresa B cria uma segunda empresa
-- ---------------------------------------------------------------------------
reset role;
select set_config('request.jwt.claims', '{"sub":"b0000000-0000-0000-0000-000000000001","role":"authenticated"}', true);
set local role authenticated;

select isnt(public.criar_empresa('Empresa B2'), null, 'criar_empresa retorna o id');
select is((select count(*) from public.membros
           where usuario_id = 'b0000000-0000-0000-0000-000000000001' and papel = 'admin')::int,
          2, 'quem cria a empresa vira admin dela');

-- ---------------------------------------------------------------------------
-- Sem login
-- ---------------------------------------------------------------------------
reset role;
select set_config('request.jwt.claims', '', true);
set local role anon;

select throws_ok($$select count(*) from public.transacoes$$, '42501', null, 'anônimo não acessa dados');

reset role;
select * from finish();
rollback;
