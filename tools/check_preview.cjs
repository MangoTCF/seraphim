/* Optional browser smoke test; node tools/check_preview.cjs preview.html.
 * Uses Chromium's debugging pipe, with no listening port or npm packages.
 */
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'seraphim-preview-'));
const browser = spawn(process.env.CHROMIUM || 'chromium', [
  '--headless', '--no-sandbox', '--disable-gpu', '--disable-background-networking',
  '--disable-component-update', '--no-first-run', '--remote-debugging-pipe',
  '--autoplay-policy=no-user-gesture-required', `--user-data-dir=${profile}`,
], {stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
let sequence = 0, input = '', log = '';
const pending = new Map(), errors = [];
browser.stderr.on('data', data => { log = (log + data).slice(-4000); });
browser.stdio[4].on('data', data => {
  input += data.toString();
  let end;
  while ((end = input.indexOf('\0')) >= 0) {
    const message = JSON.parse(input.slice(0, end)); input = input.slice(end + 1);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    if (pending.has(message.id)) {
      const {resolve, reject, timer} = pending.get(message.id); pending.delete(message.id);
      clearTimeout(timer);
      message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
    }
  }
});
browser.on('exit', code => {
  for (const {reject, timer} of pending.values()) { clearTimeout(timer); reject(new Error(`Chromium exited ${code}: ${log}`)); }
  pending.clear();
});
function call(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timeout: ${method}: ${log}`)); }, 30000);
    pending.set(id, {resolve, reject, timer});
    browser.stdio[3].write(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
  });
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  try {
    const {targetId} = await call('Target.createTarget', {url: 'about:blank'});
    const {sessionId} = await call('Target.attachToTarget', {targetId, flatten: true});
    await call('Runtime.enable', {}, sessionId);
    await call('Page.enable', {}, sessionId);
    const evaluate = async expression => {
      const result = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true, userGesture: true}, sessionId);
      if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    await call('Page.navigate', {url: pathToFileURL(path.resolve(process.argv[2])).href}, sessionId);
    let ready = false;
    for (let i = 0; i < 150; ++i) {
      ready = await evaluate("!!document.getElementById('play') && !document.getElementById('play').disabled");
      if (ready || errors.length) break;
      await delay(100);
    }
    assert.deepEqual(errors, []);
    assert.ok(ready, await evaluate("document.getElementById('status')?.textContent"));
    await evaluate("document.getElementById('play').click()");
    await delay(250);
    assert.ok(await evaluate('playing && position() > 0'));
    await evaluate('rows[0].click()');
    await delay(150);
    assert.equal(await evaluate('active'), 0);
    await evaluate("track.value='mouth-top'; track.dispatchEvent(new Event('change'))");
    await delay(100);
    assert.ok(await evaluate("playing && source.buffer === buffers['mouth-top']"));
    await evaluate("document.getElementById('play').click()");
    assert.equal(await evaluate('playing'), false);
    await evaluate("document.getElementById('stop').click()");
    assert.equal(await evaluate('position()'), 0);
    assert.deepEqual(errors, []);
    console.log('Preview passed: audio decoded, playback, seek, highlighting, solo, pause and stop.');
  } finally {
    browser.kill();
    await new Promise(resolve => browser.exitCode !== null || browser.signalCode ? resolve() : browser.once('exit', resolve));
    fs.rmSync(profile, {recursive: true, force: true});
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
