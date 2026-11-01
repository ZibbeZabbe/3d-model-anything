import { expect, test } from '@playwright/test';

/** Views of the public office through the capture page, at a size SwiftShader renders quickly. */
const VIEWS = {
  'office-top': 'room=office-v4&src=model&view=top&ppm=60',
  'office-north': 'room=office-v4&src=model&view=n&ppm=60',
  'office-perspective': 'room=office-v4&src=model&cam=2.5,1.7,2.4&look=-0.5,0.9,-0.8&fov=60&size=640x420',
};
/** Software rendering of the full office takes minutes on a CI runner. */
const READY_TIMEOUT_MS = 540_000;

for (const [name, query] of Object.entries(VIEWS)) {
  test(`${name} renders as before`, async ({ page }, testInfo) => {
    const console_: string[] = [];
    page.on('console', message => console_.push(`${message.type()}: ${message.text()}`));
    page.on('pageerror', error => console_.push(`pageerror: ${error.message}`));
    await page.goto(`/tools/capture.html?${query}`);
    try {
      await page.waitForFunction(() => document.body.dataset.ready === '1', undefined, { timeout: READY_TIMEOUT_MS });
    } finally {
      await testInfo.attach('console', { body: console_.join('\n'), contentType: 'text/plain' });
    }

    await expect(page.locator('#wrap')).toHaveScreenshot(`${name}.png`);
    expect(console_.filter(line => line.startsWith('pageerror'))).toEqual([]);
  });
}
