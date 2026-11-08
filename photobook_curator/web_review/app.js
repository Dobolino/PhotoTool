/* PhotoTool's local review workspace. Photo decisions are persisted by Python. */
'use strict';

const BASE = new URL('./', location.href);
const icons = {
  photo:'<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-6-6L4 20"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  check:'<path d="m5 12 4 4L19 6"/>', plus:'<path d="M12 5v14M5 12h14"/>', minus:'<path d="M5 12h14"/>',
  left:'<path d="m14 6-6 6 6 6"/>', right:'<path d="m10 6 6 6-6 6"/>',
  undo:'<path d="M3 10h11a7 7 0 0 1 0 14"/><path d="m7 6-4 4 4 4"/>',
  export:'<path d="M12 15V3m-4 4 4-4 4 4M5 14v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6"/>',
  moon:'<path d="M20.9 13.1A9 9 0 0 1 10.9 3.1a9 9 0 1 0 10 10Z"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  swap:'<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>', close:'<path d="m6 6 12 12M6 18 18 6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.photo}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const $ = id => document.getElementById(id);
const nfmt = value => new Intl.NumberFormat('de-CH').format(value || 0);
const shortName = value => String(value || '').replace(/\.[^.]+$/, '').slice(-20);
const button = (action, label, klass='secondary', attrs='') => `<button class="${klass}" data-action="${action}" ${attrs}>${label}</button>`;
const photoURL = (id, edge=160) => new URL(`image/${Number(id)}?edge=${edge}&v=${Number(state?.image_revision || 0)}`, BASE).href;

let state = null, view = null, photoMap = new Map(), modal = null;
let queue = Promise.resolve(), pending = 0, viewTimer, toastTimer, lastFocusElement, closePromise;
let galleryPage = 0, galleryKey = '', lastRevision = -1, lastNotice = '';
let stripSpecs = new Map(), stripPositions = new Map(), stripJobs = new Map();
const STRIDE = 116, MAX_STRIP_IMAGES = 70, GALLERY_PAGE = 60;

function currentPhoto(){ return view?.focus==null?null:photoMap.get(Number(view.focus)) || null; }
function albumPhotos(){ return (state?.kept || []).map(id=>photoMap.get(id)).filter(Boolean); }
function scoped(){ return (state?.photos || []).filter(p=>view.chapter==='all' || p.chapter===view.chapter); }
function scopedAlbum(){ return albumPhotos().filter(p=>view.chapter==='all' || p.chapter===view.chapter); }
function alternativeIds(){ return new Set(view?.alternative_ids || []); }
function pool(){
  const ids = alternativeIds();
  return scoped().filter(p=>view.filter==='all' || (view.filter==='album' ? p.selected : ids.has(p.id)));
}
function guarded(photo){ return photo && (photo.favorite || photo.manual_decision==='keep'); }
function mutationDisabled(){ return pending > 0 || Boolean(state?.busy); }
function canAdd(photo){ return photo && !photo.selected && (photo.manual_decision!=='reject' || photo.favorite); }
function validFocus(){
  const scope=scoped(), visible=pool(), album=scopedAlbum();
  if(!scope.some(p=>p.id===view.focus)) view.focus=visible[0]?.id ?? scope[0]?.id ?? null;
  if(!album.some(p=>p.id===view.anchor)) view.anchor=album[0]?.id ?? null;
}
function applySnapshot(next, initial=false){
  if(!next || !Array.isArray(next.photos)) return;
  state=next; photoMap=new Map(state.photos.map(p=>[p.id,p]));
  if(initial || !view){
    view={layout:'A',filter:'all',chapter:'all',focus:state.photos[0]?.id??null,anchor:state.kept[0]??null,theme:'dark',export_layout:'flat',alternative_ids:[],...(state.view||{})};
    if(!Array.isArray(view.alternative_ids)) view.alternative_ids=state.photos.filter(p=>!p.selected).map(p=>p.id);
  } else if(next.view?.chapter===view.chapter && Array.isArray(next.view.alternative_ids)) {
    view.alternative_ids=next.view.alternative_ids;
  }
  validFocus(); lastRevision=state.revision;
  document.body.classList.toggle('dark', view.theme==='dark');
}
async function request(payload){
  const response=await fetch(new URL('api/action', BASE), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),credentials:'same-origin',cache:'no-store'});
  let data;
  try { data=await response.json(); } catch { throw new Error('Die lokale Anwendung hat keine gültige Antwort geliefert.'); }
  if(!response.ok){ if(data.state) applySnapshot(data.state); throw new Error(data.error || 'Die Änderung konnte nicht gespeichert werden.'); }
  return data;
}
function transact(payload, options={}){
  pending++; updateSavedStatus();
  const run=queue.then(async()=>{
    const result=await request({...payload,expected_revision:state.revision});
    if(result.state) applySnapshot(result.state); else if(Array.isArray(result.photos)) applySnapshot(result);
    options.after?.(result);
    return result;
  });
  queue=run.catch(()=>{});
  return run.catch(error=>{ showError(error.message); throw error; }).finally(()=>{
    pending--; if(state) render(); updateSavedStatus();
  });
}
function launch(payload, options={}){ return transact(payload,options).catch(()=>{}); }
function persistView(immediate=false){
  clearTimeout(viewTimer);
  const save=()=>{ viewTimer=null;const copy={...view,alternative_ids:[...(view.alternative_ids||[])]}; launch({action:'view',view:copy}); };
  if(immediate) save(); else viewTimer=setTimeout(save,350);
}
function showError(message){
  lastNotice=message; $('notice').hidden=false; $('notice').textContent=message;
  if(modal) modal.error=message;
}
function flushPendingView(){
  if(viewTimer){clearTimeout(viewTimer);viewTimer=null;launch({action:'view',view:{...view,alternative_ids:[...(view.alternative_ids||[])]}});}
}
function closeReview(){
  if(closePromise)return closePromise;
  clearTimeout(viewTimer);viewTimer=null;
  closePromise=(async()=>{
    // A queued replacement can update its anchor; capture navigation after it finishes.
    await queue;
    clearTimeout(viewTimer);viewTimer=null;
    await transact({action:'view',view:{...view,alternative_ids:[...(view.alternative_ids||[])]}});
    return transact({action:'close'});
  })().catch(error=>{closePromise=null;throw error;});
  return closePromise;
}
function toast(message, undo=true){
  const host=$('toast'); host.innerHTML=`<span>${esc(message)}</span>${undo&&state?.can_undo&&!state.busy?button('undo','Rückgängig','quiet','data-mutates'):''}`;
  host.classList.add('visible'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>host.classList.remove('visible'),4500);
}
function updateSavedStatus(){
  if(!$('savedStatus')) return;
  $('savedStatus').innerHTML=icon(pending||state?.busy?'info':'check')+esc(state?.busy?'Vorgang läuft …':pending?'Wird gespeichert …':'Zwischenstand gespeichert');
  document.querySelectorAll('[data-mutates]').forEach(el=>{el.disabled=mutationDisabled() || el.dataset.locked==='true';});
}
function choose(id, role='focus'){
  if(!photoMap.has(Number(id)))return;
  if(role==='album'){
    view.anchor=Number(id);
    view.focus=scoped().find(p=>alternativeIds().has(p.id) && p.id!==Number(id))?.id ?? Number(id);
  } else view.focus=Number(id);
  render(); persistView(); revealFocus();
}
function setLayout(layout){
  view.layout=layout;
  if(layout==='B' && currentPhoto()?.selected){ view.anchor=view.focus; view.focus=scoped().find(p=>!p.selected)?.id ?? view.focus; }
  render();persistView();revealFocus();
}
function setFilter(filter){
  view.filter=filter;
  if(!pool().some(p=>p.id===view.focus))view.focus=pool()[0]?.id??view.focus;
  render();persistView();revealFocus();
}
function setChapter(chapter){
  view.chapter=chapter; view.filter='all';
  view.alternative_ids=scoped().filter(p=>!p.selected).map(p=>p.id);
  view.anchor=scopedAlbum()[0]?.id??null;
  view.focus=(view.layout==='B'?scoped().find(p=>!p.selected):null)?.id??scoped()[0]?.id??null; galleryPage=0;
  render();persistView(true);revealFocus();
}
function move(delta){
  const visible=pool();if(!visible.length)return;
  const pos=visible.findIndex(p=>p.id===view.focus);choose(visible[Math.max(0,Math.min(visible.length-1,(pos<0?0:pos)+delta))].id);
}
function toggle(id=Number(view.focus)){
  const photo=photoMap.get(Number(id));if(!photo || mutationDisabled())return;
  if(photo.selected && guarded(photo)){showError('Dieses Foto ist geschützt. Hebe zuerst den Favoritenschutz oder „Dauerhaft behalten“ auf.');return;}
  if(!photo.selected && !canAdd(photo)){showError('Dieses Foto wurde dauerhaft abgelehnt. Hebe die Vorgabe unter „Entscheidung“ auf.');return;}
  flushPendingView();
  launch({action:'toggle',id:photo.id,selected:!photo.selected},{after:()=>toast(photo.selected?'Aus dem Album entfernt. Das Foto bleibt sichtbar.':'Ins Album aufgenommen. Die Miniatur ist jetzt farbig.')});
}
function addCurrent(){ if(currentPhoto() && !currentPhoto().selected) toggle(); }
function replaceCurrent(){
  const candidate=currentPhoto(), anchor=photoMap.get(Number(view.anchor));
  if(!candidate || !anchor || candidate.selected || guarded(anchor) || mutationDisabled())return;
  flushPendingView();
  launch({action:'replace',anchor:anchor.id,id:candidate.id},{after:()=>{view.anchor=candidate.id;toast('Am gleichen Albumplatz ersetzt. Rückgängig stellt beide Fotos wieder her.');persistView();}});
}

