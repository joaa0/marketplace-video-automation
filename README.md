
## Etapa 2 — Telegram e Pexels (implementação inicial)

**Importante:** o sistema ainda NÃO é um produto final. O Telegram permite consultar tarefas e aprovar renders já registrados; o Pexels permite pesquisar referências fotográficas. A edição de roupa, Flow e publicação ainda não estão integrados.

### Configurar o Telegram sem programar

1. No Telegram, abra o bot oficial **@BotFather**, envie `/newbot` e siga as instruções.
2. Copie o token recebido para `TELEGRAM_BOT_TOKEN` no seu arquivo `.env` (nunca no GitHub).
3. Descubra seu identificador numérico de chat (`chat_id`) e coloque-o em `TELEGRAM_ALLOWED_CHAT_ID`. Não use um ID de outra pessoa.
4. Carregue as variáveis do `.env` no terminal antes de iniciar os processos. O Python **não lê `.env` automaticamente** neste projeto. Em sistemas Unix: `set -a; source .env; set +a`. No PowerShell, defina as variáveis de ambiente para a sessão ou utilize um gerenciador de ambiente.
5. Com o ambiente virtual ativo, execute `python -m app.telegram_bot` em um segundo terminal.
6. Envie `/ajuda` e `/jobs` para o seu bot. Para aprovar um render existente, use `/aprovar ID_DO_RENDER`.

**Segurança:** o bot ignora qualquer chat diferente do configurado. O comando `/aprovar` não publica vídeos; ele apenas registra a autorização, verificando o hash do arquivo.

### Configurar pesquisa de imagens

1. Crie uma chave da API do Pexels e coloque-a em `PEXELS_API_KEY` no `.env`.
2. Inicie o FastAPI conforme as instruções acima.
3. Abra `/docs`, autorize cada chamada incluindo o cabeçalho `x-operator-key` e execute `GET /media/models`.
4. Os resultados são **referências**: antes de criar publicidade com pessoas identificáveis, obtenha e documente a autorização adequada para uso e manipulação comercial. O endpoint não declara nenhuma pessoa como autorizada.

### Limitações desta etapa

- O Telegram usa *long polling*, portanto o computador deve permanecer ligado e com internet.
- A lista de tarefas é persistida em SQLite, mas o offset do Telegram é mantido apenas em memória. Após reinicialização, mensagens podem ser processadas novamente; as aprovações exigem controles adicionais de idempotência antes de produção.
- Não existe automação do Google Flow ou editor de roupas nesta versão.
- Não existe publicação automática, nem tentativa de contornar restrições das plataformas.
