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
DATABASE_URL=sqlite:///./finance_bot.db
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
- `DATABASE_URL`: opcional; usa SQLite local por padrao.
- `TIMEZONE`: opcional; usada pelo scheduler diario.
- `ALLOWED_TELEGRAM_IDS`: opcional; quando vazia, qualquer usuario pode usar o bot.

Nunca versionar `.env`, bancos SQLite locais ou arquivos de ambiente real.

## Banco e migrations

Para ambiente local simples, o bot ainda cria as tabelas automaticamente ao iniciar.

Para ambientes compartilhados ou deploy, use Alembic:

```powershell
alembic upgrade head
```

Para criar novas migrations depois de alterar modelos:

```powershell
alembic revision --autogenerate -m "descricao da mudanca"
alembic upgrade head
```

SQLite e adequado para testes locais e uso pessoal com baixo volume. Migre para PostgreSQL quando houver varios usuarios reais, concorrencia, necessidade de backup/restore confiavel, observabilidade, deploy em nuvem ou evolucao frequente do schema.

Exemplo de `DATABASE_URL` para PostgreSQL:

```env
DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/finance_bot
```

Ao migrar para PostgreSQL, adicione o driver escolhido ao `requirements.txt`.

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
5. Mantenha o comando de start como `python main.py` se o Railway pedir um valor manual.

### 3. Configurar variaveis de ambiente

No Railway, abra `Variables` e configure:

```env
TELEGRAM_BOT_TOKEN=token_real_do_bot
TIMEZONE=America/Sao_Paulo
ALLOWED_TELEGRAM_IDS=
```

Opcional para SQLite:

```env
DATABASE_URL=sqlite:///./finance_bot.db
```

Opcional recomendado para PostgreSQL:

```env
DATABASE_URL=postgresql://usuario:senha@host:porta/banco
```

O projeto converte automaticamente `postgresql://` para `postgresql+psycopg://`, compatibilizando a URL do Railway com SQLAlchemy e `psycopg`.

### 4. Persistencia do banco

SQLite em Railway serve apenas para teste rapido. O filesystem pode ser efemero; em redeploy, restart ou recriacao do container, o arquivo `finance_bot.db` pode ser perdido.

Para um teste online mais confiavel, adicione um PostgreSQL no Railway e use a `DATABASE_URL` fornecida por ele. Antes do primeiro uso em PostgreSQL, rode as migrations:

```bash
alembic upgrade head
```

Se nao houver etapa separada para rodar migrations no Railway, rode localmente apontando `DATABASE_URL` para o banco remoto ou use um shell/job temporario no Railway.

### 5. Verificar logs

Depois do deploy, abra `Deployments` ou `Logs` no Railway e procure por:

- instalacao das dependencias do `requirements.txt`;
- execucao de `python main.py`;
- ausencia de erro sobre `TELEGRAM_BOT_TOKEN`;
- inicializacao do polling do Telegram;
- logs do scheduler diario.

### 6. Cuidados de operacao

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