function thumb(photo, role='focus', absoluteIndex=null){
  const selected=photo.selected, focused=(role==='album'?view.anchor:view.focus)===photo.id;
  const mark=photo.favorite?'★':photo.manual_decision==='keep'?'Geschützt':photo.manual_decision==='reject'?'Abgelehnt':'';
  return `<div class="thumb ${selected?'selected':''} ${focused?'focused':''} ${photo.manual_decision==='reject'?'rejected':''}" data-id="${photo.id}" data-role="${role}" tabindex="0" role="button" aria-label="${esc(photo.filename)}, ${selected?'im Album':'nicht im Album'}"${absoluteIndex!==null?` style="position:absolute;left:${absoluteIndex*STRIDE}px;top:2px"`:''}><img data-photo-id="${photo.id}" src="${photoURL(photo.id)}" alt="${esc(photo.filename)}" decoding="async" loading="lazy"><button class="thumb-check" data-action="toggle" data-id="${photo.id}" data-mutates aria-label="${selected?'Aus dem Album entfernen':'Ins Album aufnehmen'}: ${esc(photo.filename)}" aria-pressed="${selected}">${selected?icon('check'):''}</button><div class="thumb-label"><span>${esc(shortName(photo.filename))}</span><span>${esc(mark || (selected?'✓':''))}</span></div></div>`;
}
function strip(photos, key, role='focus'){
  stripSpecs.set(key,{ids:photos.map(p=>p.id),role});
  return `<div class="filmstrip virtual-strip" data-strip-key="${key}" tabindex="0" aria-label="${role==='album'?'Albumfotos':'Fotoleiste'}"><div class="filmstrip-inner" style="width:${Math.max(1,photos.length*STRIDE)}px"></div></div>`;
}
function mountStrips(){
  document.querySelectorAll('.virtual-strip').forEach(el=>{
    el.scrollLeft=stripPositions.get(el.dataset.stripKey)||0;
    drawStrip(el);
  });
}
function drawStrip(el){
  const spec=stripSpecs.get(el.dataset.stripKey);if(!spec)return;
  const start=Math.max(0,Math.floor(el.scrollLeft/STRIDE)-2);
  const count=Math.min(MAX_STRIP_IMAGES,Math.ceil(el.clientWidth/STRIDE)+5);
  el.firstElementChild.innerHTML=spec.ids.slice(start,start+count).map((id,i)=>thumb(photoMap.get(id),spec.role,start+i)).join('');
}
function revealFocus(){
  for(const el of document.querySelectorAll('.virtual-strip')){
    const spec=stripSpecs.get(el.dataset.stripKey), index=spec?.ids.indexOf(spec.role==='album'?view.anchor:view.focus);
    if(index===undefined || index<0)continue;
    const left=index*STRIDE, right=left+106;
    if(left<el.scrollLeft || right>el.scrollLeft+el.clientWidth){
      el.scrollLeft=Math.max(0,left-(el.clientWidth-106)/2);stripPositions.set(el.dataset.stripKey,el.scrollLeft);drawStrip(el);
    }
  }
}
function navigation(){
  const list=pool(), pos=list.findIndex(p=>p.id===view.focus);
  return `<div class="stage-nav">${button('prev',icon('left'),'','aria-label="Voriges Foto" '+(pos<=0?'disabled':''))}<span>${list.length?nfmt(pos+1):'0'} / ${nfmt(list.length)}</span>${button('next',icon('right'),'','aria-label="Nächstes Foto" '+(pos<0||pos===list.length-1?'disabled':''))}</div>`;
}
function locationReviewControl(photo){
  if(!photo.location_review_required)return '';
  const reasons={description_conflict:'Motivbeschreibung und gespeicherter Ort nennen unterschiedliche Städte. Auch die Beschreibung kann falsch sein. GPS und Aufnahmezeiten prüfen.',location_warning:'Die gespeicherte Ortsgrundlage ist ungeklärt oder widersprüchlich. Vorschläge vor dem Speichern prüfen.',legacy_unverified:'Gespeicherte Ortsangabe ohne nachvollziehbaren Nachweis. Die Ortsprüfung benötigt keine neue KI-Bewertung.'};
  return button('location-open',icon('info')+'Zuordnung prüfen','secondary location-review',`title="${esc(reasons[photo.location_review_reason] || reasons.location_warning)}" aria-label="Ortszuordnung prüfen: ${esc(photo.filename)}"`);
}
function info(photo){
  const selected=photo.selected, rule=photo.favorite?'Favorit geschützt':photo.manual_decision==='keep'?'Dauerhaft behalten':photo.manual_decision==='reject'?'Dauerhaft abgelehnt':'';
  return `<aside class="info"><div><div class="eyebrow">${esc(photo.region || photo.chapter || 'Ohne Ortszuordnung')} · ${esc(photo.date || 'Datum fehlt')}</div>${photo.landmark?'<span class="description-label">Motivbeschreibung</span>':''}<h2 title="${esc(photo.landmark || photo.filename)}">${esc(photo.landmark || photo.filename)}</h2><span class="filename">${esc(photo.filename)}</span></div><span class="state-pill ${selected?'':'unselected'}">${icon(selected?'check':'plus')}${selected?'Im Album':'Nicht im Album'}</span>${locationReviewControl(photo)}${rule?`<span class="protection-note">${esc(rule)}</span>`:''}<div class="facts"><div><span>Aufnahme</span><strong>${esc(photo.time || 'Unbekannt')}</strong></div><div><span>Ortsgrundlage</span><strong>${esc(sourceLabel(photo.location_source))}</strong></div>${photo.location_warning?`<div class="location-hint">${esc(warningLabel(photo.location_warning))}</div>`:''}<div><span>Bildgröße</span><strong>${photo.width&&photo.height?`${photo.width} × ${photo.height}`:'Unbekannt'}</strong></div><div><span>Technischer Score</span><strong>${Number.isFinite(photo.technical_score)?Number(photo.technical_score).toFixed(0):'–'}</strong></div><div><span>Verwendung</span><strong>Originaldatei</strong></div></div><div class="info-buttons">${button('toggle',icon(selected?'minus':'plus')+(selected?'Aus Album entfernen':'Ins Album aufnehmen'),selected?'secondary':'primary',`data-id="${photo.id}" data-mutates data-locked="${selected?guarded(photo):!canAdd(photo)}"`)}${button('why',icon('info')+'Warum dieses Bild?','secondary',`data-id="${photo.id}"`)}<div class="detail-actions">${button('favorite',icon('star'),photo.favorite?'secondary favorite-active':'secondary',`data-id="${photo.id}" data-mutates aria-label="Favoritenschutz ${photo.favorite?'aufheben':'aktivieren'}" title="Favoritenschutz"`)}${button('decision','Entscheidung','secondary',`data-id="${photo.id}"`)}${button('tools',icon('more'),'secondary','aria-label="Weitere Werkzeuge"')}</div></div></aside>`;
}
function stageImage(photo, caption=true){
  return `<img class="large-image" data-photo-id="${photo.id}" src="${photoURL(photo.id,1600)}" alt="${esc(photo.filename)}" decoding="async">${caption?`<div class="stage-caption">${esc(photo.region || photo.chapter || 'Ohne Kapitel')} · ${esc(photo.date || 'Datum fehlt')}</div>`:''}`;
}
function viewer(){ const p=currentPhoto(); return p?`<section class="viewer"><div class="stage">${stageImage(p)}${navigation()}</div>${info(p)}</section>`:'<div class="loading-state">In dieser Reise sind noch keine Fotos vorhanden.</div>'; }
function filterButtons(){
  const list=scoped(), alt=alternativeIds(), counts={all:list.length,album:list.filter(p=>p.selected).length,alternatives:list.filter(p=>alt.has(p.id)).length};
  return `<div class="small-segment" aria-label="Bildfilter">${[['all','Alle'],['album','Im Album'],['alternatives','Alternativen']].map(([value,label])=>`<button data-filter="${value}" class="${view.filter===value?'active':''}">${label} <span>${nfmt(counts[value])}</span></button>`).join('')}</div>`;
}
function filmstrip(){return `<section class="strip-card"><div class="strip-head">${filterButtons()}<div class="legend"><span><i class="dot"></i>Im Album</span><span><i class="dot gray"></i>Nicht im Album</span></div></div>${pool().length?strip(pool(),'all'):'<div class="empty-lane">Keine Fotos für diesen Filter. Wähle „Alle“, um auch abgewählte Fotos zu sehen.</div>'}</section>`;}
function relation(anchor,candidate){
  if(anchor.id===candidate.id)return 'Aktuelles Albumfoto';
  if(anchor.burst_group_id!==null && anchor.burst_group_id!==undefined && candidate.burst_group_id===anchor.burst_group_id)return 'Gleiche Serie';
  if(anchor.content_cluster_id!==null && anchor.content_cluster_id!==undefined && candidate.content_cluster_id===anchor.content_cluster_id)return 'Visuelle Gruppe';
  return 'Weitere Aufnahme · keine belegte Bildähnlichkeit';
}
function pair(){
  const album=scopedAlbum(), anchor=album.find(p=>p.id===view.anchor), candidate=currentPhoto();
  if(!candidate)return `<div class="empty-workspace"><h2>Keine Fotos in diesem Kapitel</h2></div>${filmstrip()}`;
  const albumCard=anchor?`<div class="pair-title">Dein Albumfoto<small>${guarded(anchor)?'Geschützt':`Platz ${nfmt(albumPhotos().findIndex(p=>p.id===anchor.id)+1)} im Album`}</small></div><div class="stage">${stageImage(anchor,false)}</div><div class="pair-caption"><span>${esc(anchor.filename)}</span><span class="saved">✓ Im Album</span></div>`:`<div class="pair-title">Dein Albumfoto<small>Dieses Kapitel</small></div><div class="stage empty-anchor"><div><h2>Noch kein Foto im Album</h2><p>Nimm rechts ein Foto aus diesem Kapitel auf.</p></div></div><div class="pair-caption"><span>Deine übrige Auswahl bleibt erhalten.</span></div>`;
  return `<div class="pair-view"><section class="pair-card" data-pair-role="album">${albumCard}</section><section class="pair-card" data-pair-role="candidate"><div class="pair-title">${candidate.selected?'Aufgenommenes Foto':'Weitere Aufnahme'}<small>${anchor?esc(relation(anchor,candidate)):'Ein erster Vorschlag für dieses Kapitel'}</small></div><div class="stage">${stageImage(candidate,false)}</div><div class="pair-caption"><span>${esc(candidate.filename)}</span><span>${candidate.selected?'✓ Im Album':'Nicht im Album'}</span></div></section></div><div class="action-bar"><div>${button('add',icon('plus')+(anchor?'Zusätzlich aufnehmen':'Ins Album aufnehmen'),'primary',`data-mutates data-locked="${!canAdd(candidate)}"`)}${button('replace',icon('swap')+'Als Ersatz wählen','secondary',`data-mutates data-locked="${!anchor || candidate.selected || guarded(anchor) || candidate.id===anchor?.id || !canAdd(candidate)}"`)}</div><div>${button('why',icon('info')+'Warum dieses Bild?','quiet',`data-id="${candidate.id}"`)}${button('undo',icon('undo')+'Rückgängig','quiet',`data-mutates data-locked="${!state.can_undo}"`)}</div></div><div class="lanes"><section class="lane"><div class="lane-label"><strong>Im Album</strong><span>${nfmt(album.length)} ${view.chapter==='all'?'auf der ganzen Reise':'in diesem Kapitel'} ausgewählt</span></div>${album.length?strip(album,'album','album'):'<span class="empty-lane">Noch keine Bilder aus diesem Kapitel ausgewählt.</span>'}</section><section class="lane"><div class="lane-label"><strong>Alternativen</strong><span>Bleiben zum Vergleichen sichtbar</span></div>${strip(scoped().filter(p=>alternativeIds().has(p.id)),'alternatives')}</section></div>`;
}
function contacts(){
  const list=pool(), key=view.chapter+'|'+view.filter;
  if(key!==galleryKey){galleryKey=key;galleryPage=0;}
  const pages=Math.max(1,Math.ceil(list.length/GALLERY_PAGE));galleryPage=Math.min(galleryPage,pages-1);
  const slice=list.slice(galleryPage*GALLERY_PAGE,(galleryPage+1)*GALLERY_PAGE), groups=new Map();
  slice.forEach(p=>{const key=p.chapter || 'Ohne Kapitel';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p);});
  return `<section class="strip-card gallery-toolbar"><div class="strip-head">${filterButtons()}<span class="layout-note">Häkchen ändern die Auswahl</span></div></section><div class="contact-layout"><section class="contact-sheet" data-gallery-key="${esc(key)}" data-gallery-page="${galleryPage}">${[...groups].map(([name,items])=>`<div class="chapter-heading"><h3>${esc(state.chapters.find(ch=>ch.id===name)?.name || name)}</h3><span>${nfmt(state.chapters.find(ch=>ch.id===name)?.selected ?? items.filter(p=>p.selected).length)} im Album · ${nfmt(state.chapters.find(ch=>ch.id===name)?.total ?? items.length)} Fotos im Kapitel</span></div><div class="contact-grid">${items.map(p=>thumb(p)).join('')}</div>`).join('')||'<div class="empty-lane">Keine Fotos für diesen Filter.</div>'}<div class="gallery-paging">${button('gallery-prev','‹ Zurück','secondary',galleryPage===0?'disabled':'')}<span>${nfmt(list.length?galleryPage*GALLERY_PAGE+1:0)}–${nfmt(Math.min(list.length,(galleryPage+1)*GALLERY_PAGE))} von ${nfmt(list.length)}</span>${button('gallery-next','Weiter ›','secondary',galleryPage>=pages-1?'disabled':'')}</div></section><div class="contact-preview">${viewer()}<div class="contact-hint">Doppelklick auf ein Foto öffnet die Diashow.</div></div></div>`;
}
function render(){
  if(!state || !view)return;
  const chapterNav=$('chapterNav'), chapterScroll=chapterNav.scrollTop;
  const previousSheet=document.querySelector('.contact-sheet');
  const galleryScroll=previousSheet?{key:previousSheet.dataset.galleryKey,page:previousSheet.dataset.galleryPage,top:previousSheet.scrollTop}:null;
  const previousChapter=chapterNav.querySelector('.chapter-button.current')?.dataset.chapter;
  for(const el of document.querySelectorAll('.virtual-strip'))stripPositions.set(el.dataset.stripKey,el.scrollLeft);
  stripSpecs=new Map();validFocus();document.body.classList.toggle('dark',view.theme==='dark');
  document.querySelectorAll('[data-layout]').forEach(el=>el.classList.toggle('active',el.dataset.layout===view.layout));
  $('albumCount').textContent=nfmt(state.kept.length);$('totalCount').textContent=`von ${nfmt(state.photos.length)} Fotos`;
  $('pageSubtitle').textContent=view.layout==='A'?'Ein Bild im Fokus. Die ganze Reise im Blick.':view.layout==='B'?'Auswahl und Alternativen. Direkt nebeneinander.':'Tage, Motive und Verteilung auf einen Blick.';
  const projectName=state.project?.name || 'Reiseprojekt';$('projectName').textContent=projectName;$('projectCrumb').textContent=projectName;
  $('projectFooter').textContent=`${nfmt(state.photos.length)} Fotos. Deine Originaldateien bleiben erhalten.`;
  $('navLibrary').innerHTML=icon('grid')+'<span>Alle Fotos</span>';$('navReview').innerHTML=icon('eye')+'<span>Auswahl prüfen</span>';$('navExport').innerHTML=icon('folder')+'<span>Album exportieren</span>';
  $('navLibrary').classList.toggle('active',view.layout==='C');$('navReview').classList.toggle('active',view.layout!=='C');
  $('brandIcon').innerHTML='<img class="brand-image" src="./brand.png" alt="" width="36" height="36">';$('themeButton').innerHTML=icon(view.theme==='dark'?'sun':'moon')+`<span>${view.theme==='dark'?'Hell':'Dunkel'}</span>`;
  $('undoButton').innerHTML=icon('undo')+'<span>Rückgängig</span>';$('undoButton').dataset.locked=String(!state.can_undo);
  $('saveButton').innerHTML=icon('check')+'<span>Pause & speichern</span>';$('exportButton').innerHTML=icon('export')+`Finale Auswahl (${nfmt(state.kept.length)})`;
  $('scopeNote').textContent=view.chapter==='all'?'Ganze Reise':state.chapters.find(c=>c.id===view.chapter)?.name || view.chapter;
  $('chapterNav').innerHTML=`<button class="chapter-button ${view.chapter==='all'?'current':''}" data-chapter="all"><span>Ganze Reise</span><span>${nfmt(state.photos.length)}</span></button>`+(state.chapters||[]).map(ch=>`<button class="chapter-button ${view.chapter===ch.id?'current':''}" data-chapter="${esc(ch.id)}" title="${esc(ch.name)}"><span>${esc(ch.name)}</span><span>${nfmt(ch.selected)} / ${nfmt(ch.total)}</span></button>`).join('');
  chapterNav.scrollTop=chapterScroll;
  if(previousChapter!==view.chapter){
    const current=chapterNav.querySelector('.chapter-button.current');
    if(current){
      const bounds=chapterNav.getBoundingClientRect(), active=current.getBoundingClientRect();
      if(active.top<bounds.top)chapterNav.scrollTop+=active.top-bounds.top;
      else if(active.bottom>bounds.bottom)chapterNav.scrollTop+=active.bottom-bounds.bottom;
    }
  }
  $('workspace').innerHTML=view.layout==='A'?viewer()+filmstrip():view.layout==='B'?pair():contacts();
  const currentSheet=document.querySelector('.contact-sheet');
  if(currentSheet && galleryScroll && currentSheet.dataset.galleryKey===galleryScroll.key && currentSheet.dataset.galleryPage===galleryScroll.page)currentSheet.scrollTop=galleryScroll.top;
  mountStrips();updateSavedStatus();
  if(state.notice && state.notice!==lastNotice){ lastNotice=state.notice;$('notice').textContent=state.notice;$('notice').hidden=false; }
  document.documentElement.dataset.photoCount=String(state.photos.length);
  if(modal)renderModal();
}

