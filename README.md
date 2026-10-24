# Marketplace Video Automation

Um estúdio local para preparar vídeos de produtos, organizar imagens e autorizações, renderizar um vídeo vertical e revisar cada versão antes de baixar o pacote de publicação.

**Estado desta entrega (etapa 3):** o fluxo local foi testado com arquivos reais e FFmpeg. Há um painel em português, ainda sem validação visual em navegador nesta entrega. Edição de roupas por IA e geração no Google Flow ainda precisam de validação com as contas e os materiais do operador. Esta versão **ainda não é o produto final pronto para produção**. As pendências estão em [docs/ROADMAP.md](docs/ROADMAP.md).

## O que já é possível fazer

1. Cadastrar seu produto e abrir uma tarefa.
2. Adicionar fotos da peça, fotos de pessoas autorizadas, imagens já editadas, clipes MP4 e trilhas ou narrações.
3. Registrar a origem e a referência da autorização de cada arquivo.
4. Normalizar fotos JPEG, PNG e WebP, corrigindo a orientação e removendo metadados como localização.
5. Solicitar uma edição de roupa pelo adaptador Gemini, depois de configurar o serviço. **O contrato da integração tem testes simulados; a geração externa ainda não foi testada.**
6. Preparar um pacote de referência e prompt para operar o Google Flow na sua conta, e vincular o clipe baixado à tarefa.
7. Renderizar em uma fila persistente: MP4 H.264, vertical 720 × 1280, 30 quadros/segundo e áudio AAC.
8. Assistir à prévia, conferir o produto, autorizações, legenda, preço e estoque, e aprovar a versão para uma conta e destino específicos.
9. Baixar um ZIP com vídeo, legenda, aprovação e referências das mídias. Publicar manualmente na conta aprovada.

O sistema não publica por conta própria. Uma alteração no vídeo, uma versão mais recente ou a revogação da aprovação bloqueiam a exportação. A integridade das mídias de origem também é conferida na exportação.

## O que você precisa

- Python **3.11 ou 3.12**. Esta entrega foi testada em Python 3.12, Linux.
- FFmpeg e ffprobe disponíveis no computador. Confira com `ffmpeg -version` e `ffprobe -version`.
- Espaço para guardar as imagens, vídeos e banco de dados.
- Para serviços opcionais: credenciais próprias do Telegram, Pexels e Gemini, e acesso ao Google Flow.

Comece com materiais de teste. As chamadas ao editor e as gerações no Flow podem consumir créditos dos provedores.

## Instalação no Linux

No Ubuntu/Pop!_OS, instale o FFmpeg:

```bash
sudo apt update
sudo apt install ffmpeg python3-venv
```

Abra um terminal na pasta do projeto e execute:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie a chave gerada para `OPERATOR_API_KEY` no arquivo `.env`. Não envie esse arquivo ao GitHub. As variáveis do `.env` agora são carregadas automaticamente; valores já definidos no ambiente têm preferência.

Para reproduzir exatamente as versões Python testadas, use `python -m pip install -r requirements.lock` no lugar de `requirements.txt`.

No Windows, crie o ambiente com `py -m venv .venv`, ative com `.venv\Scripts\Activate.ps1` e copie a configuração com `Copy-Item .env.example .env`. Instale FFmpeg e inclua seus executáveis no PATH. **A instalação Windows não foi validada nesta entrega.**

## Abrir o estúdio

No primeiro terminal, com o ambiente virtual ativo:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No segundo terminal, na mesma pasta e com o mesmo ambiente virtual:

```bash
python -m app.worker
```

Acesse **http://127.0.0.1:8000** no navegador e informe a chave do operador. A chave fica somente na memória da página; você precisará digitá-la novamente ao recarregar.

A API também está documentada em **http://127.0.0.1:8000/docs**. Os endpoints de operação exigem o cabeçalho `X-Operator-Key`. `/` e `/health` não exibem seus dados sem autenticação.

Esta instalação é destinada a **um operador em um computador local**. Para acesso remoto ou múltiplos operadores, ainda é necessário preparar HTTPS, autenticação individual, controle de acesso, limites de requisição e implantação adequada. Mantenha o endereço de escuta em `127.0.0.1` nesta etapa.

## Seu primeiro vídeo

