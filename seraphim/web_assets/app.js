'use strict';
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const channels = [
  {id:'praise-1',name:'Prayer I',label:'PRAYER I',prayer:0},
  {id:'mouth-1',key:'1',name:'Mouth 1',label:'MOUTH 1'},
  {id:'mouth-2',key:'2',name:'Mouth 2',label:'MOUTH 2'},
  {id:'praise-2',name:'Prayer II',label:'PRAYER II',prayer:1},
  {id:'praise-3',name:'Prayer III',label:'PRAYER III',prayer:2},
  {id:'mouth-end',key:'end',name:'End',label:'END'},
  {id:'mouth-top',key:'top',name:'Top',label:'TOP'}
];
const speechChannels = ['top','1','2','end'].map(key=>channels.find(c=>c.key===key));
const languageNames = {latin:'Latin',greek:'Greek',aramaic:'Aramaic',la:'Latin',gr:'Greek',ar:'Aramaic'};
const trackLabel = id => id === 'mix' ? 'Full ensemble' : channels.find(c=>c.id===id)?.name || id.replaceAll('-',' ');
let mode='score', token='', job=null, result=null, active=-1, inspected=null, selectedTrack='mix';
let ctx, gain, source, audioBuffer, startedAt=0, offset=0, playing=false, loadSequence=0;
let busy=false, dirty=false;
const touched = new Set();
const loadedControls = new Map();
let scoreLoad = 0;
let dictionaryOverrides = Object.create(null);
const drafts = {score:'',english:'The angel sees the light.',gloss:'NPFV 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure'};
const nodes = new Map();
function svg(tag, attrs, parent) { const n=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);parent.append(n);return n; }
const points=[];
channels.forEach((c,i)=>{
  const angle=-Math.PI/2 + i*2*Math.PI/7, x=350+194*Math.cos(angle), y=303+194*Math.sin(angle);
  points.push(`${x},${y}`);
  const n=svg('g',{class:`mouthnode${c.prayer!==undefined?' prayer':''}`,transform:`translate(${x} ${y})`,tabindex:0,role:'button','aria-label':`${c.name}: inspect and solo`,'aria-pressed':false},$('mouthnodes'));
  const halo=svg('circle',{r:32,class:'nodehalo'},n);
  if(c.key){
    const flare=svg('g',{class:'vowel-flare','aria-hidden':'true'},n);
    svg('circle',{r:30,class:'vowel-aura'},flare);
    svg('circle',{r:28,class:'vowel-ring'},flare);
    svg('circle',{r:34,class:'vowel-corona'},flare);
  }
  svg('circle',{r:24,class:'nodebg'},n);
  svg('path',{d:'M-13 0Q0 -10 13 0Q0 10 -13 0Z',class:'mouthshape'},n);
  const opening=svg('ellipse',{cx:0,cy:0,rx:8,ry:1.4,fill:c.prayer!==undefined?'var(--secondary)':'var(--primary)',opacity:.65},n);
  const dy=y<180?-43:43;
  svg('text',{y:dy,class:'nodelabel'},n).textContent=c.label;
  const gloss=svg('text',{y:dy+15,class:'nodegloss'},n); gloss.textContent=c.key?'—':'Tense / prayer';
  const select=()=>{if(!result)return;inspected=c.id;showInspector(); if(result.tracks[c.id])changeTrack(selectedTrack===c.id?'mix':c.id);};
  n.onclick=select;n.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}};
  nodes.set(c.id,{n,halo,opening,gloss});
});
$('heptagon').setAttribute('points',points.join(' '));
const speakerForms = {
  seraphic:'six-winged angel',
  cupid:'winged heart pierced by an arrow beneath a halo',
  demonic:'horned demon with angular bat wings',
  succubus:'succubus with swept wings and a curled tail',
  nephilim:'nephilim with feathered and fractured wings'
};
function updateSpeaker() {
  const dialect = $('dialect').value || result?.dialect || 'seraphic';
  for (const button of $('character-picker').children) {
    button.setAttribute('aria-pressed', String(button.dataset.character === dialect));
  }
  const stage = $('angel');
  stage.dataset.dialect = dialect;
  stage.setAttribute('aria-label', `Schematic ${speakerForms[dialect]} with seven mouths at the vertices of a regular heptagon`);
}
let controlSections=[];
function createSynthControls(sections){
  controlSections=sections;
  $('synthcontrols').replaceChildren();
  for(const section of sections){
    const details=document.createElement('details');
    const summary=document.createElement('summary');summary.textContent=section.title;
    const plus=document.createElement('span');plus.textContent='＋';summary.append(plus);
    const help=document.createElement('p');help.className='controlhelp';help.textContent=section.help;
    const fields=document.createElement('div');fields.className='fields advanced';
    for(const field of section.fields){
      const label=document.createElement('label');label.className='synthfield';
      const input=document.createElement(field.kind==='select'?'select':'input');
      input.id=`control-${field.target}-${field.key}`;input.dataset.synth='true';
      if(field.kind==='select'){
        for(const choice of field.choices){const opt=document.createElement('option');opt.value=typeof choice==='object'?choice.value:choice;opt.textContent=typeof choice==='object'?choice.label:choice==='float32'?'Float32 · raw headroom':'PCM16 · compatible';input.append(opt);}
        input.value=field.default;
      }else if(field.kind==='checkbox'){
        input.type='checkbox';input.checked=field.default;label.className='switchline synthcheck';
      }else{
        input.type='number';input.step=field.key==='jobs'?'1':'any';
        if(field.min!==null)input.min=field.min;if(field.max!==null)input.max=field.max;
        input.placeholder=field.default===null?'From score / dialect':`Default: ${field.default}`;
      }
      input.addEventListener('input',()=>{dirty=true;});
      if(field.kind==='checkbox')label.append(input,field.label);else label.append(field.label,input);
      const hint=document.createElement('small');hint.className='controlhint';hint.textContent=field.help;
      const container=document.createElement('div');container.className='controlitem';container.append(label);
      if(field.kind==='number'&&(field.target==='blends'||field.key==='syllable_blend')){
        container.classList.add('blend-knob');if(field.target==='blends')input.placeholder='Inherit global';
        const controls=document.createElement('div');controls.className='blend-range';
        const slider=document.createElement('input');slider.type='range';slider.min=0;slider.max=1;slider.step=.05;slider.value=.5;slider.id=`${input.id}-slider`;slider.setAttribute('aria-label',field.label);
        let inherit=null;
        const sync=()=>{if(inherit)inherit.checked=input.value==='';slider.disabled=!!inherit?.checked;slider.value=input.value!==''?input.value:(field.target==='blends'?($('control-option-syllable_blend')?.value||'.5'):'.5');dirty=true;updateInheritedBlends();};
        slider.oninput=()=>{input.value=slider.value;sync();};input.addEventListener('input',sync);controls.append(slider);
        if(field.target==='blends'){
          const inheritLabel=document.createElement('label');inheritLabel.className='blend-inherit';
          inherit=document.createElement('input');inherit.type='checkbox';inherit.checked=true;inherit.id=`${input.id}-inherit`;inherit.setAttribute('aria-label',`${field.label}: inherit global`);slider.disabled=true;
          inherit.onchange=()=>{input.value=inherit.checked?'':($('control-option-syllable_blend')?.value||'.5');sync();};
          inheritLabel.append(inherit,'Inherit');controls.append(inheritLabel);
        }
        container.append(controls);
      }
      container.append(hint);fields.append(container);
    }
    details.append(summary,help,fields);$('synthcontrols').append(details);
  }
}
function updateInheritedBlends(){
  const global=$('control-option-syllable_blend')?.value||'.5';
  for(const channel of channels){
    const key=channel.key||channel.id;
    const input=$(`control-blends-${key}`),slider=$(`control-blends-${key}-slider`);
    if(input&&slider&&input.value==='')slider.value=global;
  }
}
function extraSettings(){
  const payload={knobs:{},voices:{},tones:{},export:{},banks:{},blends:{}};
  for(const section of controlSections)for(const field of section.fields){
    const input=$(`control-${field.target}-${field.key}`);
    if(field.kind==='number'&&input.value==='')continue;
    const value=field.kind==='checkbox'?input.checked:field.kind==='number'?Number(input.value):input.value;
    if(loadedControls.get(input.id)===value)continue;
    (field.target==='option'?payload:payload[field.target])[field.key]=value;
  }
  for(const key of ['title','front','shuffle'])if($(key).value!=='')payload[key]=$(key).value;
  for(const key of ['move','strict','heresy'])payload[key]=$(key).checked;
  return payload;
}
function resetExtraSettings(){
  createSynthControls(controlSections);
  for(const key of ['title','front','shuffle'])$(key).value='';
  $('move').checked=true;$('strict').checked=$('heresy').checked=false;
}
function applyScoreControls(values){
  for(const [id,value] of Object.entries(values)){
    const input=$(id);
    if(input.type==='checkbox')input.checked=value;
    else {
      if(input.type==='range'){
        input.step='any';
        input.min=Math.min(Number(input.min),Number(value));
        input.max=Math.max(Number(input.max),Number(value));
      }
      input.value=value;
    }
    if(id==='voice'||id==='tempo'){
      input.oninput();
      touched.delete(id);
    }
    loadedControls.set(id,input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value);
  }
  updateSpeaker();
}
function scoreOverride(id){
  const value=$(id).value;
  return loadedControls.get(id)===value?'':value;
}
async function loadScore(text,sequence,message){
  setMode('score');
  $('text').value=drafts.score=text;
  resetSettings();
  $('tense').value='nonpast';
  try{
    const values=await api('/api/score-controls',{text});
    if(sequence!==scoreLoad||mode!=='score'||$('text').value!==text)return;
    applyScoreControls(values);
    status(message);
    document.dispatchEvent(new Event('compositionchange'));
  }catch(e){
    if(sequence===scoreLoad&&mode==='score'&&$('text').value===text)status(e.message,true);
  }
}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function time(t){t=Math.max(0,Math.floor(t||0));return `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`;}
function position(){return playing?Math.min(result?.duration||0,offset+ctx.currentTime-startedAt):offset;}
function stopSource(){if(source){source.onended=null;try{source.stop();}catch{}source.disconnect();source=null;}}
function pause(){offset=position();playing=false;stopSource();$('play').textContent='▶';$('play').setAttribute('aria-label','Play');}
async function play(){if(!audioBuffer)return;try{await ctx.resume();if(offset>=result.duration)offset=0;stopSource();source=ctx.createBufferSource();source.buffer=audioBuffer;source.connect(gain);startedAt=ctx.currentTime;playing=true;source.onended=()=>{playing=false;offset=0;source=null;$('play').textContent='▶';$('play').setAttribute('aria-label','Play');};source.start(0,Math.min(offset,audioBuffer.duration-.001));$('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pause');}catch(e){pause();status(`Playback failed: ${e.message}`,true);}}
function seek(value){const resume=playing;pause();offset=Math.max(0,Math.min(result?.duration||0,Number(value)));updateWord(offset,true);if(resume)play();}
async function changeTrack(id){
  const sequence=++loadSequence; const resume=playing;pause();audioBuffer=null;$('play').disabled=true;
  selectedTrack=id;$('track').value=id;$('trackname').textContent=`Loading ${trackLabel(id)}…`;
  nodes.forEach(({n},key)=>{n.classList.toggle('solo',key===id);n.setAttribute('aria-pressed',String(key===id));});
  try{
    ctx ||= new (window.AudioContext||window.webkitAudioContext)();gain ||= ctx.createGain();gain.disconnect();gain.connect(ctx.destination);gain.gain.value=Number($('volume').value);
    const response=await fetch(`/api/jobs/${job}/${result.tracks[id]}`);if(!response.ok)throw new Error('Audio file unavailable');
    const decoded=await ctx.decodeAudioData(await response.arrayBuffer());if(sequence!==loadSequence)return;
    audioBuffer=decoded;$('play').disabled=false;$('stop').disabled=false;$('seek').disabled=false;
    $('trackname').textContent=trackLabel(id)+(id==='mix'?'':' · dry solo');
    $('download').href=`/api/jobs/${job}/${(result.downloads||result.tracks)[id]}`;
    if(resume)await play();
  }catch(e){if(sequence===loadSequence){$('trackname').textContent='Audio unavailable';status(`Could not load audio: ${e.message}`,true);}}
}
function setMode(next){drafts[mode]=$('text').value;mode=next;$('text').value=drafts[mode];document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));$('inputhint').textContent={score:'Editable .sera notation',english:'Rule-based translation · may approximate',gloss:'Separate sentences with //'}[mode];$('text').setAttribute('aria-label',`${mode} composition`);$('text').previousElementSibling.firstChild.textContent={score:'Your score ',english:'Your thought ',gloss:'Your gloss '}[mode];$('tenselabel').hidden=mode!=='gloss';for(const id of ['title','front','shuffle','move','strict'])$(id).disabled=mode==='score'||(id==='strict'&&mode!=='english');dirty=true;document.dispatchEvent(new Event('compositionchange'));}
function prayerAt(c,t=position()){return result?.prayerTimeline?.[c.id]?.find(span=>t>=span.start&&t<span.end);}
function language(word,c){if(!result.choir)return 'Disabled';const span=prayerAt(c);if(span)return `${span.tense} · ${span.cue}`;const langs=word?.languages||[];const value=langs.length?langs[c.prayer%langs.length]:null;return value?(languageNames[value]||value):'Prayer / tail';}
function short(s,n=23){return s.length>n?s.slice(0,n-1)+'…':s;}
function showInspector(){
  const word=result?.words[active],channel=channels.find(c=>c.id===inspected);const box=$('inspector');box.replaceChildren();
  const title=document.createElement('span');title.className='eyebrow';box.append(title);
  const body=document.createElement('p');box.append(body);
  if(!word){title.textContent='BETWEEN WORDS';body.textContent='Prayer voices and room decay may continue between spoken words.';return;}
  if(!channel){title.textContent=`WORD ${active+1} · FOUR SIMULTANEOUS MOUTHS`;body.textContent=speechChannels.map(c=>`${c.name}: ${word.mouths[c.key].gloss}`).join('  ·  ');return;}
  title.textContent=`${channel.name} · WORD ${active+1}`;
  if(channel.key){const m=word.mouths[channel.key];body.textContent=m.gloss+(m.moved?' · 4D moved: mouth closed; voice displaced':'');const raw=document.createElement('p');raw.className='raw';raw.textContent=m.text||'Hum / silent';box.append(raw);}
  else{const span=prayerAt(channel);body.textContent=span?`${languageNames[span.language]||span.language} · ${span.tense} · ${span.cue} sung contour. This label follows the audible tense schedule, including backmasked choirs. It is not a prayer syllable transcript.`:`${language(word,channel)} prayer · legacy language scheduling, without melodic tense cues.`;}
}
let editingIndex=-1, auditionSelection=null, editHistory=[];
for(const channel of speechChannels){
  const wrap=document.createElement('div');wrap.className='wordmouth';
  const label=document.createElement('label');label.textContent=channel.name;
  const input=document.createElement('textarea');input.id=`word-mouth-${channel.key}`;input.rows=2;input.spellcheck=false;label.append(input);
  const brightness=document.createElement('select');brightness.id=`word-brightness-${channel.key}`;brightness.setAttribute('aria-label',`${channel.name} vowel brightness`);
  for(const [value,name] of [['','Keep individual brightness'],['1','☀ Bright vowels'],['2','🔆 Extra-bright vowels'],['3','☢ Ionized vowels']]){const opt=document.createElement('option');opt.value=value;opt.textContent=name;brightness.append(opt);}
  wrap.append(label,brightness);$('word-mouth-fields').append(wrap);
}
function editCurrentWord(){
  const word=result?.words[active];if(!word){$('wordeditor').hidden=true;return;}
  $('wordeditor').hidden=false;
  if(editingIndex===active)return;
  editingIndex=active;$('word-tense').value=(word.tenses||[]).join('+');$('word-tone').value=Object.entries(word.tones||{}).map(([key,value])=>`${key}:${value}`).join(',');$('word-stammer').checked=word.stammer;
  $('word-temporal').textContent=word.temporal;
  for(const channel of speechChannels){$(`word-mouth-${channel.key}`).value=word.mouths[channel.key].notation;$(`word-brightness-${channel.key}`).value='';}
  $('word-edit-status').textContent='';
}
function renderBankReport(){
  const reports=result?.resolved?.sample_banks||{};
  $('bankreport').hidden=!Object.keys(reports).length;$('bankreport-list').replaceChildren();
  for(const [channel,report] of Object.entries(reports)){
    const entry=document.createElement('div');entry.className='bankcoverage';
    const title=document.createElement('strong');title.textContent=`${trackLabel(channel.startsWith('praise-')?channel:`mouth-${channel}`)} · ${report.name}`;
    const counts=report.counts||{};
    const detail=document.createElement('p');
    detail.textContent=`Sampled segments: ${Object.values(counts.sample||{}).reduce((a,b)=>a+b,0)}. Approximations: ${Object.keys(counts.approximation||{}).join(', ')||'none'}. Formant fallback: ${Object.keys(counts.formant||{}).join(', ')||'none'}.`;
    entry.append(title,detail);$('bankreport-list').append(entry);
  }
}
function renderGrammar(){
  $('grammarpanel').hidden=false;$('grammarview').replaceChildren();
  for(const [i,sentence] of (result.grammar||[]).entries()){
    const section=document.createElement('section');section.className='grammarclause';
    const heading=document.createElement('h3');heading.textContent=`Sentence ${i+1}`;
    const terms=document.createElement('p');terms.textContent=sentence.terms.join(' → ');
    const order=document.createElement('small');order.textContent=`Tree order: ${sentence.chain.map(n=>`word ${n}`).join(' → ')}`;
    section.append(heading,terms,order);
    for(const temporal of sentence.temporal){const row=document.createElement('p');row.className='controlhelp';row.textContent=`Word ${temporal.spoken}: ${temporal.tenses.join(' + ')||'unspecified'}`;section.append(row);}
    for(const issue of sentence.problems){const row=document.createElement('p');row.className='grammarissue';row.textContent=issue;section.append(row);}
    $('grammarview').append(section);
  }
}
async function applyWord(audition=false){
  if(busy||active<0||!result)return;
  if(dirty){$('word-edit-status').textContent='Render the changed composition first, then edit its words.';return;}
  pause();const word=result.words[active];const source=result.source;
  const mouths={},brightness={};for(const channel of speechChannels){mouths[channel.key]=$(`word-mouth-${channel.key}`).value;const v=$(`word-brightness-${channel.key}`).value;if(v)brightness[channel.key]=Number(v);}
  const edit={tense:$('word-tense').value,tone:$('word-tone').value,stammer:$('word-stammer').checked,mouths,brightness};
  $('apply-word').disabled=$('audition-word').disabled=true;
  try{
    const response=await api('/api/edit-word',{mode:'score',text:source,index:word.source_index,edit,seed:$('seed').value,dialect:scoreOverride('dialect'),heresy:$('heresy').checked});
    editHistory.push(source);$('undo-word').disabled=false;setMode('score');$('text').value=response.text;drafts.score=response.text;dirty=false;
    auditionSelection=audition?word.source_index:null;$('render').click();
  }catch(e){$('word-edit-status').textContent=e.message;}
  finally{$('apply-word').disabled=$('audition-word').disabled=false;}
}
$('wordeditor').addEventListener('toggle',()=>{if($('wordeditor').open&&playing)pause();});
$('apply-word').onclick=()=>applyWord(false);$('audition-word').onclick=()=>applyWord(true);
$('undo-word').onclick=()=>{if(busy||!editHistory.length)return;setMode('score');$('text').value=editHistory.pop();drafts.score=$('text').value;$('undo-word').disabled=!editHistory.length;auditionSelection=null;$('render').click();};
const displayMotion = new WeakMap();
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
function displayText(element, text, distance=5){
  const previous=element.querySelector('.display-current')?.textContent??element.textContent;
  if(previous===text)return;
  displayMotion.get(element)?.cancel();
  if(reduceMotion.matches){element.textContent=text;return;}
  const timing={duration:240,easing:'cubic-bezier(.2, 0, 0, 1)'};
  if(element.namespaceURI===NS){
    element.textContent=text;
    displayMotion.set(element,element.animate(
      [{opacity:.45,translate:`0 ${distance}px`},{opacity:1,translate:'0 0'}],timing));
    return;
  }
  const current=document.createElement('span');
  current.className='display-current';
  current.textContent=text;
  const outgoing=document.createElement('span');
  outgoing.className='display-outgoing';
  outgoing.setAttribute('aria-hidden','true');
  outgoing.textContent=previous;
  element.replaceChildren(current,outgoing);
  const motion=outgoing.animate(
    [{opacity:1,translate:'0 0'},{opacity:0,translate:`0 -${distance}px`}],timing);
  motion.onfinish=()=>outgoing.remove();
  displayMotion.set(element,motion);
  current.animate([{opacity:0,translate:`0 ${distance}px`},{opacity:1,translate:'0 0'}],timing);
}
function updateWord(t,force=false){
  if(!result)return;
  const index=result.words.findIndex((word,i,words)=>
    t>=word.start&&t<(words[i+1]?.start??word.end));
  if(index===active&&!force)return;active=index;const word=result.words[index];
  displayText($('nowword'),word?(result.selection!==null?`Word ${word.source_index+1} · isolated audition`:`Word ${index+1} of ${result.words.length}`):(t<result.words[0].start?'Before the first word.':'The voices linger.'));
  displayText($('nowdetail'),word?speechChannels.map(c=>word.mouths[c.key].gloss).join(' · '):'Prayer, breath and the shape of the room.');
  document.querySelectorAll('.wordcard').forEach((b,i)=>{b.classList.toggle('active',i===index);b.setAttribute('aria-pressed',String(i===index));});
  channels.forEach(c=>{
    const label=c.key?(word?.mouths[c.key].gloss||'—'):language(word,c);
    displayText(nodes.get(c.id).gloss,short(label),3);
  });showInspector();editCurrentWord();
}
function vowelLevel(timeline,t){
  if(!timeline?.length)return 0;
  // Find the last vowel that has started, even after a seek or track change.
  let lo=0, hi=timeline.length;
  while(lo<hi){
    const mid=Math.floor((lo+hi)/2);
    if(timeline[mid][0]<=t)lo=mid+1;
    else hi=mid;
  }
  const span=timeline[lo-1];
  return span && t<span[1] ? span[2] : 0;
}
function frame(){
  const t=position();$('clock').textContent=time(t);if(!$('seek').matches(':active'))$('seek').value=t;
  $('angel').closest('.angelstage').classList.toggle('playing', playing);
  $('seek').style.setProperty('--played',`${result ? t/result.duration*100 : 0}%`);
  updateWord(t);
  for(const channel of channels.filter(c=>c.prayer!==undefined)){
    if(!result)break;
    const label=short(language(result.words[active],channel));
    if(nodes.get(channel.id).gloss.textContent!==label){displayText(nodes.get(channel.id).gloss,label,3);if(inspected===channel.id)showInspector();}
  }
  for(const c of channels){
    const {n,halo,opening}=nodes.get(c.id);
    const audible=selectedTrack==='mix'||selectedTrack===c.id;
    const samples=result?.activity[c.id];
    const frame=t*20, index=Math.floor(frame), fraction=frame-index;
    const activity=(samples?.[index]||0)*(1-fraction)+(samples?.[index+1]||0)*fraction;
    const amp=(playing?activity:0)*(audible?1:.15);
    halo.style.opacity=String(amp*.26);
    halo.setAttribute('r',String(29+amp*11));
    opening.setAttribute('ry',String(1.4+amp*5));
    if(c.key){
      const level=playing&&audible?vowelLevel(result?.vowelBrightness?.[c.id],t):0;
      if(Number(n.dataset.brightness||0)!==level)n.dataset.brightness=level;
    }
  }
  requestAnimationFrame(frame);
}
function renderWords(){
  $('wordlist').replaceChildren();result.words.forEach((word,i)=>{
    const card=document.createElement('button');card.className='wordcard';card.setAttribute('aria-label',`Word ${i+1}, seek to ${word.start.toFixed(1)} seconds`);
    const num=document.createElement('span');num.className='wordnumber';num.textContent=String(i+1).padStart(2,'0');
    const glyph=document.createElement('span');glyph.className='wordglyph';glyph.dir='rtl';glyph.textContent=word.glyphs||'Ø';
    const gloss=document.createElement('span');gloss.className='wordgloss';
    speechChannels.forEach(c=>{const s=document.createElement('span');const label=document.createElement('b');label.textContent=`${c.key} `;s.append(label,word.mouths[c.key].gloss);gloss.append(s);});
    const stamp=document.createElement('span');stamp.className='wordtime';stamp.textContent=`${word.start.toFixed(1)}s`;gloss.append(stamp);card.append(num,glyph,gloss);card.onclick=()=>seek(word.start+.001);$('wordlist').append(card);
  });$('empty').hidden=true;$('wordcount').textContent=`${result.words.length} words`;
}
function setBusy(value){busy=value;$('render').disabled=value;$('cancel').hidden=!value;$('status').classList.toggle('busy',value);document.dispatchEvent(new Event('renderstatechange'));}
async function api(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Seraphim-Token':token},body:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw new Error(value.error||`Request failed (${r.status})`);return value;}
async function poll(id){
  try{const r=await fetch(`/api/jobs/${id}/status`);if(!r.ok)throw new Error('Could not read render status');const state=await r.json();if(job!==id)return;
    if(state.state==='running'){status(state.message);setTimeout(()=>poll(id),700);return;}
    setBusy(false);status(state.message,state.state==='error');
    if(state.state==='done'){
      pause();offset=0;result=state.result;active=-2;selectedTrack='mix';inspected=null;editingIndex=-1;
      updateSpeaker();
      $('prayer-key').hidden=!result.choir||!result.prayer_time;$('dialectbadge').textContent=result.dialect;$('duration').textContent=time(result.duration);$('seek').max=result.duration;
      $('track').replaceChildren();for(const key of Object.keys(result.tracks)){const opt=document.createElement('option');opt.value=key;opt.textContent=trackLabel(key);$('track').append(opt);}$('track').disabled=false;
      $('download').hidden=false;$('savescore').hidden=false;$('savescore').href=`/api/jobs/${id}/score.sera`;
      $('savebundle').hidden=false;$('savebundle').href=`/api/jobs/${id}/bundle.zip`;
      $('offlinepreview').hidden=!result.preview;$('offlinepreview').href=`/api/jobs/${id}/preview.html`;
      $('resolvedpanel').hidden=false;$('resolved').textContent=JSON.stringify(result.resolved,null,2);$('saveplan').href=`/api/jobs/${id}/plan.json`;
      $('readingpanel').hidden=false;$('reading').textContent=result.reading||'No read-back available.';$('diagnostics').textContent=result.diagnostics.length?JSON.stringify(result.diagnostics,null,2):'No phonological issues reported.';
      renderWords();renderGrammar();renderBankReport();updateWord(0,true);await changeTrack('mix');status(result.selection!==null?'Word audition ready. The score download retains the full composition.':dirty?'Ready to listen. Editor changes apply on the next render.':'Ready to listen. Click a word to seek, or a mouth to solo.');
    }
  }catch(e){setBusy(false);status(e.message,true);}
}
$('render').onclick=async()=>{
  if(busy)return;
  const invalid=document.querySelector('.editor input:invalid');
  if(invalid){
    for(let details=invalid.closest('details');details;details=details.parentElement.closest('details'))details.open=true;
    invalid.reportValidity();
    status(invalid.validationMessage,true);
    return;
  }
  if(!$('text').value.trim()){status('Enter some text or choose an example first.',true);$('text').focus();return;}
  try{setBusy(true);status('Starting synthesis…');const payload={mode,text:$('text').value,dialect:mode==='score'?scoreOverride('dialect'):$('dialect').value,room:scoreOverride('room'),seed:$('seed').value,tense:$('tense').value,choir:$('choir').checked,reverb:scoreOverride('reverb')};for(const key of ['voice','tempo'])if(touched.has(key))payload[key]=scoreOverride(key);Object.assign(payload,extraSettings());if(mode!=='score')payload.dictionary=dictionaryOverrides;if(auditionSelection!==null){payload.selection=auditionSelection;auditionSelection=null;}
    pause();++loadSequence;audioBuffer=null;result=null;active=-1;$('play').disabled=true;$('stop').disabled=true;$('seek').disabled=true;$('track').disabled=true;$('download').hidden=true;$('savescore').hidden=true;$('savebundle').hidden=true;$('offlinepreview').hidden=true;$('resolvedpanel').hidden=true;
    const response=await api('/api/render',payload);job=response.job;dirty=false;poll(job);
  }catch(e){setBusy(false);status(e.message,true);}
};
$('cancel').onclick=async()=>{try{await api('/api/cancel',{});}catch(e){status(e.message,true);}};
$('play').onclick=()=>playing?pause():play();$('stop').onclick=()=>seek(0);$('seek').oninput=e=>seek(e.target.value);$('track').onchange=e=>changeTrack(e.target.value);$('volume').oninput=()=>{if(gain)gain.gain.value=Number($('volume').value);};
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
for(const key of ['voice','tempo'])$(key).oninput=()=>{touched.add(key);dirty=true;$(`${key}-value`).textContent=key==='voice'?`${Number($(key).value)>0?'+':''}${Number($(key).value).toFixed(2)}`:`${Number($(key).value).toFixed(2)}×`;};
$('text').oninput=()=>dirty=true;
$('dialect').addEventListener('change',updateSpeaker);
for(const id of ['dialect','room','seed','tense','choir','reverb'])$(id).addEventListener('change',()=>{dirty=true;});
function resetSettings(){
  resetExtraSettings();loadedControls.clear();touched.clear();
  for(const [id,min,max,value] of [['voice',-1,1,0],['tempo',.25,3,1]]){
    const input=$(id);input.min=min;input.max=max;input.step=.05;input.value=value;
    $(`${id}-value`).textContent='From score';
  }
  $('dialect').value=$('room').value=$('reverb').value='';
  $('seed').value=0;$('choir').checked=true;dirty=true;updateSpeaker();
}
$('reset').onclick=resetSettings;
async function example(name){
  if(!name)return;
  const sequence=++scoreLoad;
  try{
    const response=await fetch(`/api/example/${encodeURIComponent(name)}`);
    if(!response.ok)throw new Error('Example unavailable');
    const text=await response.text();
    if(sequence===scoreLoad)await loadScore(text,sequence,'Example loaded. Shape its sound, then render.');
  }catch(e){if(sequence===scoreLoad)status(e.message,true);}
}
$('example').onchange=e=>example(e.target.value);
$('open').onclick=()=>$('file').click();
$('file').onchange=async()=>{
  const f=$('file').files[0];if(!f)return;
  $('file').value='';
  if(f.size>262144){status('Please choose a file under 256 KB.',true);return;}
  const sequence=++scoreLoad;
  try{
    const text=await f.text();
    if(sequence!==scoreLoad)return;
    const message=`${f.name} loaded. Render when ready.`;
    if(f.name.toLowerCase().endsWith('.sera'))await loadScore(text,sequence,message);
    else{setMode('english');$('text').value=text;dirty=true;status(message);document.dispatchEvent(new Event('compositionchange'));}
  }catch(e){if(sequence===scoreLoad)status(e.message,true);}
};
$('theme').onclick=()=>{document.body.classList.toggle('light');try{localStorage.setItem('seraphim-theme',document.body.classList.contains('light')?'light':'dark');}catch{}};
try{if(localStorage.getItem('seraphim-theme')==='light')document.body.classList.add('light');}catch{}
(async()=>{try{const r=await fetch('/api/session');if(!r.ok)throw new Error('Local server unavailable');token=(await r.json()).token;const controls=await fetch('/api/controls');if(!controls.ok)throw new Error('Control definitions unavailable; restart the server.');createSynthControls(await controls.json());const response=await fetch('/api/examples');const examples=await response.json();examples.forEach(name=>{const opt=document.createElement('option');opt.value=name;opt.textContent=name.replace('.sera','').replaceAll('_',' ');$('example').append(opt);});const first=examples.includes('kadosh.sera')?'kadosh.sera':examples[0];if(!window.restoreStudioDraft?.()&&first){$('example').value=first;await example(first);}dirty=false;document.dispatchEvent(new Event('studioready'));}catch(e){status(`Could not connect: ${e.message}`,true);$('render').disabled=true;}})();
requestAnimationFrame(frame);
