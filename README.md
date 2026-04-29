# Finance Bot

Bot de Telegram para controle financeiro pessoal com gastos, receitas, orcamentos, despesas fixas previstas, analises e previsao diaria automatica.

## Funcionalidades

- cadastro automatico de usuarios ao interagir com o bot;
- `/add valor categoria descricao`: registra um gasto real.
- `/mes`: mostra total do mes, total por categoria e quantidade de lancamentos.
- `/hoje`: lista os gastos de hoje.
- `/dia 15` ou `/dia 22/04/2026`: lista gastos de uma data.
- `/grafico`: envia grafico de pizza por categoria.
- `/edit id valor categoria descricao`: edita um gasto.
- `/delete id`: apaga um gasto.
- `/receita valor descricao` ou `/receitas valor descricao`: registra uma entrada financeira.
- `/saldo`: mostra saldo atual, receitas do mes, gastos do mes, fixos previstos e saldo projetado.
- `/orcamento valor`: define o orcamento total do mes atual.
- `/orcamento categoria valor`: define o orcamento mensal de uma categoria.
- `/previsao`: calcula previsao manual do mes.
- `/comparar`: compara gastos com o mes anterior, total e por categoria.
- `/fixo valor categoria descricao`: cadastra uma despesa fixa prevista.
- `/fixos`: lista despesas fixas e total.
- `/delete_fixo id`: apaga uma despesa fixa prevista.
- `/help`: mostra ajuda.

Cada usuario acessa apenas os proprios dados. O Telegram identifica a pessoa por `telegram_user_id`, e internamente gastos, receitas, orcamentos, fixos e notificacoes usam `users.id` para isolamento dos dados.

## Cadastro de usuarios

No `/start`, e tambem ao usar qualquer comando financeiro, o bot captura:

- `telegram_user_id`;
- `telegram_chat_id`;
- `first_name`;
- `username`.

Se o usuario nao existir, cria um registro em `users`. Se ja existir, atualiza `telegram_chat_id`, `first_name` e `username` quando houver mudanca.

Para restringir o ambiente de testes, configure `ALLOWED_TELEGRAM_IDS` com IDs separados por virgula. Se a variavel estiver vazia, qualquer usuario pode usar o bot.

## Logica de previsao

A previsao usa regras simples, preparadas para evoluir depois com IA:

- calcula media diaria historica com os ultimos 3 meses;
- se houver menos de 3 meses, usa o maximo disponivel;
- se nao houver historico, usa o ritmo do mes atual;
- calcula media diaria do mes atual;
- projeta gastos variaveis ate o fim do mes;
- soma os gastos fixos previstos;
- compara com orcamento total e por categoria;
- gera alertas para aumento acima de 20%, categoria fora do padrao, uso alto do orcamento, saldo projetado negativo e fixos maiores que receita.

Gastos fixos nao entram no historico e nao sao registrados como gastos reais. Eles servem apenas para planejamento.

## Scheduler diario

O arquivo `app/scheduler.py` usa APScheduler com `AsyncIOScheduler`.

- Executa todos os dias as 08:00.
- Usa o timezone de `TIMEZONE` no `.env`.
- Busca todos os usuarios conhecidos no banco.
- Envia uma previsao individual via Telegram.
- Registra o envio em `daily_notifications`.
- Evita duplicidade no mesmo dia com chave unica por usuario e data.

## Estrutura

```text
finance_bot/
├── app/
│   ├── bot/
│   │   ├── handlers.py
│   │   └── commands.py
│   ├── database/
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── session.py
│   ├── services/
│   │   ├── expense_service.py
│   │   ├── income_service.py
│   │   ├── budget_service.py
│   │   ├── analytics_service.py
│   │   ├── alert_service.py
│   │   ├── fixed_expense_service.py
│   │   └── report_service.py
│   ├── utils/
│   │   ├── charts.py
│   │   └── validators.py
│   ├── config.py
│   └── scheduler.py
├── main.py
├── requirements.txt
└── .env.example
```

## Configurar

```powershell
copy .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=token_gerado_pelo_BotFather
DATABASE_URL=
TIMEZONE=America/Sao_Paulo
ALLOWED_TELEGRAM_IDS=
```

## Instalar dependencias

