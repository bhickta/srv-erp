const fs = require('fs');
const assert = require('assert');
const {chromium} = require('/home/bhickta/development/oem-bench/browser-tools/node_modules/playwright');
const bench = '/home/bhickta/development/oem-bench';
const secrets = JSON.parse(fs.readFileSync(`${bench}/config/local-secrets.json`));
const fixture = JSON.parse(fs.readFileSync(`${bench}/config/race-fixture.json`));
(async () => {
    const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
    const context = await browser.newContext({baseURL: 'http://127.0.0.1:8011', viewport: {width: 390, height: 844}});
    const login = await context.request.post('/api/method/login', {form: {usr: 'Administrator', pwd: secrets.admin_password}});
    assert.equal(login.status(), 200);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.stack || error.message));
    await page.goto('/app/oem-catalog');
    try { await page.locator('input[data-fieldname="customer"]').waitFor({timeout: 15000}); } catch (error) { await page.screenshot({path: `${bench}/logs/browser-failure.png`, fullPage: true}); console.error(JSON.stringify({url: page.url(), errors, text: (await page.locator('body').innerText()).slice(0,2000)})); throw error; }
    for (const [key, value] of Object.entries(fixture.payload.context)) {
        const input = page.locator(`input[data-fieldname="${key}"]`);
        await input.fill(value); await input.press('Tab');
    }
    await page.getByRole('button', {name: 'Find and configure products'}).click();
    try { await page.locator(`button[data-product="${fixture.payload.product}"]`).click({timeout: 10000}); } catch (error) { console.error(JSON.stringify({errors, text: (await page.locator('body').innerText()).slice(-2200)})); throw error; }
    await page.locator('.oem-config-dialog select').first().waitFor();
    await page.locator('.oem-config-dialog textarea').fill('EXAMPLE');
    const results = [];
    for (const width of [320, 360, 390, 412, 768, 1024, 1440]) {
        await page.setViewportSize({width, height: 844});
        const dimensions = await page.locator('.oem-config-dialog .modal-content').evaluate(node => ({width: node.clientWidth, scroll: node.scrollWidth}));
        assert(dimensions.scroll <= dimensions.width + 1, `Configurator overflow at ${width}: ${JSON.stringify(dimensions)}`);
        results.push({width, content_width: dimensions.width, scroll_width: dimensions.scroll});
    }
    await page.setViewportSize({width: 390, height: 844});
    await page.getByRole('button', {name: 'Review', exact: true}).click();
    await page.getByRole('button', {name: 'Use existing Item'}).waitFor({timeout: 15000});
    await page.screenshot({path: `${bench}/logs/oem-configurator-390.png`, fullPage: true});
    assert.equal(errors.length, 0, JSON.stringify(errors));
    fs.writeFileSync(`${bench}/logs/browser-evidence.json`, JSON.stringify({browser: await browser.version(), viewports: results, javascript_errors: errors}, null, 2));
    console.log(JSON.stringify({viewports: results.length, review: 'existing exact Item', javascript_errors: errors.length}));
    await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