1. No painel, conecte com a chave e cadastre SKU, nome e link do produto.
2. Envie uma foto como **Foto do produto / roupa**. Informe de onde veio e a referência da licença ou autorização arquivada. Esse registro é uma declaração sua; o programa não verifica juridicamente o documento.
3. Para um teste sem IA, selecione essa imagem na etapa **Renderizar**. Escolha uma duração de 2 a 60 segundos, escreva a legenda e informe o marketplace e a conta.
4. Clique em **Colocar na fila**. O worker cria o vídeo e o painel acompanha o processamento. Se recarregar, selecione a tarefa para retomar o acompanhamento.
5. Clique em **Carregar prévia**, confira o vídeo inteiro e os dados exibidos. Marque as quatro confirmações e informe seu nome.
6. Clique em **Aprovar esta versão** e depois **Baixar pacote aprovado**.
7. Abra o ZIP e publique o vídeo manualmente, usando a legenda e a conta registradas. Confira novamente preço e disponibilidade na hora de publicar.

A imagem é ajustada com bordas quando necessário, sem corte do produto. Um clipe curto é repetido até completar a duração escolhida. A trilha escolhida também pode ser repetida; **o áudio original do clipe é substituído**. Sem trilha, o resultado contém uma faixa silenciosa. Não há geração de voz nesta etapa: você pode enviar uma narração já gravada.

A legenda é um arquivo `legenda.txt` para a publicação; ela ainda não é gravada sobre a imagem do vídeo.

## Fotos e edição de roupa por IA

As fotos devem ter pelo menos 256 pixels em cada dimensão e no máximo 25 milhões de pixels. O programa guarda uma cópia PNG de até 2160 pixels no lado maior. Cada envio tem limite de 50 MiB. Clipes aceitos: MP4 de até 300 segundos e 4096 pixels em cada dimensão. Trilhas: WAV, MP3, Ogg ou FLAC.

Para usar o editor:

1. Configure `GEMINI_API_KEY` e `GEMINI_IMAGE_MODEL` no `.env`, escolhendo um modelo de imagem disponível na sua conta.
2. Reinicie a API.
3. Adicione uma foto da pessoa autorizada e uma foto da roupa, com as respectivas evidências de uso e edição.
4. Na etapa de edição, selecione os dois arquivos e descreva detalhes que precisam ser preservados.
5. Solicite a edição. O resultado será registrado como uma nova mídia, ligado às fotos originais e ao modelo configurado.
6. Confira rosto, proporções, cor, estampa, logotipos, costuras e caimento. O sistema **não garante fidelidade do SKU automaticamente**.

