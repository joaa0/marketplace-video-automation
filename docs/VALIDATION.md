# Validação da etapa 3 — 24/10/2026

## Resultado

- Base do ZIP: **4 testes passaram** antes das alterações.
- Suíte ampliada desta entrega: **27 testes passaram**, em 10,03 segundos.
- `python -m compileall -q app tests`: passou.
- Verificação de sintaxe do JavaScript embutido no painel e do script opcional Playwright: passou.
- `python -m pip check`: nenhuma dependência quebrada.
- `git diff --check`: sem erros de espaço em branco.
- Aviso conhecido: o TestClient da versão instalada de Starlette informa descontinuação do uso de `httpx` e sugere `httpx2`; os testes passaram. A migração dessa dependência não foi incluída nesta etapa.

Ambiente: Linux, Python 3.12.14, FFmpeg/ffprobe 6.1.1. Versões Python usadas: `requirements.lock`.

## O que foi exercitado de verdade

| Área | Evidência local | Limite |
| --- | --- | --- |
| API e SQLite | Cadastro, persistência, rotas autenticadas, isolamento de tarefas e consulta | Sem teste de carga ou instalação multiusuário |
| Imagens | Leitura e reconstrução de PNG, remoção de metadados, tamanho mínimo, transparência sobre branco e rejeição de arquivos inválidos | JPEG/WebP suportados pelo código, mas sem matriz ampla de fixtures reais nesta entrega |
| Vídeo | FFmpeg produziu MP4 720×1280 H.264/yuv420p com AAC; ffprobe e decodificação completa confirmaram o conteúdo | Fixtures curtas, sintéticas; sem campanha comercial real |
| Áudio | WAV sintético incorporado à renderização e faixa silenciosa quando não há trilha | Sem TTS, mixagem com áudio original ou avaliação humana de áudio comercial |
| Fila | Reserva, impossibilidade de segunda reserva simultânea sequencial, recuperação após expiração, três tentativas e falha definitiva | Sem teste de múltiplos processos concorrentes sob carga |
| Aprovação | Checklist, integridade, versão mais recente, rejeição de duplicatas e revogação | Revisor declarado por chave local compartilhada |
| Exportação | Bloqueio sem aprovação, verificação de vídeo e origens, correspondência de hash/conta/destino/legenda, ZIP com conteúdo real | Sem publicação em plataforma externa |
| Origem Flow | Pacote com referência/prompt e vinculação de clipe com linhagem | Clipe de teste produzido pelo FFmpeg, sem geração Google |
| Painel | Entrega HTML, cabeçalhos, sintaxe JS e endpoints usados pelo painel | Teste visual/E2E em navegador **não concluído** |

## Serviços externos: não validados nesta entrega

| Serviço | Implementação | Teste realizado | Teste real pendente |
| --- | --- | --- | --- |
| Gemini | Envio de duas imagens e instruções; gravação de nova imagem e linhagem | HTTP simulado, leitura de resposta de imagem, resposta sem imagem, ausência de configuração | Chave/modelo reais, geração paga, fidelidade de roupa/identidade e latência |
| Google Flow | Passagem assistida com ZIP e importação de MP4 pelo operador | Roundtrip local com fixture | Conta Google, geração, download e aceitação do resultado |
| Telegram | Long polling, chat autorizado, confirmação explícita e offset SQLite | Transporte simulado para autorização e aprovação | Bot real, rede e retomada após reinício |
| Pexels | Pesquisa original preservada | Chave ausente e limite de consulta | Busca com chave real e aceitação das referências |

## Bloqueio de verificação do navegador

Foi preparado `scripts/smoke_studio.cjs` para exercitar o fluxo completo e a largura móvel de 390 pixels. A execução parou antes de abrir a página: o Chromium não estava instalado. As tentativas de instalação retornaram arquivos de download inválidos/vazios. Portanto, **não há afirmação de aprovação visual, reprodução no navegador ou sucesso desse E2E**.

O script fica disponível para execução em um ambiente com Playwright/Chromium e uma API/worker isolados. Os testes FastAPI e FFmpeg não dependem desse navegador e foram concluídos.

## Próximo aceite necessário

Validar o painel em navegador real, repetir o fluxo com materiais autorizados do produto e executar os serviços externos nas contas corretas. Só depois avançar para declarar essas integrações operacionais. O roadmap mantém critérios adicionais para a entrega do produto final.
