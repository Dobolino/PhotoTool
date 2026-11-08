"""Exercise the real modern UI against an existing synthetic photo project.

Uses the system Chromium and Node runtimes. It copies project metadata into a
new QA output directory, runs the actual Python session/server, then checks
selection, lazy rendering, two exports and exact reopening. Originals are read
only. No models, geocoding service or paid AI is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


BROWSER_CHECK = r'''
const fs=require('fs');
const [port,url,out]=process.argv.slice(2);
(async()=>{
 const tabs=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
 const target=tabs.find(tab=>tab.type==='page');
 const ws=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 let sequence=0;const pending=new Map,errors=[];
 ws.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){pending.get(data.id)(data);pending.delete(data.id)}if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text)};
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout: '+method))}},20000).unref()});
 const ev=async expression=>{const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.result?.exceptionDetails)throw Error(JSON.stringify(response.result.exceptionDetails));return response.result.result.value};
 const pause=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
 const assert=(condition,message)=>{if(!condition)throw Error(message)};
 const wait=async(expression,message,timeout=20000)=>{const until=Date.now()+timeout;while(Date.now()<until){if(await ev(expression))return;await pause(80)}throw Error(message)};
 const idle=()=>wait(`document.getElementById('savedStatus')?.textContent.includes('Zwischenstand gespeichert') && !PhotoToolReview.debug().state.busy`,'UI did not become idle');
 const click=async selector=>{assert(await ev(`Boolean(document.querySelector(${JSON.stringify(selector)}))`),'Missing control '+selector);await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);await pause(500);await idle()};
 const thumb=async(id,key='all',role='focus')=>{
   const list=await ev(`(()=>{const d=PhotoToolReview.debug();return ${key==='album'?'d.state.kept.filter(id=>d.scoped.includes(id))':key==='alternatives'?'d.scoped.filter(id=>d.view.alternative_ids.includes(id))':'d.pool'}})()`);
   const index=list.indexOf(id);assert(index>=0,'Photo not in strip '+id);
   const strip=`.virtual-strip[data-strip-key="${key}"]`;
   await ev(`(()=>{const element=document.querySelector(${JSON.stringify(strip)});element.scrollLeft=${index*116};element.dispatchEvent(new Event('scroll'));})()`);await pause(120);
   const selector=`${strip} .thumb[data-id="${id}"][data-role="${role}"]`;
   await wait(`Boolean(document.querySelector(${JSON.stringify(selector)}))`,'Virtual strip did not render target '+id);
   return selector;
 };
 await send('Page.enable');await send('Runtime.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1500,height:980,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});
 await wait(`document.documentElement.dataset.appReady==='true' && Boolean(window.PhotoToolReview)`,'Production workspace did not initialize');
 await click('[data-chapter="all"]');await click('[data-layout="A"]');await click('[data-filter="all"]');
 const initial=await ev(`PhotoToolReview.debug()`),initialKept=initial.state.kept;
 assert(initial.state.photos.length===Number(process.env.PHOTO_QA_COUNT),'Incorrect imported count');
 assert(initial.pool.length===initial.state.photos.length,'All photos filter omitted unselected imports');
 assert(initial.stripImageCount<100,'Filmstrip eagerly rendered the whole photo collection');
 const tokyo=initial.state.photos.filter(p=>p.region==='Tokyo');
 assert(tokyo.some(p=>/^\d+_Tokyo\//.test(p.chapter_folder||'')) && tokyo.some(p=>!p.chapter_folder),'Fixture lacks selected folder / reserve chapter contrast');
 assert(new Set(tokyo.map(p=>p.chapter)).size===1,'Tokyo reserve and numbered selected chapter were split');
 assert(initial.state.chapters.every(ch=>ch.total===initial.state.photos.filter(p=>p.chapter===ch.id).length && ch.selected===initial.state.photos.filter(p=>p.chapter===ch.id&&p.selected).length),'Chapter counters do not match actual photos');
 // A different chapter must never retain another city's anchor or album lane.
 const otherChapter=initial.state.chapters.find(ch=>ch.id!==initial.state.chapters[0].id&&ch.selected>0&&ch.total>ch.selected).id;
 await click('[data-layout="B"]');await click(`[data-chapter="${otherChapter}"]`);
 const scopedBefore=await ev('PhotoToolReview.debug()');
 assert(scopedBefore.state.photos.find(p=>p.id===scopedBefore.view.anchor)?.chapter===otherChapter,'Comparison anchor belongs to another chapter');
 assert(await ev(`[...document.querySelectorAll('.virtual-strip[data-strip-key="album"] .thumb')].every(el=>PhotoToolReview.debug().state.photos.find(p=>p.id===Number(el.dataset.id)).chapter===${JSON.stringify(otherChapter)})`),'Comparison album strip leaked photos from another chapter');
 const scopedCandidate=scopedBefore.state.photos.find(p=>p.chapter===otherChapter&&!p.selected&&p.manual_decision!=='reject'&&!p.favorite).id;
 let scopedSelector=await thumb(scopedCandidate,'alternatives');await click(scopedSelector);
 await click('[data-action="add"]');
 assert(await ev(`PhotoToolReview.debug().view.anchor===${scopedBefore.view.anchor}`),'Add unexpectedly replaced the selected chapter anchor');
 await click('#undoButton');
 await click('[data-chapter="all"]');await click('[data-layout="A"]');await click('[data-filter="all"]');
 const candidate=initial.state.photos.find(photo=>!photo.selected&&photo.manual_decision!=='reject'&&!photo.flags.includes('unreadable')).id;
 const anchor=initial.state.photos.find(photo=>photo.selected&&!photo.favorite&&photo.manual_decision==='auto').id;
 const anchorPosition=initial.state.photos.find(photo=>photo.id===anchor).position;
 // Removing an existing album image makes it available in the stable pool.
 let removedSelector=await thumb(anchor);await click(removedSelector+' .thumb-check');
 assert(await ev(`!PhotoToolReview.debug().state.kept.includes(${anchor}) && PhotoToolReview.debug().view.alternative_ids.includes(${anchor})`),'Removed album photo did not enter alternatives');
 await click('[data-filter="alternatives"]');
 assert(await ev(`PhotoToolReview.debug().pool.includes(${anchor})`),'Removed album photo is inaccessible in alternatives');
 await click('#undoButton');await click('[data-filter="all"]');
 let selector=await thumb(candidate);
 await click(selector);
 assert(await ev(`PhotoToolReview.debug().view.focus===${candidate}`),'Thumbnail failed to focus');
 assert(await ev(`JSON.stringify(PhotoToolReview.debug().state.kept)===${JSON.stringify(JSON.stringify(initialKept))}`),'Thumbnail click changed selection');
 assert(await ev(`getComputedStyle(document.querySelector('.large-image')).filter==='none'`),'Large omitted preview was gray');
 await click('[data-filter="alternatives"]');
 const alternatives=await ev('PhotoToolReview.debug().pool.length');
 selector=await thumb(candidate);
 await click(selector+' .thumb-check');
 assert(await ev(`PhotoToolReview.debug().state.photos.find(photo=>photo.id===${candidate}).selected`),'Checkbox did not select');
 assert(await ev(`PhotoToolReview.debug().pool.length===${alternatives} && PhotoToolReview.debug().pool.includes(${candidate})`),'Selected alternative disappeared from source pool');
 assert(await ev(`document.querySelector(${JSON.stringify(selector)}).classList.contains('selected')`),'Selected thumbnail did not become colored');
 await click('#undoButton');
 assert(await ev(`!PhotoToolReview.debug().state.photos.find(photo=>photo.id===${candidate}).selected`),'Undo failed to remove added photo');
 await click('[data-layout="B"]');
 selector=await thumb(anchor,'album','album');await click(selector);
 selector=await thumb(candidate,'alternatives');await click(selector);
 await click('[data-action="replace"]');
 assert(await ev(`PhotoToolReview.debug().state.kept.length===${initialKept.length} && PhotoToolReview.debug().state.kept.includes(${candidate}) && !PhotoToolReview.debug().state.kept.includes(${anchor})`),'Replace did not exchange exactly one photo');
 assert(await ev(`PhotoToolReview.debug().state.photos.find(photo=>photo.id===${candidate}).position===${anchorPosition}`),'Replace lost album slot');
 await click('#undoButton');
 assert(await ev(`PhotoToolReview.debug().state.kept.includes(${anchor})&&!PhotoToolReview.debug().state.kept.includes(${candidate})`),'Composite replacement Undo failed');
 // Reapply the exchange through the real controls before exporting.
 selector=await thumb(anchor,'album','album');await click(selector);
 selector=await thumb(candidate,'alternatives');await click(selector);
 await click('[data-action="replace"]');
 await click('#exportButton');
 await click('[data-export-mode="flat"]');
 await click('[data-action="run-export"]');
 await wait(`PhotoToolReview.debug().state.job?.status==='done' && !PhotoToolReview.debug().state.busy`,'Flat export did not finish',60000);
 assert(await ev(`document.querySelector('.modal h2').textContent.includes('exportiert')`),'Export success was not shown');
 await click('[data-action="close-modal"]');
 const screenshots=[];
 for(const [layout,name] of [['A','modern-a'],['B','modern-b'],['C','modern-c']]){
   await click(`[data-layout="${layout}"]`);await pause(500);
   assert(await ev(`document.documentElement.scrollWidth<=innerWidth`),'Horizontal overflow in '+layout);
   const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
   fs.writeFileSync(`${out}/${name}.png`,Buffer.from(capture.result.data,'base64'));screenshots.push(name+'.png');
 }
 const galleryImages=await ev(`document.querySelectorAll('#workspace img').length`);
 assert(galleryImages<=65,'Contact sheet rendered all imports instead of a bounded page');
 await click('[data-layout="B"]');
 if(await ev(`PhotoToolReview.debug().view.theme!=='dark'`))await click('#themeButton');
 const exportKept=await ev('PhotoToolReview.debug().state.kept');
 // Simulate native X immediately after a selection and debounced navigation.
 await click('[data-chapter="all"]');await click('[data-layout="A"]');await click('[data-filter="all"]');
 const closeCandidate=await ev(`PhotoToolReview.debug().state.photos.find(p=>!p.selected&&p.manual_decision!=='reject'&&!p.favorite).id`);
 const closeChapter=await ev(`PhotoToolReview.debug().state.chapters.find(ch=>ch.id!==PhotoToolReview.debug().state.photos.find(p=>p.id===${closeCandidate}).chapter).id`);
 const closeSelector=await thumb(closeCandidate);
 const closeResult=await ev(`(async()=>{
   const originalFetch=window.fetch.bind(window),requests=[];
   window.fetch=async(input,options)=>{if(options?.body){const body=JSON.parse(options.body);requests.push(body.action);if(body.action==='toggle')await new Promise(resolve=>setTimeout(resolve,120));}return originalFetch(input,options);};
   document.querySelector(${JSON.stringify(closeSelector+' .thumb-check')}).click();
   [...document.querySelectorAll('[data-chapter]')].find(el=>el.dataset.chapter===${JSON.stringify(closeChapter)}).click();
   document.getElementById('themeButton').click();
   document.querySelector('[data-layout="B"]').click();
   document.querySelector('[data-action="next"]')?.click();
   const expected={...PhotoToolReview.debug().view};
   await PhotoToolReview.close();
   window.fetch=originalFetch;
   return {requests,expected,actual:PhotoToolReview.debug()};
 })()`);
 assert(closeResult.actual.state.kept.includes(closeCandidate),'Close discarded queued selection');
 assert(closeResult.actual.state.close_requested,'Native close hook did not request close');
 assert(closeResult.requests.includes('toggle') && closeResult.requests.at(-2)==='view' && closeResult.requests.at(-1)==='close','Close ran before latest view / queued selection: '+closeResult.requests);
 for(const key of ['layout','filter','chapter','focus','theme'])assert(closeResult.actual.state.view[key]===closeResult.expected[key],'Close lost latest navigation '+key);
 const final=closeResult.actual;
 assert(errors.length===0,'Browser exceptions: '+errors.join('; '));
 const result={success:true,total:initial.state.photos.length,initial_kept:initialKept,export_kept:exportKept,kept:final.state.kept,view:final.view,anchor,candidate,anchorPosition,initialStripImages:initial.stripImageCount,finalStripImages:final.stripImageCount,galleryImages,screenshots,close_requests:closeResult.requests,browser_errors:errors,checks:['all imports accessible','canonical selected/reserve chapters','chapter counters','chapter-scoped comparison anchor and filmstrip','Add keeps anchor','removed photo enters alternatives','virtual mixed filmstrip','thumbnail focus without selection','large omitted preview in color','checkbox selection color','stable alternative source pool','single Undo','exact replacement slot','replacement Undo','real flat export','three layouts','queued selection plus latest view before native close']};
 fs.writeFileSync(`${out}/browser-result.json`,JSON.stringify(result,null,2));
 ws.close();
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''


BROWSER_RELINK_CHECK = r'''
const fs=require('fs');
const [port,url,out]=process.argv.slice(2);
(async()=>{
 const tabs=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
 const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 let sequence=0;const pending=new Map;
 ws.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){pending.get(data.id)(data);pending.delete(data.id)}};
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout: '+method))}},20000).unref()});
 const ev=async expression=>{const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.result?.exceptionDetails)throw Error(JSON.stringify(response.result.exceptionDetails));return response.result.result.value};
 const pause=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
 const assert=(condition,message)=>{if(!condition)throw Error(message)};
 const wait=async(expression,message)=>{const until=Date.now()+15000;while(Date.now()<until){if(await ev(expression))return;await pause(80)}throw Error(message)};
 const click=async selector=>{await wait(`Boolean(document.querySelector(${JSON.stringify(selector)}))`,'Missing control '+selector);await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);await pause(200)};
 const pixel=`(()=>{const i=document.querySelector('.large-image');if(!i?.complete||!i.naturalWidth)return null;const c=document.createElement('canvas');c.width=c.height=1;c.getContext('2d').drawImage(i,0,0,1,1);return [...c.getContext('2d').getImageData(0,0,1,1).data]})()`;
 await send('Page.enable');await send('Page.navigate',{url});
 await wait(`document.documentElement.dataset.appReady==='true' && window.PhotoToolReview`,'Relink fixture did not load');
 await wait(`(${pixel})?.[0]>200`,'Initial red preview did not load');
 await click('[data-layout="B"]');
 const emptyChapter=await ev('PhotoToolReview.debug().state.photos.find(p=>p.id===1).chapter');
 await ev(`[...document.querySelectorAll('[data-chapter]')].find(el=>el.dataset.chapter===${JSON.stringify(emptyChapter)}).click()`);await pause(500);
 assert(await ev(`PhotoToolReview.debug().view.anchor===null && PhotoToolReview.debug().view.focus===1`),'Empty chapter retained an unrelated anchor or candidate');
 assert(await ev(`!document.querySelector('[data-pair-role="album"] img') && document.querySelector('[data-pair-role="candidate"] img').dataset.photoId==='1'`),'Empty chapter displayed an unrelated photo');
 assert(await ev(`document.querySelector('[data-action="replace"]').disabled && !document.querySelector('[data-action="add"]').disabled`),'Empty chapter actions do not guide first Add');
 await click('[data-action="add"]');
 await wait(`PhotoToolReview.debug().state.kept.includes(1) && PhotoToolReview.debug().view.anchor===1`,'First Add did not establish local chapter anchor');
 await click('#undoButton');await wait(`!PhotoToolReview.debug().state.kept.includes(1)`,'Empty chapter Add Undo failed');
 await click('[data-chapter="all"]');await click('[data-layout="A"]');
 await ev(`document.querySelector('.thumb[data-id="0"]').click()`);await pause(500);
 const oldURL=await ev(`document.querySelector('.large-image').src`);
 const oldKept=await ev('PhotoToolReview.debug().state.kept');
 const oldView=await ev('PhotoToolReview.debug().view');
 await click('[data-action="tools"]');await click('[data-action="source-choose"]');
 await wait(`Boolean(document.querySelector('[data-action="source-apply"]'))`,'Source chooser did not produce an applicable preview');
 await click('[data-action="source-apply"]');
 await wait(`PhotoToolReview.debug().state.image_revision===1`,'Relink did not publish new image revision');
 await wait(`(${pixel})?.[2]>200 && (${pixel})?.[0]<60`,'Browser retained cached old photo after relink');
 const freshURL=await ev(`document.querySelector('.large-image').src`);
 assert(freshURL!==oldURL && freshURL.includes('v=1'),'Relink did not version image URLs');
 assert(await ev(`JSON.stringify(PhotoToolReview.debug().state.kept)===${JSON.stringify(JSON.stringify(oldKept))}`),'Relink changed kept photos');
 for(const key of ['layout','chapter','filter','focus','anchor','theme'])assert(await ev(`PhotoToolReview.debug().view[${JSON.stringify(key)}]===${JSON.stringify(oldView[key])}`),'Relink changed view '+key);
 const result={success:true,before_image_url:oldURL.split('/image/')[1],after_image_url:freshURL.split('/image/')[1],pixel:await ev(pixel),checks:['empty chapter has no unrelated anchor','empty chapter Add establishes local anchor','native chooser to source preview','apply real CSV/draft path repair','versioned browser image cache','color pixels changed','selection and view preserved']};
 fs.writeFileSync(`${out}/browser-relink-result.json`,JSON.stringify(result,null,2));ws.close();
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''


def check_browser_relink(output, port):
    """Reproduce an image-ID cache collision with two real colored JPEGs."""
    from PIL import Image
    from photobook_curator.models import Photo
    from photobook_curator.output import write_csv
    from photobook_curator.modern_review import ReviewServer
    from photobook_curator.modern_review_session import ReviewSession
    from photobook_curator.review_export import plan_from_photos
    fixture = output / 'relink-fixture'
    old, new, project = (fixture / name for name in ('old', 'new', 'project'))
    for directory in (old, new, project):
        directory.mkdir(parents=True)
    photos = []
    for index in range(2):
        name = f'{index}.jpg'
        Image.new('RGB', (640, 480), (230, 30, 20)).save(old / name)
        Image.new('RGB', (640, 480), (20, 30, 230)).save(new / name)
        photos.append(Photo(old / name, name, region='Tokyo' if index == 0 else 'Nara', is_candidate=True,
                            is_selected=index == 0, book_position=1 if index == 0 else None))
    write_csv(photos, project / 'photos_analysis.csv')
    (project / 'phototool_project.json').write_text(json.dumps({
        'kind': 'phototool_project', 'version': 1, 'input_dir': str(old)}))
    session = ReviewSession(photos, plan_from_photos(photos), project,
                           on_native=lambda name, payload: {'old_root': str(old), 'new_root': str(new)})
    server = ReviewServer(session)
    try:
        url = server.start()
        harness = output / 'browser-relink-check.cjs'
        harness.write_text(BROWSER_RELINK_CHECK, encoding='utf-8')
        result = subprocess.run(['node', str(harness), str(port), url, str(output)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        assert all(session.image_photo(index).path == new / f'{index}.jpg' for index in range(2))
        return json.loads((output / 'browser-relink-result.json').read_text())
    finally:
        server.close()
        session.close()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_export(session, output, layout, kept=None):
    if kept is None:
        kept = session.snapshot()['kept']
    expected = Counter(sha(session.image_photo(index).path) for index in kept)
    exported = [path for path in (output / 'selected').rglob('*') if path.is_file()]
    assert len(exported) == len(kept)
    assert Counter(sha(path) for path in exported) == expected
    assert all((path.parent == output / 'selected') == (layout == 'flat') for path in exported)
    assert (output / 'selection_audit.html').is_file()
    assert (output / 'selection_audit.csv').is_file()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-count', type=int, default=2000)
    args = parser.parse_args()
    source, output = args.project.resolve(), args.output.resolve()
    if not (source / 'photos_analysis.csv').is_file():
        parser.error('project must contain photos_analysis.csv')
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        parser.error('QA output must be separate from the source project')
    if output.exists() and any(output.iterdir()):
        parser.error('QA output must be new or empty')
    if not shutil.which('chromium') or not shutil.which('node'):
        parser.error('system Chromium and Node are required for this development check')
    output.mkdir(parents=True, exist_ok=True)
    for name in ('photos_analysis.csv', 'selection_draft.json'):
        if (source / name).is_file():
            shutil.copy2(source / name, output / name)
    from photobook_curator.modern_review import ReviewServer
    from photobook_curator.modern_review_session import ReviewSession
    from photobook_curator.review_export import load_photos_from_csv, plan_from_photos
    photos = load_photos_from_csv(output / 'photos_analysis.csv')
    assert len(photos) == args.expected_count
    session = ReviewSession(photos, plan_from_photos(photos), output)
    server = ReviewServer(session)
    url = server.start()
    profile = output / 'chromium-profile'
    profile.mkdir()
    harness = output / 'browser-check.cjs'
    harness.write_text(BROWSER_CHECK, encoding='utf-8')
    started = time.monotonic()
    with (output / 'chromium.log').open('w') as log:
        browser = subprocess.Popen(['chromium', '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
            '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'], stdout=log, stderr=log)
        try:
            deadline = time.monotonic()+20
            port_file = profile / 'DevToolsActivePort'
            while not port_file.is_file():
                if browser.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Chromium DevTools did not become ready')
                time.sleep(.05)
            port = port_file.read_text().splitlines()[0]
            import os
            result = subprocess.run(['node', str(harness), port, url, str(output)],
                env={**os.environ, 'PHOTO_QA_COUNT': str(args.expected_count)}, capture_output=True,
                text=True, timeout=180)
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout)
            browser_result = json.loads((output / 'browser-result.json').read_text())
            check_export(session, output, 'flat', browser_result['export_kept'])
            expected_view = {key: browser_result['view'][key] for key in
                             ('layout', 'filter', 'chapter', 'focus', 'anchor', 'theme', 'export_layout')}
            session.save()
            server.close()
            session.close()
            reopened_photos = load_photos_from_csv(output / 'photos_analysis.csv')
            reopened = ReviewSession(reopened_photos, plan_from_photos(reopened_photos), output)
            restored = reopened.snapshot()
            assert restored['kept'] == browser_result['kept']
            assert {key: restored['view'][key] for key in expected_view} == expected_view
            job = reopened.action({'action': 'export', 'export_layout': 'chapters'})['job']
            deadline = time.monotonic()+60
            while job['status'] == 'running':
                if time.monotonic()>deadline:
                    raise TimeoutError('Chapter export did not finish')
                time.sleep(.05)
                job = reopened.action({'action': 'job', 'job_id': job['id']})['job']
            assert job['status'] == 'done', job
            check_export(reopened, output, 'chapters')
            reopened.close()
            relink_result = check_browser_relink(output, port)
            results = {'success': True, 'photos': len(photos), 'selected': len(restored['kept']),
                'elapsed_seconds': round(time.monotonic()-started, 3), 'browser': browser_result,
                'browser_source_relink': relink_result,
                'export_verification': 'exact kept count and SHA-256 multiset, flat and chapter output',
                'resume': 'exact kept list and layout/filter/chapter/focus/anchor/theme/export mode',
                'fixture': 'synthetic metadata and 24-MP JPEGs; not a real-photo quality judgement'}
            (output / 'result.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps({key: results[key] for key in ('success', 'photos', 'selected', 'elapsed_seconds', 'export_verification', 'resume')}, indent=2))
        finally:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    browser.kill()
            server.close()
            if not session.busy:
                session.close()


if __name__ == '__main__':
    main()