O adaptador segue a [documentação oficial de geração e edição de imagens Gemini](https://ai.google.dev/gemini-api/docs/generate-content/image-generation). Não há modelo fixado por padrão: disponibilidade, preço e adequação precisam ser conferidos na conta. Os testes locais verificam o formato da requisição e a leitura da resposta com um serviço simulado; não comprovam qualidade visual nem funcionamento em uma conta real.

Não há repetição automática de chamadas pagas. Se ocorrer timeout, confira o histórico do provedor antes de tentar novamente: uma solicitação sem resposta pode já ter consumido créditos.

## Google Flow: operação assistida

Esta etapa implementa a **preparação e o recebimento dos arquivos**, sem controlar sua sessão do Google ou afirmar ter executado uma geração externa.

1. Selecione uma imagem e descreva o movimento no painel.
2. Baixe o pacote Flow: ele contém `reference.png`, `prompt.txt`, instruções e o identificador da solicitação.
3. Abra [Google Flow](https://labs.google/fx/tools/flow) na sua conta. Crie um vídeo vertical usando a imagem como quadro ou ingrediente, conforme as opções disponíveis.
4. Use o prompt, gere, revise o produto e baixe o MP4.
5. Envie o clipe na mesma tarefa, escolhendo **Clipe MP4, inclusive do Flow**. Registre a origem e as condições de uso.
6. Selecione o clipe e clique em **Vincular clipe à solicitação**. Ao retomar uma tarefa, a solicitação pendente mais recente aparece no painel.
7. Renderize o clipe, revise e aprove o vídeo final normalmente.

Esse fluxo acompanha as opções de referências descritas na [ajuda oficial do Flow](https://support.google.com/flow/answer/16353334?hl=pt-BR). Os testes usaram um clipe gerado localmente como fixture; **não houve sessão Google nem geração Flow real**. O sistema registra a origem externa como declarada pelo operador.

## Telegram opcional

1. No Telegram, crie um bot com o **@BotFather**.
2. Preencha `TELEGRAM_BOT_TOKEN` e seu identificador numérico em `TELEGRAM_ALLOWED_CHAT_ID`.
3. Execute `python -m app.telegram_bot` em um terceiro terminal.
4. Use `/ajuda` ou `/jobs` para consultar as tarefas.
5. Depois de revisar o vídeo no painel e conferir SKU, direitos, legenda, preço e estoque, use `/aprovar ID_DO_VIDEO CONFIRMO`.

O bot ignora chats não autorizados. A confirmação registra aprovação, sem publicar. O offset de leitura fica no SQLite. Após falha de rede, uma mensagem pode ser tentada novamente; uma aprovação já ativa não é duplicada. A entrega de respostas não tem garantia de exatamente uma vez.

A autorização do chat e a aprovação têm testes locais com transporte simulado. **As chamadas à API real do Telegram ainda não foram validadas.**

## Pexels opcional

Configure `PEXELS_API_KEY` e consulte `GET /media/models` em `/docs`, enviando a chave do operador. Essa pesquisa fornece referências e autoria, sem baixar nem registrar automaticamente as imagens. Pessoas identificáveis não são marcadas como autorizadas para publicidade.

O código original foi preservado. A ausência de credencial e os limites de consulta têm testes; a pesquisa externa com uma chave real segue pendente.

## Onde seus dados ficam

Por padrão, tudo fica na pasta `data/`:

- `app.sqlite3`: produtos, tarefas, autorizações, aprovações e auditoria.
- `media/`: cópias normalizadas das imagens, clipes e áudios.
- `renders/`: vídeos finais.

Os caminhos podem ser definidos no `.env`. Não edite ou apague uma mídia usada em uma aprovação: a exportação detectará a alteração. Para produzir outra versão, envie outro arquivo e renderize novamente.

Faça backup da pasta `data/` e do `.env` com os processos parados. Guarde as credenciais separadamente e com acesso restrito. Não há ainda rotina automática de backup, retenção ou limpeza de arquivos órfãos. O registro de auditoria fica no próprio SQLite; ele não é um log externo inviolável contra alguém com acesso ao disco.

## Se algo não funcionar

| Situação | O que fazer |
| --- | --- |
| “Chave de operador inválida” | Confira `OPERATOR_API_KEY` no `.env`, reinicie a API e reconecte o painel. |
| Tarefa permanece `QUEUED` | Inicie o worker na mesma pasta, com o mesmo `.env`. |
| Tarefa ficou `RUNNING` após uma queda | Reinicie o worker. Ele retoma após expirar a reserva de até 10 minutos. |
| Renderização falha | Confira FFmpeg/ffprobe, o formato dos arquivos e a mensagem no processamento. Há no máximo três tentativas por processamento. |
| Vídeo ou mídia alterada | Registre uma nova mídia e gere outra versão. Não tente reutilizar a aprovação anterior. |
| Editor retorna erro | Confira chave/modelo e o histórico do provedor antes de repetir uma operação paga. |
| Exportação bloqueada | Aprove a versão mais recente, confira integridade e direitos das origens, ou gere pelo pipeline se o vídeo foi registrado apenas pela API antiga. |
| Perdi o ID do vídeo | Reconecte, selecione a tarefa e use a lista de vídeos no passo 5. |

## Testes e desenvolvimento

```bash
python -m pytest -q
```

Os testes de mídia usam **FFmpeg/ffprobe de verdade**. A suíte verifica imagens inválidas, metadados, geração audiovisual, edição simulada, fila, limite de tentativas, isolamento entre tarefas, autenticação, alterações de hash, versões antigas, revogação, exportação e aprovação pelo transporte simulado do Telegram.

Há também um teste opcional de navegador em `scripts/smoke_studio.cjs`. Ele exige Node, Playwright e Chromium instalados e uma API/worker isolados com dados sintéticos. Rode com `MVA_URL`, `MVA_KEY` e o caminho de uma imagem sintética. Não o execute sobre dados de uso real: ele cria um produto, renderiza, aprova, exporta e revoga uma fixture.

Para entender o funcionamento interno, leia [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). O resultado e os limites dos testes desta entrega estão em [docs/VALIDATION.md](docs/VALIDATION.md).