```powershell
cd "C:\Users\rafaelms\Documents\New project\finance_bot"
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Rodar

```powershell
python main.py
```

Sem ativar a venv:

```powershell
.\.venv\Scripts\python.exe main.py
```

Deixe o terminal aberto enquanto usa o bot.

## Variaveis de ambiente

Crie um arquivo `.env` a partir de `.env.example`.

```env
TELEGRAM_BOT_TOKEN=token_gerado_pelo_BotFather
DATABASE_URL=sqlite:///./finance_bot.db
TIMEZONE=America/Sao_Paulo
ALLOWED_TELEGRAM_IDS=
```

- `TELEGRAM_BOT_TOKEN`: obrigatoria.
- `DATABASE_URL`: opcional; quando vazia, usa SQLite local em `./finance_bot.db`.
- `TIMEZONE`: opcional; usada pelo scheduler diario.
- `ALLOWED_TELEGRAM_IDS`: opcional; quando vazia, qualquer usuario pode usar o bot.

Nunca versionar `.env`, bancos SQLite locais ou arquivos de ambiente real.

## Banco e migrations

Para ambiente local simples com SQLite, o bot cria as tabelas automaticamente ao iniciar quando `DATABASE_URL` esta vazia.

Para ambientes compartilhados ou deploy com PostgreSQL, use Alembic. No Railway, o bot executa as migrations automaticamente ao iniciar quando detecta PostgreSQL:

```bash
python main.py
```

Para rodar migrations manualmente:

```powershell
alembic upgrade head
```

Para criar novas migrations depois de alterar modelos:

```powershell
alembic revision --autogenerate -m "descricao da mudanca"
alembic upgrade head
```

SQLite e adequado para desenvolvimento local e uso pessoal com baixo volume. Em deploy no Railway, prefira PostgreSQL porque o filesystem do container pode ser efemero e o arquivo `finance_bot.db` pode ser perdido em redeploy, restart ou recriacao do container.

Exemplo de `DATABASE_URL` para PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/finance_bot
```

Railway pode fornecer `postgres://` ou `postgresql://`; o projeto normaliza essas URLs para `postgresql+psycopg://` automaticamente. O driver `psycopg[binary]` ja esta no `requirements.txt`.

## Rodar com Docker

```powershell
docker compose up --build -d
```

O `docker-compose.yml` usa volume persistente em `/app/data` e define:

```env
DATABASE_URL=sqlite:////app/data/finance_bot.db
```

Para ver logs:

```powershell
docker compose logs -f
```

## Deploy com systemd em VPS

Exemplo de service em Linux:

```ini
[Unit]
Description=Finance Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/finance_bot
EnvironmentFile=/opt/finance_bot/.env
ExecStart=/opt/finance_bot/.venv/bin/python main.py
Restart=always
RestartSec=5
User=financebot

[Install]
WantedBy=multi-user.target
```

Comandos basicos:

```bash
sudo systemctl daemon-reload
sudo systemctl enable finance-bot
sudo systemctl start finance-bot
sudo journalctl -u finance-bot -f
```

## Deploy de teste no Railway

O bot usa polling, entao nao precisa expor porta HTTP. O processo deve ficar rodando 24/7 como worker.

Arquivos de start incluidos:

- `Procfile`: `worker: python main.py`
- `railway.json`: define `startCommand` como `python main.py` e restart em falha.

### 1. Subir o projeto para o GitHub

Confirme que `.env`, bancos SQLite e `.venv` nao foram versionados. O `.gitignore` ja cobre esses arquivos.

### 2. Criar projeto no Railway

1. Acesse Railway.
2. Crie um novo projeto.
3. Escolha deploy a partir do GitHub.
4. Selecione o repositorio do `finance_bot`.
5. Se o Railway pedir um comando de start manual, use `python main.py`.

### 3. Adicionar PostgreSQL no Railway

No canvas do projeto Railway:

1. Clique em `+ New`.
2. Selecione `Database`.
3. Escolha `Add PostgreSQL`.
4. Aguarde o servico PostgreSQL ficar ativo.
5. Abra o servico PostgreSQL e confirme que ele expose variaveis como `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` e `DATABASE_URL`.

### 4. Configurar variaveis de ambiente do bot

No servico do bot, abra `Variables` e configure:

```env
TELEGRAM_BOT_TOKEN=token_real_do_bot
TIMEZONE=America/Sao_Paulo
ALLOWED_TELEGRAM_IDS=
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Use o nome real do seu servico PostgreSQL no lugar de `Postgres`, se ele tiver outro nome no canvas. Essa referencia faz o Railway iniciar o PostgreSQL antes do bot e injeta a URL correta no deploy.

Para teste local sem PostgreSQL, deixe `DATABASE_URL` vazia:

```env
DATABASE_URL=
```

Para teste local apontando para PostgreSQL, use uma URL real:

```env
DATABASE_URL=postgresql://usuario:senha@host:porta/banco
```

O projeto converte automaticamente `postgres://` e `postgresql://` para `postgresql+psycopg://`, compatibilizando a URL do Railway com SQLAlchemy e `psycopg`.

