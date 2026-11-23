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
  '--no-proxy-server', '--disable-features=LocalNetworkAccessChecks',
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
    if(process.env.DEBUG_BROWSER && message.method) fs.appendFileSync('out/browser-events.log',JSON.stringify(message)+'\n');
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
    const {targetId} = await call('Target.createTarget', {url:'about:blank'});
    const {sessionId} = await call('Target.attachToTarget', {targetId,flatten:true});
    await call('Runtime.enable', {}, sessionId);
    if(process.env.DEBUG_BROWSER)await call('Network.enable',{},sessionId);
    await call('Page.enable', {}, sessionId);
    const evaluate = async expression => {
      const r = await call('Runtime.evaluate', {expression,returnByValue:true,awaitPromise:true,userGesture:true},sessionId);
      if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));
      return r.result.value;
    };
    const until = async expression => {
      for(let i=0;i<300;i++){if(await evaluate(expression))return;await delay(200);}
      throw new Error('Timed out: '+expression+' '+await evaluate("document.getElementById('status').textContent"));
    };
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false},sessionId);
    await call('Page.navigate',{url:process.argv[2]||'http://127.0.0.1:8765'},sessionId);
    await until("document.getElementById('status').textContent.startsWith('Example loaded')");
    const metadataScore = '@dialect: fallen\n@tempo: 1.237\n@voice: feminine,top=-0.37\n@tone: neutral,anger:0.4\n@predelay: 0.025\n@breath: 0.2\nword\n top: /26/☀';
    await evaluate(`loadScore(${JSON.stringify(metadataScore)}, ++scoreLoad, 'Loaded test score')`);
    assert.equal(await evaluate("$('dialect').value"),'demonic');
    assert.equal(await evaluate("$('tempo').value"),'1.237');
    assert.equal(await evaluate("$('control-voices-top').value"),'-0.37');
    assert.equal(await evaluate("$('control-option-predelay').value"),'25');
    assert.equal(await evaluate("$('control-knobs-breath').value"),'0.2');
    assert.equal(await evaluate("$('control-tones-neutral').checked"),true);
    assert.deepEqual(await evaluate('extraSettings().tones'),{});
    await evaluate("example($('example').value)");
    assert.equal(await evaluate("$('control-voices-top').value"),'0');
    assert.equal(await evaluate("$('control-tones-condescend').value"),'0.6');
    await evaluate(`loadScore(${JSON.stringify('@dialect: nephilim\nword\n top: /26/☀')}, ++scoreLoad, 'Loaded inherited tuning')`);
    assert.equal(await evaluate("$('control-voices-top').value"),'-0.4');
    assert.equal(await evaluate("$('control-voices-1').value"),'0.8');
    assert.equal(await evaluate("$('control-knobs-swap').value"),'0.5');
    assert.deepEqual(await evaluate('extraSettings().voices'),{});
    await evaluate("example('cupid.sera')");
    assert.equal(await evaluate("$('dialect').value"),'cupid');
    assert.equal(await evaluate("$('control-knobs-breath').value"),'0.34');
    assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.editor input:invalid'), input => input.id)"),[]);
    await evaluate("$('render').click()");
    await until("!busy && !!audioBuffer && result?.dialect==='cupid'");
    assert.ok(await evaluate("Object.hasOwn(result.tracks, 'whisper-top')"));
    await evaluate("example($('example').value)");
    assert.equal(await evaluate("document.querySelectorAll('.mouthnode').length"),7);
    assert.ok(await evaluate("document.querySelectorAll('[data-synth]').length>40"));
    await evaluate("$('control-option-prayer_tail').value=1.6; $('control-option-prayer_rise').value=9");
    await evaluate("document.getElementById('control-option-transitions').value=.8; document.getElementById('control-voices-top').value=.65; document.getElementById('control-knobs-breath').value=.1; document.getElementById('control-option-space').checked=false; document.getElementById('control-option-master').checked=false; document.getElementById('control-option-predelay').value=25; document.getElementById('control-tones-neutral').checked=true; document.getElementById('control-export-format').value='float32'; document.getElementById('control-export-preview').checked=true");
    if(process.env.SERAPHIM_TEST_BANKS){
      await evaluate("document.getElementById('control-banks-top').value='miku-en'; document.getElementById('control-banks-praise-1').value='miku-jp-soft'");
    }
    await evaluate("document.getElementById('control-option-syllable_blend').value=.75; document.getElementById('control-option-syllable_blend').dispatchEvent(new Event('input'))");
    assert.equal(await evaluate("document.getElementById('control-blends-top-slider').value"),'0.75');
    assert.equal(await evaluate("document.getElementById('control-blends-top-inherit').checked"),true);
    await evaluate("document.getElementById('control-blends-top').value=0; document.getElementById('control-blends-top').dispatchEvent(new Event('input')); document.getElementById('control-blends-praise-1-inherit').checked=false; document.getElementById('control-blends-praise-1-inherit').dispatchEvent(new Event('change')); document.getElementById('control-blends-praise-1-slider').value=.9; document.getElementById('control-blends-praise-1-slider').dispatchEvent(new Event('input'))");
    assert.equal(await evaluate("document.getElementById('control-blends-top-inherit').checked"),false);
    await evaluate("setMode('gloss'); document.getElementById('text').value='NPFV 1S see-OBJ ABS-light'; document.getElementById('room').value='dry'; document.getElementById('tempo').value=2; document.getElementById('tempo').dispatchEvent(new Event('input')); document.getElementById('render').click()");
    await until("!busy && !!audioBuffer");
    assert.equal(await evaluate(`(() => {
      const [first, second] = result.words;
      updateWord((first.end + second.start) / 2, true);
      return $('nowword').querySelector('.display-current').textContent;
    })()`),'Word 1 of 4');
    assert.equal(await evaluate(`(() => {
      updateWord(result.words.at(-1).end, true);
      return $('nowword').querySelector('.display-current').textContent;
    })()`),'After the last word.');
    await evaluate('updateWord(0, true)');
    assert.equal(await evaluate('Object.keys(result.tracks).length'),8);
    assert.equal(await evaluate('result.resolved.options.prayer_tail'),1.6);
    assert.equal(await evaluate('result.resolved.options.prayer_rise'),9);
    if(process.env.SERAPHIM_TEST_BANKS){
      assert.equal(await evaluate("result.resolved.sample_banks.top.bank"),'miku-en');
      assert.equal(await evaluate("result.resolved.sample_banks['praise-1'].bank"),'miku-jp-soft');
      assert.equal(await evaluate("document.getElementById('bankreport').hidden"),false);
      assert.ok(await evaluate("document.getElementById('bankreport-list').textContent.includes('Formant fallback')"));
    }

    assert.equal(await evaluate('result.resolved.voice.top'),.65);
    assert.equal(await evaluate('result.resolved.syllable_blend.top'),0);
    assert.equal(await evaluate("result.resolved.syllable_blend['1']"),.75);
    assert.equal(await evaluate("result.resolved.syllable_blend['praise-1']"),.9);

    assert.equal(await evaluate('result.resolved.options.transitions'),.8);
    assert.equal(await evaluate('result.prayer_time'),true);
    assert.ok(await evaluate("result.prayerTimeline['praise-1'].length>0"));
    assert.equal(await evaluate('result.resolved.options.space'),false);
    assert.equal(await evaluate('result.resolved.options.master'),false);
    assert.equal(await evaluate('result.resolved.options.predelay'),.025);
    assert.equal(await evaluate('result.resolved.dialect.breath'),.1);
    assert.equal(await evaluate("document.getElementById('offlinepreview').hidden"),false);
    assert.ok(await evaluate("document.getElementById('download').href.endsWith('mix-export.wav')"));

    await evaluate("document.getElementById('play').click()");await delay(300);
    assert.ok(await evaluate('playing && position()>0'));
    assert.ok(await evaluate("$('angel').closest('.angelstage').classList.contains('playing')"));
    await evaluate("document.querySelector('.wordcard').click()");await delay(120);
    assert.equal(await evaluate('active'),0);
    assert.equal(await evaluate("prayerAt(channels.find(c=>c.id==='praise-1')).tense"),'nonpast');
    await evaluate("nodes.get('mouth-top').n.dispatchEvent(new MouseEvent('click'))");
    await until("selectedTrack==='mouth-top' && !!audioBuffer && !document.getElementById('play').disabled");
    assert.ok(await evaluate("document.getElementById('inspector').textContent.includes('Top')"));
    assert.ok(await evaluate('playing'));
    await evaluate("document.getElementById('play').click()");assert.equal(await evaluate('playing'),false);
    assert.ok(await evaluate("result.words[0].tenses.length>0"));
    assert.equal(await evaluate("document.getElementById('grammarpanel').hidden"),false);
    await evaluate("document.getElementById('wordeditor').open=true; document.getElementById('word-tense').value='gnomic+nonpast'; document.getElementById('word-tone').value='fear:0.25'; document.getElementById('word-stammer').checked=true; document.getElementById('word-brightness-top').value='3'; document.getElementById('audition-word').click()");
    await until("!busy && !!audioBuffer && result.selection===0");
    assert.equal(await evaluate('result.words.length'),1);
    assert.equal(await evaluate("result.words[0].tenses.join('+')"),'gnomic+nonpast');
    assert.equal(await evaluate('result.words[0].stammer'),true);
    assert.equal(await evaluate('result.words[0].tones.fear'),.25);
    await evaluate("document.querySelector('.wordcard').click()");
    assert.equal(await evaluate("prayerAt(channels.find(c=>c.id==='praise-1')).tense"),'gnomic');
    assert.ok(await evaluate("language(result.words[0],channels.find(c=>c.id==='praise-1')).includes('steady')"));
    assert.ok(await evaluate("result.source.includes('gnomic+nonpast')"));
    await evaluate("document.getElementById('undo-word').click()");
    await until("!busy && !!audioBuffer && result.selection===null");
    assert.equal(await evaluate('result.words.length'),4);
    assert.equal(await evaluate('result.words[0].stammer'),false);
    await evaluate("document.querySelector('.wordcard').click(); document.getElementById('wordeditor').open=true");
    const screenshot=await call('Page.captureScreenshot',{format:'png'},sessionId);
    fs.mkdirSync('out',{recursive:true});fs.writeFileSync('out/webui-desktop.png',Buffer.from(screenshot.data,'base64'));
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},sessionId);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    const mobile=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true},sessionId);
    fs.writeFileSync('out/webui-mobile.png',Buffer.from(mobile.data,'base64'));
    await evaluate("document.getElementById('theme').click()");
    assert.ok(await evaluate("document.body.classList.contains('light')"));
    await evaluate("document.getElementById('stop').click()");assert.equal(await evaluate('offset'),0);
    assert.deepEqual(errors,[]);
    await evaluate("document.getElementById('reset').click()");
    assert.equal(await evaluate("document.getElementById('control-voices-top').value"),'');
    assert.equal(await evaluate("document.getElementById('control-banks-top').value"),'');
    assert.equal(await evaluate("document.getElementById('control-blends-top').value"),'');
    assert.equal(await evaluate("document.getElementById('control-blends-top-inherit').checked"),true);
    assert.equal(await evaluate("document.getElementById('control-blends-top-slider').disabled"),true);

    assert.equal(await evaluate("document.getElementById('control-option-space').checked"),true);
    await evaluate("setMode('gloss'); $('text').value='NPFV 1S see-OBJ ABS-lighthouse'; document.querySelector('[data-character=cupid]').click(); $('prepare-score').click()");
    await until("$('dictionary-dialog').open && !$('dictionary-form').hidden");
    assert.equal(await evaluate("$('dictionary-gloss').value"), 'lighthouse');
    await evaluate(`$('dictionary-tokens').value='/26/☢ /45/☀ /314/🔆';
      $('dictionary-tokens').dispatchEvent(new Event('input', {bubbles:true}));
      $('dictionary-form').requestSubmit()`);
    await until("$('dictionary-status').textContent.startsWith('Entry saved')");
    await evaluate("$('build-score').click()");
    await until("$('score-dialog').open");
    assert.ok(await evaluate("$('text').value.includes('@dialect: cupid')"));
    const initialCount = await evaluate('scoreView.words.length');
    await evaluate("document.querySelector('[data-arrange=insert]').click()");
    await until(`scoreView.words.length === ${initialCount + 1}`);
    await evaluate(`$('score-tense').value='gnomic+nonpast';
      $('score-tense').dispatchEvent(new Event('input', {bubbles:true}));
      insertPhoneme('/26/☀'); $('score-form').requestSubmit()`);
    await until("scoreView.words[1].tense === 'gnomic+nonpast'");
    assert.equal(await evaluate("scoreView.words[1].mouths.top"), '/26/☀');
    await evaluate("document.querySelector('[data-arrange=up]').click()");
    await until("scoreView.words[0].tense === 'gnomic+nonpast'");
    await evaluate("$('score-undo').click()");
    assert.equal(await evaluate("scoreView.words[1].tense"), 'gnomic+nonpast');
    await evaluate("document.querySelector('[data-arrange=delete]').click()");
    await until(`scoreView.words.length === ${initialCount}`);
    await evaluate(`$('score-undo').click(); $('score-source-panel').open=true;
      $('score-source').value=$('score-source').value.replace(/^@title:.*$/m, '@title: Browser score');
      $('score-source').dispatchEvent(new Event('input')); $('score-source-form').requestSubmit()`);
    await until("scoreView.title === 'Browser score'");
    await evaluate("document.querySelector('[data-close=score-dialog]').click()");
    const authoredScore = await evaluate("$('text').value");
    await call('Page.reload', {}, sessionId);
    await until("studioReady && mode === 'score'");
    assert.equal(await evaluate("$('text').value"), authoredScore);
    assert.equal(await evaluate("dictionaryOverrides.lighthouse.tokens[0]"), '/26/☢');
    assert.equal(await evaluate("$('dialect').value"), 'cupid');
    assert.ok(await evaluate("fetch('/docs').then(r => r.ok)"));
    assert.deepEqual(errors,[]);
    console.log('Authoring passed: character selection, missing vocabulary review, dictionary edit, score arrangement and editing, local storage, and docs.');
    console.log('Web UI passed: per-mouth syllable blend, sliders, inheritance and explicit off, smoothness control and live prayer-time cues, word editing, stacked tense, audition and undo, expanded settings, float export, offline preview, reset, real render, seven channels, play, seek, mouth inspection, solo, pause, stop, mobile layout and theme.');
  } finally {
    browser.kill();
    await new Promise(resolve=>browser.exitCode!==null||browser.signalCode?resolve():browser.once('exit',resolve));
    fs.rmSync(profile,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
