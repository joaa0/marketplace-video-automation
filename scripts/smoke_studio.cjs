// Optional full browser test. Requires npm package playwright and its Chromium.
// Run only against an isolated local API/worker with synthetic data.
// MVA_URL=http://127.0.0.1:8081 MVA_KEY=... node scripts/smoke_studio.cjs /path/to/fixture.png
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const fixture = process.argv[2];
  if (!fixture || !process.env.MVA_KEY) throw Error('Informe imagem sintética e MVA_KEY.');
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];
    page.on('pageerror', e=>errors.push(e.message));
    await page.goto(process.env.MVA_URL || 'http://127.0.0.1:8081');
    await page.locator('#key').fill(process.env.MVA_KEY);
    await page.locator('#connect button').click();
    await page.getByText('Conectado. Escolha uma tarefa ou cadastre um produto.').waitFor();
    await page.locator('#sku').fill('BROWSER-TEST');
    await page.locator('#title').fill('Produto de teste sintético');
    await page.locator('#url').fill('https://example.org/test');
    await page.locator('#product button').click();
    await page.getByText('Produto cadastrado e tarefa criada. Adicione as mídias.').waitFor();
    const job=await page.locator('#jobs').inputValue();
    await page.locator('#source').fill('Imagem sintética de teste');
    await page.locator('#rights').fill('Fixture sintética sem pessoa, não publicar');
    await page.locator('#file').setInputFiles(fixture);
    await page.locator('#upload button').click();
    await page.getByText('Mídia validada e registrada.').waitFor();
    const visual=await page.locator('#visual option').nth(1).getAttribute('value');
    await page.locator('#visual').selectOption(visual);
    await page.locator('#duration').fill('2');
    await page.locator('#caption').fill('Teste local, sem publicação');
    await page.locator('#account').fill('conta-de-teste');
    await page.locator('#render button').click();
    await page.getByText('Vídeo pronto para revisão. Carregue a prévia.').waitFor({timeout:30000});
    await page.locator('#preview').click();
    await page.waitForFunction(()=>document.querySelector('#video').readyState>=1);
    const info=await page.locator('#reviewInfo').textContent();
    assert(info.includes('conta-de-teste') && info.includes('Teste local, sem publicação'));
    await page.locator('#reviewer').fill('Operador de teste');
    for (const id of ['checkSku','checkRights','checkCaption','checkPrice']) await page.locator('#'+id).check();
    await page.locator('#approval button').click();
    await page.getByText('Versão aprovada. Você já pode baixar o pacote para publicação manual.').waitFor();
    const downloaded=page.waitForEvent('download');
    await page.locator('#export').click();
    assert.equal((await downloaded).suggestedFilename(), 'pacote-publicacao.zip');
    await page.locator('#revoke').click();
    await page.getByText('Aprovação revogada. A exportação está bloqueada.').waitFor();
    await page.reload();
    assert.equal(await page.locator('#key').inputValue(), '');
    await page.locator('#key').fill(process.env.MVA_KEY);
    await page.locator('#connect button').click();
    await page.getByText('Conectado. Escolha uma tarefa ou cadastre um produto.').waitFor();
    await page.locator('#jobs').selectOption(job);
    await page.waitForFunction(()=>document.querySelector('#savedRenders').options.length>1);
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'Mobile overflow');
    assert.deepEqual(errors,[]);
    console.log('Browser E2E passed: product → asset → real worker → preview → approve → export → revoke → reload; mobile width 390px.');
  } finally {
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