function openModal(type, data={}){
  clearTimeout(viewTimer);viewTimer=null;
  launch({action:'view',view:{...view,alternative_ids:[...(view.alternative_ids||[])]}});
  lastFocusElement=document.activeElement;modal={type,...data};renderModal();
  queueMicrotask(()=>$('modalHost').querySelector('button,input,select')?.focus());
}
function closeModal(){
  if(modal?.job?.status==='running'){
    if(modal.type==='location')cancelLocation();
    else toast('Der Vorgang läuft weiter. Bitte warte auf das Ergebnis.',false);
    return;
  }
  modal=null;$('modalHost').innerHTML='';lastFocusElement?.isConnected&&lastFocusElement.focus();
}
function modalShell(title,body,foot=''){
  $('modalHost').innerHTML=`<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle"><div class="modal-top"><h2 id="modalTitle">${esc(title)}</h2>${button('close-modal',icon('close'),'icon-button','aria-label="Schließen"')}</div>${modal.error?`<p class="modal-error" role="alert">${esc(modal.error)}</p>`:''}${body}${foot}</section></div>`;
}
function pagedRows(rows){
  modal.page=Math.max(0,Math.min(modal.page||0,Math.max(0,Math.ceil(rows.length/100)-1)));
  return rows.slice(modal.page*100,(modal.page+1)*100);
}
function modalPaging(rows){
  return `<div class="modal-paging">${button('modal-prev','‹ Zurück','secondary',modal.page===0?'disabled':'')}<span>${nfmt(rows.length?modal.page*100+1:0)}–${nfmt(Math.min(rows.length,(modal.page+1)*100))} von ${nfmt(rows.length)}</span>${button('modal-next','Weiter ›','secondary',(modal.page+1)*100>=rows.length?'disabled':'')}</div>`;
}
function exportTree(){
  const photos=albumPhotos(), lines=[`selected/`];
  if(view.export_layout==='flat')photos.forEach((p,i)=>lines.push(`  ${String(i+1).padStart(Math.max(3,String(photos.length).length),'0')}_${p.filename}`));
  else {
    const groups=new Map();for(const p of photos){const group=p.chapter_folder || `${p.region||'Unbestimmt'}/hauptteil`;if(!groups.has(group))groups.set(group,[]);groups.get(group).push(p);}
    for(const [name,members]of groups){lines.push(`  ${name}/`);members.forEach((p,i)=>lines.push(`    ${String(i+1).padStart(3,'0')}_${p.filename}`));}
  }
  if(!photos.length)lines.push('  Noch keine Fotos ausgewählt.');
  return lines.slice(0,250).join('\n')+(lines.length>250?'\n  …':'');
}
function renderModal(){
  if(!modal)return;
  if(modal.type==='export'){
    const job=modal.job, done=job?.status==='done', running=job?.status==='running';
    modalShell(done?'Dein Album wurde exportiert.':'Deine endgültige Auswahl',`<p>Nur deine <strong>${nfmt(state.kept.length)} ausgewählten Fotos</strong> werden als Originalkopien ausgegeben. Deine Originaldateien bleiben erhalten.</p><div class="export-choices">${[['flat','Ein gemeinsamer Ordner','Alle endgültigen Fotos direkt beieinander.'],['chapters','Nach Kapiteln aufteilen','Ein Auswahlordner mit Unterordnern je Kapitel.']].map(([value,title,description])=>`<button class="choice ${view.export_layout===value?'active':''}" data-export-mode="${value}" ${running?'disabled':''}><strong>${title}</strong><span>${description}</span></button>`).join('')}</div><div class="destination-label">Ausgabeordner: ${esc(state.project?.output_dir || '')}</div><pre class="folder-preview">${esc(exportTree())}</pre>${job?`<p class="job-status" role="status">${esc(job.message || (running?'Die endgültigen Fotos werden kopiert …':done?'Bildexport abgeschlossen.':job.error || 'Vorgang beendet.'))}</p>`:''}${job?.warning?`<p class="modal-error">${esc(job.warning)}</p>`:''}`,`<div class="modal-footer"><small>Die bisherige Ausgabe wird nach erfolgreichem Kopieren ersetzt.</small>${button(done?'close-modal':'run-export',icon(done?'check':'export')+(done?'Fertig':running?'Export läuft …':'Finale Auswahl exportieren'),'primary export',running||!state.kept.length?'disabled':'')}</div>`);
  } else if(modal.type==='why'){
    modalShell(currentPhoto()?.filename || 'Warum dieses Bild?',modal.loading?'<p>Gespeicherte Auswahlgründe werden geladen …</p>':(modal.data?.sections||[]).map(section=>`<section class="audit-section"><h3>${esc(section.title)}</h3><div>${esc(section.text).replace(/\n/g,'<br>')}</div></section>`).join('')||'<p>Für dieses Foto ist kein Auswahlgrund aufgezeichnet.</p>');
  } else if(modal.type==='decision'){
    const p=photoMap.get(modal.id);
    modalShell('Deine Entscheidung',`<p>${esc(p.filename)} · Die Vorgabe gilt auch bei einer neuen automatischen Auswahl. Favoritenschutz hat Vorrang.</p><label class="field-label" for="decisionSelect">Dauerhafte Vorgabe</label><select id="decisionSelect"><option value="auto" ${modal.decision==='auto'?'selected':''}>Automatik</option><option value="keep" ${modal.decision==='keep'?'selected':''}>Dauerhaft behalten</option><option value="reject" ${modal.decision==='reject'?'selected':''}>Dauerhaft ablehnen</option></select><label class="field-label" for="decisionReason">Deine Begründung (optional)</label><textarea id="decisionReason" rows="4" maxlength="4096">${esc(modal.reason||'')}</textarea>`,`<div class="modal-footer">${button('close-modal','Abbrechen','secondary')}${button('save-decision','Entscheidung speichern','primary','data-mutates')}</div>`);
  } else if(modal.type==='tools'){
    modalShell('Werkzeuge',`<div class="tool-list">${button('report',icon('info')+'Prüfbericht als HTML / CSV','secondary')}${button('location-open',icon('photo')+'Orte neu prüfen …','secondary')}${button('source-choose',icon('folder')+'Originale wiederfinden …','secondary')}${button('advanced-print','Druckqualität prüfen','secondary','data-tool="print"')}${button('advanced-motifs','Motivgruppen und Erzählmix','secondary','data-tool="motifs"')}${button('advanced-chapters','Kapitel bearbeiten','secondary','data-tool="chapters"')}${button('advanced-rebuild','Auswahl neu berechnen','secondary','data-tool="rebuild"')}${button('advanced-all','Weitere Werkzeuge','secondary','data-tool="all"')}${button('redo',icon('undo')+'Wiederholen','secondary',`data-mutates data-locked="${!state.can_redo}"`)}${button('request-close','Pause, speichern und schließen','secondary')}</div><p>Die erweiterten Prüfungen öffnen den Werkzeugbereich mit deinem gespeicherten Bearbeitungsstand. Grau kennzeichnet nur, dass ein Foto aktuell nicht im Album ist.</p>`);
  } else if(modal.type==='report'){
    modalShell('Prüfbericht',modal.loading?'<p>Bericht wird erstellt …</p>':`<p>Der Bericht trennt aktuelle Entscheidungen, den letzten protokollierten automatischen Lauf und gespeicherte Qualitätshinweise.</p><div class="tool-list">${safeReportLink(modal.data?.report_url,'HTML-Bericht öffnen')}${safeReportLink(modal.data?.csv_url,'CSV-Bericht öffnen')}</div>`);
  } else if(modal.type==='location'){
    const result=modal.result, running=modal.job?.status==='running';
    const rows=result?.changes||[];
    modalShell('Ortszuordnung prüfen',`<p>Die Ortsprüfung verwendet GPS und nahe, eindeutige Aufnahmezeiten. Widersprüchliche Orte bleiben ungeklärt. Deine Bildauswahl bleibt erhalten; eine neue KI-Bewertung ist dafür nicht nötig.</p>${!result?`<label class="check-field"><input type="checkbox" id="locationOnline" ${modal.online?'checked':''} ${running?'disabled':''}> Online-Ortsnamen verwenden</label><p>Online werden GPS-Koordinaten an Nominatim gesendet, keine Fotos. Offline werden bekannte Städte bis 25 km angenähert.</p><label class="field-label" for="locationHours">Zeitanker höchstens entfernt</label><select id="locationHours" ${running?'disabled':''}>${[1,3,6,12,24].map(hours=>`<option ${Number(modal.hours||6)===hours?'selected':''} value="${hours}">${hours} Stunden</option>`).join('')}</select>`:`<p><strong>${nfmt(result.changed_count)} Aktualisierungen</strong> · ${nfmt(result.unresolved_count)} Orte ungeklärt. Auswahl und Favoriten bleiben erhalten.</p><div class="location-table"><table><thead><tr><th>Bild</th><th>Bisher</th><th>Neu</th><th>Grundlage</th></tr></thead><tbody>${pagedRows(rows).map(row=>`<tr><td>${esc(row.filename)}</td><td>${esc(row.old_region||'Unbekannt')}</td><td>${esc(row.new_region||'Ungeklärt')}</td><td>${esc(sourceLabel(row.source))}${row.source_detail?`<br>${esc(row.source_detail)}`:''}${row.warning?`<br>${esc(warningLabel(row.warning))}`:''}</td></tr>`).join('')}</tbody></table></div>${modalPaging(rows)}<p>Speichern übernimmt alle vorgeschlagenen Ortskorrekturen und setzt den Rückgängig-Verlauf zurück.</p>`}${running?`<p class="job-status">${modal.cancelRequested?'Prüfung wird abgebrochen …':'Ortsgrundlagen werden geprüft …'}</p>`:modal.job?.status==='cancelled'?'<p class="job-status">Prüfung abgebrochen. Die bisherigen Zuordnungen bleiben erhalten.</p>':''}`,`<div class="modal-footer">${button(running?'location-cancel':'close-modal',running?'Prüfung abbrechen':'Schließen','secondary',modal.cancelRequested?'disabled':'')}${button(result?'location-apply':'location-run',result?'Alle Ortskorrekturen speichern':'Vorschau berechnen','primary',running||result?.changed_count===0?'disabled':'')}</div>`);
  } else if(modal.type==='source'){
    const result=modal.result;
    const entries=result?.entries||[];
    modalShell('Originale wiederfinden',modal.loading?'<p>Quellordner auswählen …</p>':`<p>${nfmt(result?.changed_count)} Originaldateien können neu verknüpft werden. Die Bildauswahl und Entscheidungen bleiben erhalten.</p><div class="destination-label">Bisher: ${esc(result?.old_root||'')}<br>Neu: ${esc(result?.new_root||'')}</div><div class="location-table"><table><thead><tr><th>Bild</th><th>Ergebnis</th><th>Hinweis</th></tr></thead><tbody>${pagedRows(entries).map(row=>`<tr><td>${esc(row.filename||'')}</td><td>${esc(relinkStatus(row.status))}</td><td>${esc(row.message||'')}</td></tr>`).join('')}</tbody></table></div>${modalPaging(entries)}${result?.can_apply?'':'<p>Die Pfade sind noch nicht eindeutig zugeordnet. Prüfe den gewählten Ordner und starte die Zuordnung erneut.</p>'}`,`<div class="modal-footer">${button('close-modal','Schließen','secondary')}${result?.can_apply?button('source-apply','Neue Originalpfade speichern','primary'):button('source-choose','Anderen Ordner wählen','primary')}</div>`);
  }
  updateSavedStatus();
}
function safeReportLink(path,label){
  if(!path)return '';
  const url=new URL(path,BASE);if(url.origin!==BASE.origin || !url.pathname.startsWith(BASE.pathname))return '';
  return `<a class="secondary report-link" href="${esc(url.href)}" target="_blank" rel="noopener">${esc(label)}</a>`;
}
function sourceLabel(value){return ({gps_online:'GPS / Online-Ortsname',gps_offline:'GPS / Offline-Näherung',time_nearest:'Zeitnaher GPS-Anker',unknown:'Ungeklärt',legacy:'Herkunft unbekannt',manual:'Manuell'})[value]||value||'Herkunft unbekannt';}
function warningLabel(value){return ({conflicting_anchors:'Widersprüchliche Zeitanker',no_nearby_anchor:'Kein naher GPS-Anker',missing_datetime:'Aufnahmedatum fehlt',gps_unresolved:'GPS-Ortsname ungeklärt',invalid_gps:'Ungültige GPS-Angaben'})[value]||value;}
function relinkStatus(value){return ({ready:'Bereit',unchanged:'Unverändert',outside_root:'Anderer Quellordner',missing:'Nicht gefunden',ambiguous:'Mehrdeutig',invalid:'Ungültiges Ziel'})[value]||value||'Ungeklärt';}
async function startJob(payload){
  clearTimeout(viewTimer);viewTimer=null;
  try{
    const result=await transact(payload);if(!modal)return;
    modal.job=result.job;renderModal();pollJob(result.job.id);
  }catch{}
}
async function pollJob(id){
  try{
    const result=await request({action:'job',job_id:id});
    if(result.state)applySnapshot(result.state);
    if(modal){modal.job=result.job;if(result.job.status!=='running')modal.cancelRequested=false;if(result.job.status==='done'){modal.result=result.job.result||{};if(modal.type==='location')modal.preview_id=modal.result.preview_id;}if(result.job.status==='error'){modal.error=result.job.error||'Der Vorgang konnte nicht abgeschlossen werden.';}}
    else if(result.job.status==='error')showError(result.job.error||'Der Vorgang konnte nicht abgeschlossen werden.');
    render();
    if(result.job.status==='running')setTimeout(()=>pollJob(id),500);
  }catch(error){showError(error.message);if(modal){modal.error=error.message;renderModal();}}
}
function cancelLocation(){
  if(modal?.type!=='location' || modal.cancelRequested)return;
  modal.cancelRequested=true;renderModal();
  launch({action:'location_cancel'},{after:()=>{if(modal?.type==='location')renderModal();}});
}

