const puppeteer = require('puppeteer');

async function main() {
  const baseUrl = process.env.TEST_BASE_URL || 'http://localhost:3000';
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1366, height: 900 });

    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(String(error && error.message ? error.message : error)));

    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('body', { timeout: 30000 });
    await page.waitForFunction(() => document.body && document.body.innerText.trim().length > 0, {
      timeout: 30000,
    });

    const result = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
        .map((button) => button.textContent && button.textContent.trim())
        .filter(Boolean)
        .slice(0, 12);
      const inputs = document.querySelectorAll('input, textarea, select').length;
      return {
        title: document.title,
        textSample: document.body.innerText.trim().slice(0, 500),
        buttonCount: buttons.length,
        buttons,
        inputCount: inputs,
      };
    });

    console.log(JSON.stringify(result, null, 2));

    if (pageErrors.length > 0) {
      throw new Error(`Page runtime errors: ${pageErrors.join(' | ')}`);
    }
    if (!result.textSample) {
      throw new Error('Smoke check failed: page rendered no visible text');
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
