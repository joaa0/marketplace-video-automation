# Roadmap do produto completo

O objetivo continua sendo o produto completo. Os itens abaixo distinguem implementação local, contratos de integração e validação real. Não confundir código disponível com serviço externo validado.

## Implementado e exercitado localmente

- [x] Estrutura original FastAPI/SQLite e cadastro de produtos/tarefas preservados.
- [x] Painel em português para o fluxo de produção, revisão e download.
- [x] Registro de mídia, origem e referência de direitos; hash e linhagem.
- [x] Normalização de fotos, orientação e remoção de metadados.
- [x] Fila persistente com retomada por reserva e limite de tentativas.
- [x] Renderização FFmpeg real em formato vertical H.264 + AAC.
- [x] Aprovação humana por versão, hash, destino, conta e legenda, com checklist.
- [x] Revogação e invalidação de aprovação anterior ao registrar nova versão.
- [x] Exportação de pacote para publicação manual, bloqueada sem aprovação.
- [x] Protocolo de preparação/importação assistida do Flow, com fixture local.
- [x] Contrato simulado do editor de roupas Gemini e falha fechada sem credenciais.
- [x] Chat autorizado, confirmação explícita e persistência do offset Telegram.

## Próxima etapa: aceitação com materiais e contas reais

- [ ] Edição de roupa com Gemini: credencial e modelo válidos, consentimento, fidelidade do SKU e qualidade visual aprovados.
- [ ] Sessão Google Flow: geração real, disponibilidade de recursos, download e retorno do clipe aprovados.
- [ ] Telegram: long polling e respostas reais com a conta autorizada.
- [ ] Pexels: consulta real e revisão das condições de uso de referências.
- [ ] Guardar evidências de aceitação, custos, latências, erros e instruções de recuperação, sem segredos.

## Antes de considerar o produto final

- [ ] Fluxos de revisão de imagem e rejeição com motivo, comparação visual de SKU e proveniência mais forte.
- [ ] Presets por marketplace e checagem dos requisitos atuais de cada destino.
- [ ] Narração/TTS opcional, mixagem de áudio e legendas gravadas no vídeo.
- [ ] Cancelamento, repetição manual, acompanhamento detalhado de tentativas e diagnóstico no painel.
- [ ] Migrações versionadas, backup/restauração testados, retenção e limpeza segura de arquivos órfãos.
- [ ] Autenticação individual, autorização por função, proteção de implantação e limites operacionais.
- [ ] Empacotamento de instalação e testes em Windows, além de Linux.
- [ ] Testes de carga, concorrência e falhas em uma implantação persistente real.
- [ ] Validar se a operação assistida do Flow atende ao produto ou se há uma integração oficial adequada; não assumir API ou automação de sessão validada.
- [ ] Avaliar APIs oficiais de publicação por marketplace e tipo de conta. Mesmo que implementadas, exigir aprovação humana vinculada ao conteúdo e destino imediatamente antes de publicar.

## Critérios para publicação

Aprovação explícita e ativa; direitos conferidos; SKU preservado; preço e disponibilidade atuais; conta e destino corretos; mídia íntegra; credenciais protegidas; nenhuma duplicação quando o resultado de uma publicação for desconhecido.
