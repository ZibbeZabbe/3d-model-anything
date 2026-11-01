#!/usr/bin/env node
// Screenshot the capture page's #wrap element once it sets document.body.dataset.ready = '1'.
// usage: node capture.mjs <url> <out.png>
// env:   CAP_TIMEOUT_MS (ready wait, default 120000)
//        CAP_BROWSER_CHANNEL (e.g. "chrome" to use the installed Chrome instead of Playwright's Chromium)
// Needs @playwright/test in the target project (npm i -D @playwright/test; npx playwright install chromium).
import { chromium } from '@playwright/test';

const DEFAULT_TIMEOUT_MS = 120_000;
/** Margin around #wrap so the whole WebGL canvas fits inside the viewport. */
const VIEWPORT_MARGIN_PX = 40;

const [url, out] = process.argv.slice(2);
if (!url || !out) {
  console.error('usage: node capture.mjs <url> <out.png>');
  process.exit(2);
}
const timeout = Number(process.env.CAP_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);

const browser = await chromium.launch({
  channel: process.env.CAP_BROWSER_CHANNEL || undefined,
  args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
});
const console_ = [];
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } });
  page.on('console', message => console_.push(`${message.type()}: ${message.text()}`));
  page.on('pageerror', error => console_.push(`pageerror: ${error.message}`));
  page.on('response', response => { if (response.status() >= 400) console_.push(`HTTP ${response.status()} ${response.url()}`); });
  await page.goto(url);
  await page.waitForFunction(() => document.body.dataset.ready === '1', undefined, { timeout });
  // An element screenshot does not guarantee WebGL pixels outside the viewport: fit the canvas.
  const box = await page.locator('#wrap').boundingBox();
  if (!box) throw new Error('#wrap is not visible');
  await page.setViewportSize({ width: Math.ceil(box.width) + VIEWPORT_MARGIN_PX, height: Math.ceil(box.height) + VIEWPORT_MARGIN_PX });
  await page.locator('#wrap').screenshot({ path: out });
  console.log(out);
} catch (error) {
  console.error(`FAIL ${url}: ${error.message.split('\n')[0]}`);
  console.error('(a missing import makes Vite serve an error page; the page console follows)');
  for (const line of console_.slice(-12)) console.error(line);
  process.exitCode = 1;
} finally {
  await browser.close();
}