document.addEventListener('click',event=>{
  const control=event.target.closest('button,a');
  if(control?.disabled)return;
  if(control?.dataset.layout){setLayout(control.dataset.layout);return;}
  if(control?.dataset.filter){setFilter(control.dataset.filter);return;}
  if(control?.dataset.chapter){setChapter(control.dataset.chapter);return;}
  if(control?.dataset.exportMode){view.export_layout=control.dataset.exportMode;persistView();renderModal();return;}
  const action=control?.dataset.action;
  if(action){
    const id=Number(control.dataset.id ?? view?.focus), p=photoMap.get(id);
    switch(action){
      case 'library': view.chapter='all';view.filter='all';view.alternative_ids=state.photos.filter(p=>!p.selected).map(p=>p.id);setLayout('C');break;
      case 'review':setLayout('A');break;case 'layout-a':setLayout('A');break;
      case 'theme':view.theme=view.theme==='dark'?'light':'dark';render();persistView();break;
      case 'toggle':toggle(id);break;case 'add':addCurrent();break;case 'replace':replaceCurrent();break;
      case 'undo':case 'redo':if(!mutationDisabled()){
        flushPendingView();
        launch({action},{after:result=>{if(result.view){view.focus=result.view.focus;view.anchor=result.view.anchor;}$('toast').classList.remove('visible');}});
      }break;
      case 'prev':move(-1);break;case 'next':move(1);break;
      case 'gallery-prev':galleryPage--;render();break;case 'gallery-next':galleryPage++;render();break;
      case 'modal-prev':if(modal){modal.page=Math.max(0,(modal.page||0)-1);renderModal();}break;
      case 'modal-next':if(modal){modal.page=(modal.page||0)+1;renderModal();}break;
      case 'favorite':if(p){flushPendingView();launch({action:'favorite',id,value:!p.favorite});}break;
      case 'decision':if(p)openModal('decision',{id,decision:p.manual_decision||'auto',reason:p.decision_reason||''});break;
      case 'save-decision':if(modal)launch({action:'decision',id:modal.id,decision:$('decisionSelect').value,reason:$('decisionReason').value},{after:()=>{closeModal();toast('Dauerhafte Entscheidung gespeichert.');}});break;
      case 'why':openModal('why',{loading:true});transact({action:'audit',id},{after:result=>{if(modal?.type==='why'){modal.loading=false;modal.data=result;renderModal();}}}).catch(()=>{});break;
      case 'tools':openModal('tools');break;case 'open-export':openModal('export');break;
      case 'run-export':startJob({action:'export',export_layout:view.export_layout});break;
      case 'report':openModal('report',{loading:true});transact({action:'report'},{after:result=>{if(modal?.type==='report'){modal.loading=false;modal.data=result;renderModal();}}}).catch(()=>{});break;
      case 'location-open':openModal('location',{online:false,hours:6});break;
      case 'location-run':if(modal){modal.online=$('locationOnline').checked;modal.hours=Number($('locationHours').value);startJob({action:'location_preview',online:modal.online,max_hours:modal.hours});}break;
      case 'location-apply':if(modal)launch({action:'location_apply',preview_id:modal.preview_id},{after:result=>{if(result.view)view={...view,...result.view};closeModal();toast('Ortskorrekturen gespeichert. Auswahl unverändert.');}});break;
      case 'location-cancel':cancelLocation();break;
      case 'source-choose':
        openModal('source',{loading:true});
        transact({action:'source_choose'},{after:result=>{
          if(result.cancelled){closeModal();return;}
          if(modal?.type==='source')transact({action:'source_preview'},{after:preview=>{
            if(modal?.type==='source'){modal.loading=false;modal.result=preview;renderModal();}
          }}).catch(()=>{});
        }}).catch(()=>{});break;
      case 'source-apply':if(modal)launch({action:'source_apply',preview_id:modal.result?.preview_id},{after:result=>{if(result.view)view={...view,...result.view};closeModal();toast('Originaldateien neu verknüpft.');}});break;
      case 'advanced-print':case 'advanced-motifs':case 'advanced-chapters':case 'advanced-rebuild':case 'advanced-all':
        clearTimeout(viewTimer);viewTimer=null;
        launch({action:'advanced',tool:control.dataset.tool||'all'},{after:()=>{if(modal){modal.loading=true;modalShell('Werkzeugbereich wird geöffnet','<p>Dein gespeicherter Bearbeitungsstand wird übernommen.</p>');}}});break;
      case 'close-modal':if(modal?.type==='location'&&modal.preview_id)launch({action:'location_cancel',preview_id:modal.preview_id});closeModal();break;
      case 'save':case 'request-close':closeReview().catch(()=>{});break;
    }
    return;
  }
  const tile=event.target.closest('.thumb');if(tile)choose(Number(tile.dataset.id),tile.dataset.role);
  if(event.target.classList.contains('modal-backdrop'))closeModal();
});
document.addEventListener('dblclick',event=>{const tile=event.target.closest('.thumb');if(tile&&!event.target.closest('.thumb-check')){view.focus=Number(tile.dataset.id);setLayout('A');}});
document.addEventListener('input',event=>{
  if(modal?.type==='decision' && event.target.id==='decisionReason')modal.reason=event.target.value;
});
document.addEventListener('change',event=>{
  if(modal?.type==='decision' && event.target.id==='decisionSelect')modal.decision=event.target.value;
  if(modal?.type==='location' && event.target.id==='locationOnline')modal.online=event.target.checked;
  if(modal?.type==='location' && event.target.id==='locationHours')modal.hours=Number(event.target.value);
});
document.addEventListener('scroll',event=>{
  const el=event.target;if(!el.classList?.contains('virtual-strip'))return;
  stripPositions.set(el.dataset.stripKey,el.scrollLeft);
  if(stripJobs.has(el))return;stripJobs.set(el,requestAnimationFrame(()=>{stripJobs.delete(el);if(el.isConnected)drawStrip(el);}));
},true);
document.addEventListener('error',event=>{
  if(event.target.tagName!=='IMG')return;
  event.target.classList.add('image-failed');
  const stage=event.target.closest('.stage');if(stage&&!stage.querySelector('.image-unavailable')){const label=document.createElement('div');label.className='image-unavailable';label.textContent='Foto nicht verfügbar · Originaldatei prüfen';stage.append(label);}
},true);
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){closeModal();return;}
  if(modal){
    if(event.key==='Tab'){
      const controls=[...$('modalHost').querySelectorAll('button:not(:disabled),input,select,textarea,a[href]')];
      const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }return;
  }
  if(event.target.matches('input,textarea,select'))return;
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();launch({action:'view',view:{...view}});return;}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){
    event.preventDefault();if(mutationDisabled())return;flushPendingView();
    launch({action:event.shiftKey?'redo':'undo'},{after:result=>{if(result.view){view.focus=result.view.focus;view.anchor=result.view.anchor;}}});return;
  }
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='y'){
    event.preventDefault();if(mutationDisabled())return;flushPendingView();
    launch({action:'redo'},{after:result=>{if(result.view){view.focus=result.view.focus;view.anchor=result.view.anchor;}}});return;
  }
  if(event.key==='ArrowRight'){event.preventDefault();move(1);}else if(event.key==='ArrowLeft'){event.preventDefault();move(-1);}
  else if(event.key===' '){if(event.target.tagName==='BUTTON')return;event.preventDefault();toggle(Number(event.target.closest('.thumb')?.dataset.id??view.focus));}
  else if(event.key==='Enter' && event.target.classList.contains('thumb')){event.preventDefault();choose(Number(event.target.dataset.id),event.target.dataset.role);}
  else if(['k','x','u'].includes(event.key.toLowerCase())&&!event.ctrlKey&&!event.metaKey){const p=currentPhoto();if(p){openModal('decision',{id:p.id,decision:({k:'keep',x:'reject',u:'auto'})[event.key.toLowerCase()],reason:p.decision_reason||''});}}
});
window.addEventListener('resize',()=>{for(const el of document.querySelectorAll('.virtual-strip'))drawStrip(el);});
window.addEventListener('beforeunload',()=>{
  if(!state || !view)return;
  // Every selection is already durably saved; this only preserves navigation.
  fetch(new URL('api/action',BASE),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'view',view:{...view},expected_revision:state.revision}),keepalive:true}).catch(()=>{});
});
window.PhotoToolReview={close:closeReview,debug:()=>({state,view,pool:pool().map(p=>p.id),scoped:scoped().map(p=>p.id),renderedImageCount:document.images.length,stripImageCount:document.querySelectorAll('.virtual-strip img').length}),refresh:async()=>{const response=await fetch(new URL('api/state',BASE),{cache:'no-store'});applySnapshot(await response.json(),true);render();}};
window.PhotoToolState=()=>state;

(async()=>{
  try{
    const response=await fetch(new URL('api/state',BASE),{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw new Error('Das Reiseprojekt konnte nicht geöffnet werden.');
    applySnapshot(await response.json(),true);render();revealFocus();
    document.documentElement.dataset.appReady='true';
    if(state.busy && state.job?.id)pollJob(state.job.id);
  }catch(error){$('workspace').innerHTML='<div class="loading-state"><h2>Projekt nicht verfügbar</h2><p id="startupError"></p><button class="primary" data-action="reload">Erneut versuchen</button></div>';$('startupError').textContent=error.message;$('workspace').querySelector('button').addEventListener('click',()=>location.reload());showError(error.message);}
})();