### 5. Persistencia do banco

SQLite em Railway serve apenas para teste rapido. O filesystem pode ser efemero; em redeploy, restart ou recriacao do container, o arquivo `finance_bot.db` pode ser perdido.

Para um teste online mais confiavel, use PostgreSQL no Railway. O app roda as migrations automaticamente antes de iniciar o polling:

```bash
python main.py
```

Se quiser rodar migrations manualmente antes do deploy, rode localmente apontando `DATABASE_URL` para o banco remoto ou use um shell/job temporario no Railway:

```bash
alembic upgrade head
```

### 6. Verificar logs

Depois do deploy, abra `Deployments` ou `Logs` no Railway e procure por:

- instalacao das dependencias do `requirements.txt`;
- execucao de `alembic upgrade head`;
- execucao de `python main.py`;
- ausencia de erro sobre `TELEGRAM_BOT_TOKEN`;
- inicializacao do polling do Telegram;
- logs do scheduler diario.

### 7. Testar o banco correto

1. No Railway, confira nos logs se o deploy executou `alembic upgrade head` sem erro.
2. Envie `/start` para o bot no Telegram.
3. Envie `/add 10 teste deploy`.
4. Envie `/receita 100 teste`.
5. Envie `/orcamento 500`.
6. Envie `/fixo 20 teste fixo`.
7. Reinicie o servico no Railway.
8. Rode `/mes`, `/saldo` e `/fixos`; os dados devem continuar existindo.

Se os dados sumirem apos restart, o bot provavelmente esta usando SQLite efemero em vez de PostgreSQL. Revise `DATABASE_URL` no servico do bot.

### 8. Cuidados de operacao

Use apenas uma instancia ativa do bot. Duas instancias com polling podem conflitar no Telegram e duplicar scheduler. Se futuramente escalar replicas, mova o scheduler para um worker unico ou use lock distribuido no banco.

## Scheduler em producao

O scheduler roda no mesmo processo do bot e executa todos os dias as 08:00 no `TIMEZONE` configurado. Use apenas uma instancia ativa do bot para evitar jobs duplicados. Em deploy com replicas multiplas, mova o scheduler para um worker unico ou adicione lock distribuido no banco.

## Testes automatizados

Os testes usam `unittest` da biblioteca padrao.

```powershell
python -m unittest discover -s tests -v
```

Eles cobrem:

- criacao e reuso de usuario interno;
- isolamento de dados em edicao/delecao de gastos;
- receitas, orcamentos e gastos fixos vinculados ao usuario interno;
- notificacoes diarias sem duplicidade;
- scheduler continuando o envio para outros usuarios quando um envio falha.

## Validacao manual

1. Cadastre receita com `/receita 3500 salario`.
2. Cadastre gasto com `/add 100 alimentacao mercado`.
3. Confira `/saldo`.
4. Defina `/orcamento 3000` e `/orcamento alimentacao 900`.
5. Cadastre fixos com `/fixo 120 academia` e `/fixo 800 aluguel`.
6. Confira `/fixos`.
7. Rode `/previsao`.
8. Rode `/comparar`.
9. Simule dois usuarios e confirme isolamento dos dados.
10. Para testar o scheduler sem esperar 08:00, chame `send_daily_forecasts(application)` em um script de teste com uma aplicacao fake ou ajuste temporariamente o horario do job em `app/scheduler.py`.

## Validacao do cadastro automatico

1. Novo usuario:
   - Envie `/start`.
   - Verifique a tabela `users`; deve haver um registro com `telegram_user_id`, `telegram_chat_id`, `first_name`, `username`, `is_active`, `created_at` e `updated_at`.

2. Usuario existente:
   - Envie `/start` novamente com a mesma conta.
   - O bot deve reutilizar o mesmo `users.id`, sem duplicar usuario.

3. Atualizacao de username:
   - Altere o username no Telegram.
   - Envie `/start`.
   - O campo `username` deve ser atualizado na tabela `users`.

4. Bloqueio por allowlist:
   - Configure `ALLOWED_TELEGRAM_IDS=123456,789012`.
   - Tente usar o bot com outro Telegram ID.
   - O bot deve responder que o usuario nao esta autorizado.

5. Isolamento:
   - Use duas contas diferentes.
   - Registre gastos, receitas, orcamentos e fixos em ambas.
   - Os comandos `/mes`, `/saldo`, `/previsao`, `/fixos`, `/comparar`, `/edit` e `/delete` devem afetar apenas os dados do usuario atual.
