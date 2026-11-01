import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { PNG } from 'pngjs';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const run = promisify(execFile);
const script = new URL('./capture.mjs', import.meta.url).pathname;

const pages = {
  '/ready.html': `<body style="margin:0"><div id="wrap" style="width:120px;height:80px;background:#f00"></div>
    <script>setTimeout(() => { document.body.dataset.ready = '1'; }, 50);</script></body>`,
  '/broken.html': `<body><div id="wrap"></div><script>console.error('module failed to load');</script></body>`,
};

let server;
let base;
let out;

beforeAll(async () => {
  server = createServer((req, res) => {
    const page = pages[req.url];
    res.writeHead(page ? 200 : 404, { 'content-type': 'text/html' });
    res.end(page ?? '');
  });
  await new Promise(resolve => server.listen(0, resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  out = await mkdtemp(join(tmpdir(), 'capture-'));
});

afterAll(async () => {
  server.close();
  await rm(out, { recursive: true, force: true });
});

describe('capture page screenshot', () => {
  it('saves the #wrap element once the page signals it is ready', async () => {
    const file = join(out, 'ready.png');

    await run('node', [script, `${base}/ready.html`, file]);

    const png = PNG.sync.read(await readFile(file));
    expect([png.width, png.height]).toEqual([120, 80]);
  }, 60_000);

  it('fails with the page console when the ready signal never arrives', async () => {
    const failure = run('node', [script, `${base}/broken.html`, join(out, 'broken.png')], { env: { ...process.env, CAP_TIMEOUT_MS: '1500' } });

    await expect(failure).rejects.toMatchObject({ stderr: expect.stringContaining('module failed to load') });
  }, 60_000);
});
