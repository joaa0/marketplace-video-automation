# Arquitetura — etapa 3

## Componentes

- `app/main.py`: API original de produtos, tarefas, registro e aprovação; autenticação e painel.
- `app/db.py`: esquema SQLite aditivo. Preserva as tabelas originais e adiciona mídias, linhagem, solicitações Flow, fila e estado do bot.
- `app/media.py`: normalização Pillow, hashes, validação ffprobe/FFmpeg e renderização.
- `app/pipeline_api.py`: entrada de mídia, edição, passagem assistida ao Flow, fila, consulta e exportação.
- `app/ai_editor.py`: adaptador REST Gemini configurável; sem repetição automática de chamadas pagas.
- `app/worker.py`: processamento audiovisual persistente.
- `app/telegram_bot.py` e `app/pexels.py`: integrações originais preservadas, com confirmação explícita e offset persistente no bot.
- `app/static/index.html`: painel sem dependências de frontend, com chave somente em memória.

## Dados e linhagem

`products → jobs → assets / renders / tasks / flow_requests / audit_events`.

`assets` registra tipo, origem, referência de direitos, caminho, SHA-256 e metadados. Imagens de IA guardam os IDs das entradas. O retorno assistido do Flow liga uma referência a um clipe enviado pelo operador. `render_assets` guarda as entradas diretas e seus ancestrais no momento da renderização.

Nenhum conteúdo de um ZIP recebido é extraído pela API. A aplicação não baixa URLs informadas pelo usuário. As imagens são reconstruídas a partir dos pixels. Clipes exigem assinatura de contêiner MP4, e áudios exigem assinaturas conhecidas antes do ffprobe. Os processos recebem argumentos em lista, sem shell, com protocolos locais restritos e timeout.

O SQLite usa chaves estrangeiras, transações, timeout de bloqueio e fechamento explícito das conexões. As tabelas adicionais são criadas na inicialização; não há ainda um sistema de migrações versionadas. Faça backup antes de atualizar instalações com dados reais.

## Fila

Estados: `QUEUED → RUNNING → DONE`, com retorno a `QUEUED` em falha local recuperável e `FAILED` ao esgotar três tentativas. Uma tarefa de produto só pode ter uma renderização ativa.

O worker reserva uma tarefa em transação `BEGIN IMMEDIATE`, atribui um token e um prazo de 600 segundos. A renderização é feita fora da transação. Antes de registrar o vídeo, confere novamente o token, a reserva e a integridade das entradas. Registro do render, linhagem, invalidação de aprovações anteriores, auditoria e conclusão da fila são atômicos.

Quedas deixam a tarefa recuperável após a reserva expirar. Resultados de um worker que perdeu a reserva são descartados. Chamadas de IA são síncronas e **não fazem parte dessa fila de repetição**, para evitar consumo duplicado de créditos após resultados desconhecidos.

## Aprovação e exportação

A aprovação exige quatro confirmações explícitas, nome do revisor, vídeo válido e hash íntegro. Ela só pode se referir ao render mais recente da tarefa, e guarda hash, destino, conta e legenda. As confirmações também entram no evento de auditoria.

A exportação exige aprovação ativa da versão atual e igualdade de todos os campos vinculados. Reconfere hash das origens, decodifica o vídeo e inclui no ZIP os mesmos bytes cujo hash foi calculado. O pacote contém vídeo, legenda, aprovação e origem das mídias.

`POST /renders` permanece disponível para compatibilidade, mas agora valida o conteúdo audiovisual. Um render registrado apenas por esse endpoint, sem linhagem de mídia, não pode ser exportado pelo pipeline. Essa restrição corrige a aceitação anterior de arquivos fictícios com extensão MP4; o teste antigo foi atualizado para usar um vídeo real e manter a verificação de alteração de hash.

A revogação bloqueia novas exportações; um arquivo que já foi baixado continua sob responsabilidade do operador. `publication_enabled` permanece falso. Não há adaptador de publicação automática.

## Limites de confiança

Uma chave compartilhada identifica o operador local; o nome do revisor é declarado, sem identidade individual autenticada. Quem tem acesso ao disco pode alterar banco e arquivos. O log SQLite não substitui auditoria externa. O sistema trata evidências de direitos e origem Flow como declarações do operador.

Validação técnica de mídia não comprova SKU, identidade, qualidade publicitária ou licença comercial. Essas verificações continuam humanas. A próxima etapa precisa validar os provedores, endurecer implantação/autenticação e ampliar controle de qualidade e recuperação operacional.
