'use strict';

const studioKey = 'seraphim-studio-v1';
const dictionaryKey = 'seraphim-dictionary-v1';
let catalog, catalogRequest, pendingReview, selectedGloss = null;
let scoreView, scoreIndex = 0, scoreChanged = false, sourceChanged = false, scoreWorking = false;
let dictionaryWorking = false, dictionaryChanged = false, studioReady = false;
const scoreUndo = [];
const mouthFields = {};

function readLocal(key) {
  try { return JSON.parse(localStorage.getItem(key)); }
  catch { return null; }
}

function writeLocal(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

const savedDictionary = readLocal(dictionaryKey);
if (savedDictionary && typeof savedDictionary === 'object' && !Array.isArray(savedDictionary)) {
  Object.assign(dictionaryOverrides, savedDictionary);
}

function settingsInputs() {
  return [...document.querySelectorAll('.editor input[id]:not([type=file]), .editor select[id]')]
    .filter(el => el.id !== 'example');
}

function saveStudio() {
  if (!studioReady) return;
  drafts[mode] = $('text').value;
  const inputs = Object.fromEntries(settingsInputs().map(el =>
    [el.id, el.type === 'checkbox' ? el.checked : el.value]));
  if (!writeLocal(studioKey, {drafts, mode, inputs, touched: [...touched], loaded: [...loadedControls]})) {
    $('storage-note').textContent = 'Browser storage is unavailable. Download your score to keep a copy.';
  }
}

window.restoreStudioDraft = function () {
  const saved = readLocal(studioKey);
  if (!saved || !Object.hasOwn(drafts, saved.mode)) return false;
  setMode(saved.mode);
  for (const name of Object.keys(drafts)) {
    if (typeof saved.drafts?.[name] === 'string') drafts[name] = saved.drafts[name];
  }
  $('text').value = drafts[mode];
  applyScoreControls(Object.fromEntries((saved.loaded || []).filter(([id]) => $(id))));
  for (const el of settingsInputs()) {
    const value = saved.inputs?.[el.id];
    if (el.type === 'checkbox' && typeof value === 'boolean') el.checked = value;
    if (typeof value === 'string') el.value = value;
  }
  for (const el of document.querySelectorAll('.blend-knob input[type=number]')) {
    el.dispatchEvent(new Event('input'));
  }
  for (const id of ['voice', 'tempo']) $(id).oninput();
  touched.clear();
  for (const id of saved.touched || []) touched.add(id);
  for (const id of ['voice', 'tempo']) {
    if (!touched.has(id) && !loadedControls.has(id)) $(id + '-value').textContent = 'From score';
  }
  updateSpeaker();
  return true;
};

document.addEventListener('studioready', () => {
  studioReady = true;
  $('prepare-score').disabled = false;
  refreshComposeActions();
  saveStudio();
});
document.addEventListener('compositionchange', () => {
  refreshComposeActions();
  queueMicrotask(saveStudio);
});
document.querySelector('.editor').addEventListener('input', () => {
  refreshComposeActions();
  saveStudio();
});
document.querySelector('.editor').addEventListener('change', saveStudio);
$('reset').addEventListener('click', saveStudio);
window.addEventListener('pagehide', saveStudio);

function refreshComposeActions() {
  $('prepare-score').textContent = mode === 'score' ? 'Open score editor' : 'Prepare score';
  $('export-draft').disabled = mode !== 'score' || !$('text').value.trim();
}

function downloadScore() {
  const url = URL.createObjectURL(new Blob([$('text').value], {type: 'text/plain;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'score.sera';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('export-draft').onclick = $('score-download').onclick = downloadScore;

function compositionRequest(inputMode = mode, text = $('text').value) {
  return {mode: inputMode, text, dialect: inputMode === 'score' ? scoreOverride('dialect') : $('dialect').value, seed: $('seed').value,
    tense: $('tense').value, title: $('title').value, front: $('front').value,
    shuffle: $('shuffle').value, move: $('move').checked, strict: $('strict').checked,
    heresy: $('heresy').checked};
}

async function getCatalog() {
  if (!catalogRequest) {
    catalogRequest = fetch('/api/dictionary').then(async response => {
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Dictionary unavailable');
      catalog = value;
      for (const pos of catalog.parts) $('dictionary-pos').add(new Option(pos, pos));
      for (const [group, values] of [['vowels', catalog.vowels], ['consonants', catalog.consonants]]) {
        for (const value of values) {
          const notation = `/${value}/${group === 'vowels' ? '☀' : ''}`;
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'secondary';
          button.textContent = notation;
          button.onclick = () => insertPhoneme(notation);
          $('phoneme-' + group).append(button);
        }
      }
      return catalog;
    }).catch(error => {
      catalogRequest = null;
      throw error;
    });
  }
  return catalogRequest;
}

function persistDictionary(entries) {
  dictionaryOverrides = entries;
  return writeLocal(dictionaryKey, entries);
}

function dictionaryStatus(message) {
  $('dictionary-status').textContent = message;
}

function openDictionary(review = null) {
  pendingReview = review;
  selectedGloss = null;
  dictionaryChanged = false;
  $('build-score').disabled = false;
  $('dictionary-search').value = '';
  $('dictionary-search-row').hidden = Boolean(review);
  $('review-actions').hidden = !review;
  $('dictionary-form').hidden = true;
  $('dictionary-list').replaceChildren();
  $('dictionary-heading').textContent = review ? 'Review missing words' : 'Dictionary';
  $('dictionary-help').textContent = review
    ? 'Select a coined gloss to change its pronunciation, or accept the suggestions to build the score.'
    : 'Search the installed dictionary or save your own pronunciation in this browser.';
  dictionaryStatus('');
  $('dictionary-dialog').showModal();
  getCatalog().then(() => {
    renderDictionary();
    if (review) selectGloss(Object.keys(review.proposals)[0]);
  }).catch(error => dictionaryStatus(error.message));
}

function renderDictionary() {
  const entries = pendingReview
    ? Object.fromEntries(Object.entries(pendingReview.proposals).map(([gloss, entry]) =>
        [gloss, Object.hasOwn(dictionaryOverrides, gloss) ? dictionaryOverrides[gloss] : entry]))
    : {...catalog.entries, ...dictionaryOverrides};
  const search = $('dictionary-search').value.trim().toLowerCase();
  const matches = Object.keys(entries).sort((a, b) => a.localeCompare(b)).filter(gloss => {
    const {pos, tokens} = entries[gloss];
    return !search || `${gloss} ${pos} ${tokens.join(' ')}`.toLowerCase().includes(search);
  });
  $('dictionary-list').replaceChildren(...matches.map(gloss => {
    const {pos, tokens} = entries[gloss];
    const button = document.createElement('button');
    button.textContent = gloss;
    button.setAttribute('aria-pressed', gloss === selectedGloss);
    const detail = document.createElement('small');
    detail.textContent = `${pos} · ${tokens.join(' ')}${Object.hasOwn(dictionaryOverrides, gloss) ? ' · Saved override' : ''}`;
    button.append(detail);
    button.onclick = () => selectGloss(gloss);
    return button;
  }));
  if (!matches.length) $('dictionary-list').textContent = 'No matching entries.';
  updateDictionaryButtons();
}

function selectGloss(gloss) {
  selectedGloss = gloss;
  dictionaryChanged = false;
  $('build-score').disabled = false;
  const entry = Object.hasOwn(dictionaryOverrides, gloss) ? dictionaryOverrides[gloss] :
    (pendingReview?.proposals[gloss] ?? (Object.hasOwn(catalog.entries, gloss) ? catalog.entries[gloss] : null));
  $('dictionary-form').hidden = false;
  $('dictionary-gloss').value = gloss ?? '';
  $('dictionary-gloss').readOnly = Boolean(pendingReview);
  $('dictionary-pos').value = entry?.pos ?? 'N';
  $('dictionary-tokens').value = entry?.tokens.join(' ') ?? '';
  $('dictionary-remove').hidden = !Object.hasOwn(dictionaryOverrides, gloss);
  $('dictionary-discard').disabled = true;
  renderDictionary();
}

async function updateDictionary(remove = false) {
  if (dictionaryWorking) return;
  const changes = Object.assign(Object.create(null), dictionaryOverrides);
  const gloss = $('dictionary-gloss').value.trim();
  if (remove) delete changes[selectedGloss];
  else changes[gloss] = {
    pos: $('dictionary-pos').value,
    tokens: $('dictionary-tokens').value.trim().split(/\s+/)
  };
  const effective = pendingReview ? {...pendingReview.proposals, ...changes} : changes;
  if (remove && pendingReview && Object.hasOwn(pendingReview.proposals, selectedGloss)) {
    effective[selectedGloss] = pendingReview.proposals[selectedGloss];
  }
  setDictionaryWorking(true);
  try {
    await api('/api/dictionary', {dictionary: effective});
    const stored = persistDictionary(changes);
    if (remove && !pendingReview && !Object.hasOwn(catalog.entries, selectedGloss)) {
      $('dictionary-form').hidden = true;
      selectedGloss = null;
      dictionaryChanged = false;
      renderDictionary();
    } else selectGloss(remove ? selectedGloss : gloss);
    dictionaryStatus(stored ? (remove ? 'Override removed.' : 'Entry saved in this browser.') :
      'Dictionary updated for this session. Browser storage is unavailable.');
  } catch (error) {
    dictionaryStatus(error.message);
  } finally {
    setDictionaryWorking(false);
  }
}

function setDictionaryWorking(value) {
  dictionaryWorking = value;
  $('dictionary-dialog').querySelectorAll('button, input, select').forEach(el => { el.disabled = value; });
  updateDictionaryButtons();
}

function updateDictionaryButtons() {
  for (const button of $('dictionary-list').children) button.disabled = dictionaryWorking || dictionaryChanged;
  $('dictionary-new').disabled = dictionaryWorking || dictionaryChanged;
  $('build-score').disabled = dictionaryWorking || dictionaryChanged || !catalog;
  $('dictionary-discard').disabled = dictionaryWorking || !dictionaryChanged;
}

$('dictionary-form').addEventListener('input', () => {
  dictionaryChanged = true;
  dictionaryStatus('Save or discard your entry edits to continue.');
  updateDictionaryButtons();
});
$('dictionary-discard').onclick = () => {
  selectGloss(selectedGloss);
  dictionaryStatus('');

}

$('dictionary-open').onclick = () => openDictionary();
$('dictionary-search').oninput = () => { if (catalog) renderDictionary(); };
$('dictionary-new').onclick = () => { if (catalog) { selectGloss(null); $('dictionary-gloss').focus(); } };
$('dictionary-form').onsubmit = event => { event.preventDefault(); updateDictionary(); };
$('dictionary-remove').onclick = () => updateDictionary(true);

$('prepare-score').onclick = async () => {
  if (!$('text').value.trim()) return status('Enter a sentence or score first.', true);
  const request = compositionRequest();
  $('prepare-score').disabled = true;
  try {
    const view = await api('/api/compose', {...request, dictionary: dictionaryOverrides});
    if (JSON.stringify(request) !== JSON.stringify(compositionRequest())) return;
    if (Object.keys(view.coined).length) openDictionary({request, proposals: view.coined});
    else openScore(view);
  } catch (error) {
    status(error.message, true);
  } finally {
    $('prepare-score').disabled = false;
  }
};

$('build-score').onclick = async () => {
  const review = pendingReview;
  const entries = Object.assign(Object.create(null), review.proposals, dictionaryOverrides);
  setDictionaryWorking(true);
  try {
    const view = await api('/api/compose', {...review.request, dictionary: entries});
    if (Object.keys(view.coined).length) {
      Object.assign(review.proposals, view.coined);
      renderDictionary();
      dictionaryStatus('Review the additional glosses before building.');
      return;
    }
    const stored = persistDictionary(entries);
    $('dictionary-dialog').close();
    openScore(view);
    if (!stored) $('score-status').textContent = 'Score built. Browser storage is unavailable.';
  } catch (error) {
    dictionaryStatus(error.message);
  } finally {
    setDictionaryWorking(false);
  }
};

for (const [key, name] of [['top', 'Top'], ['1', 'Mouth 1'], ['2', 'Mouth 2'], ['end', 'End']]) {
  const field = document.createElement('textarea');
  field.rows = 2;
  field.spellcheck = false;
  const label = document.createElement('label');
  label.textContent = name;
  label.append(field);
  $('score-mouths').append(label);
  $('phoneme-mouth').add(new Option(name, key));
  mouthFields[key] = field;
  field.addEventListener('focus', () => { $('phoneme-mouth').value = key; });
}

function insertPhoneme(notation) {
  const field = mouthFields[$('phoneme-mouth').value];
  if (/^\s*(?:~\s*)?[Øø_∅]\s*$/.test(field.value)) {
    field.value = field.value.startsWith('~') ? '~ ' : '';
    field.setSelectionRange(field.value.length, field.value.length);
  }
  const {selectionStart: start, selectionEnd: end, value} = field;
  const prefix = start && !/\s/.test(value[start - 1]) ? ' ' : '';
  const suffix = end < value.length && !/\s/.test(value[end]) ? ' ' : '';
  field.setRangeText(prefix + notation + suffix, start, end, 'end');
  field.focus();
  markScoreChanged();
}

function setScoreText(text) {
  if (mode !== 'score') setMode('score');
  $('text').value = drafts.score = text;
  dirty = true;
  document.dispatchEvent(new Event('compositionchange'));
}

function openScore(view) {
  if (mode !== 'score') {
    setScoreText(view.text);
    // The generated source carries its character, including when exported.
    $('dialect').value = view.dialect;
    loadedControls.set('dialect', view.dialect);
    updateSpeaker();
  }
  scoreUndo.length = 0;
  $('score-source-panel').open = false;
  displayScore(view, 0);
  $('score-dialog').showModal();
  getCatalog().catch(error => { $('score-status').textContent = error.message; });
}

function displayScore(view, index) {
  scoreView = view;
  if (!scoreOverride('dialect')) {
    $('dialect').value = view.dialect;
    loadedControls.set('dialect', view.dialect);
    updateSpeaker();
  }
  sourceChanged = false;
  $('score-source').value = view.text;
  $('score-title').textContent = `${view.title} · ${view.words.length} ${view.words.length === 1 ? 'word' : 'words'}`;
  $('score-navigation').replaceChildren(...view.words.map((word, i) => {
    const button = document.createElement('button');
    button.textContent = `${i + 1}. ${word.label || 'Word'}`;
    const detail = document.createElement('small');
    detail.textContent = (word.sentenceStart ? 'Sentence start · ' : '') + word.tense;
    button.append(detail);
    button.onclick = () => selectWord(i);
    return button;
  }));
  $('score-issues').hidden = !view.diagnostics.length;
  $('score-diagnostics').textContent = JSON.stringify(view.diagnostics, null, 2);
  selectWord(index);
  $('score-navigation').children[index].scrollIntoView({block: 'nearest'});
}

function selectWord(index) {
  scoreIndex = index;
  const word = scoreView.words[index];
  $('score-tense').value = word.tense;
  $('score-tone').value = word.tone;
  $('score-stammer').checked = word.stammer;
  for (const [key, field] of Object.entries(mouthFields)) field.value = word.mouths[key];
  [...$('score-navigation').children].forEach((button, i) => button.setAttribute('aria-pressed', i === index));
  scoreChanged = false;
  $('score-status').textContent = 'Score is ready to render.';
  updateScoreButtons();
}

function updateScoreButtons() {
  const blocked = scoreChanged || sourceChanged || scoreWorking;
  for (const button of $('score-navigation').children) button.disabled = blocked;
  for (const button of document.querySelectorAll('[data-arrange]')) {
    button.disabled = blocked || (button.dataset.arrange === 'up' && scoreIndex === 0) ||
      (button.dataset.arrange === 'down' && scoreIndex === scoreView.words.length - 1) ||
      (button.dataset.arrange === 'delete' && scoreView.words.length === 1);
  }
  $('score-undo').disabled = blocked || !scoreUndo.length;
  $('score-render').disabled = blocked || busy;
  $('score-download').disabled = blocked;
  $('score-save').disabled = scoreWorking || !scoreChanged;
  $('score-discard').disabled = scoreWorking || !scoreChanged;
  for (const field of [$('score-tense'), $('score-tone'), $('score-stammer'), ...Object.values(mouthFields)]) {
    field.disabled = scoreWorking || sourceChanged;
  }
  $('phoneme-mouth').disabled = scoreWorking || sourceChanged;
  $('score-form').querySelectorAll('details button').forEach(button => {
    button.disabled = scoreWorking || sourceChanged;
  });
  $('score-source').disabled = scoreWorking || scoreChanged;
  $('score-source-apply').disabled = scoreWorking || !sourceChanged;
  $('score-source-discard').disabled = scoreWorking || !sourceChanged;
}

function markScoreChanged() {
  scoreChanged = true;
  $('score-status').textContent = 'Apply or discard your word edits to continue.';
  updateScoreButtons();
}

async function changeScore(path, data) {
  const request = compositionRequest('score');
  const previous = {view: scoreView, index: scoreIndex};
  scoreWorking = true;
  updateScoreButtons();
  try {
    let view = await api(path, {...request, index: scoreIndex, ...data});
    if (path === '/api/edit-word') view = await api('/api/compose', {...request, text: view.text});
    scoreUndo.push(previous);
    setScoreText(view.text);
    displayScore(view, view.index ?? Math.min(scoreIndex, view.words.length - 1));
  } catch (error) {
    $('score-status').textContent = error.message;
  } finally {
    scoreWorking = false;
    updateScoreButtons();
  }
}

$('score-form').addEventListener('input', event => {
  if (event.target.id !== 'phoneme-mouth') markScoreChanged();
});
$('score-form').onsubmit = event => {
  event.preventDefault();
  if (scoreWorking || !scoreChanged) return;
  changeScore('/api/edit-word', {edit: {
    tense: $('score-tense').value.trim(), tone: $('score-tone').value.trim(),
    stammer: $('score-stammer').checked,
    mouths: Object.fromEntries(Object.entries(mouthFields).map(([key, field]) => [key, field.value]))
  }});
};
$('score-discard').onclick = () => selectWord(scoreIndex);
$('score-source').oninput = () => {
  sourceChanged = $('score-source').value !== scoreView.text;
  $('score-status').textContent = sourceChanged ? 'Validate and apply or discard the score source.' : 'Score is ready to render.';
  updateScoreButtons();
};
$('score-source-form').onsubmit = event => {
  event.preventDefault();
  if (!scoreWorking && sourceChanged) changeScore('/api/compose', {text: $('score-source').value});
};
$('score-source-discard').onclick = () => {
  $('score-source').value = scoreView.text;
  $('score-source').oninput();
};
document.addEventListener('renderstatechange', () => { if (scoreView) updateScoreButtons(); });
for (const button of document.querySelectorAll('[data-arrange]')) {
  button.onclick = () => changeScore('/api/arrange', {action: button.dataset.arrange});
}
$('score-undo').onclick = () => {
  const {view, index} = scoreUndo.pop();
  setScoreText(view.text);
  displayScore(view, index);
};
$('score-render').onclick = () => { $('score-dialog').close(); $('render').click(); };

function canClose(dialog) {
  return dialog.id === 'score-dialog' ? !scoreWorking && !scoreChanged && !sourceChanged : !dictionaryWorking && !dictionaryChanged;
}
for (const button of document.querySelectorAll('[data-close]')) {
  const dialog = $(button.dataset.close);
  button.onclick = () => { if (canClose(dialog)) dialog.close(); };
  dialog.addEventListener('cancel', event => { if (!canClose(dialog)) event.preventDefault(); });
}

for (const option of $('dialect').options) {
  if (!option.value) continue;
  const button = document.createElement('button');
  button.className = 'secondary';
  button.textContent = option.textContent.split(' · ')[0];
  button.dataset.character = option.value;
  button.onclick = () => {
    $('dialect').value = option.value;
    $('dialect').dispatchEvent(new Event('change', {bubbles: true}));
  };
  $('character-picker').append(button);
}
updateSpeaker();
