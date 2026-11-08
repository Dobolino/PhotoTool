"""Exercise bounded review geometry with many chapters and mixed image shapes.

Creates generated local JPEGs, serves the real production workspace, and drives
system Chromium through CDP. This checks layout and navigation, not photo quality.
Use --baseline to reproduce the released 0.5.0 overflow after CSS changes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def create_fixture(directory: Path, count: int = 2618, chapters: int = 43):
    from PIL import Image, ImageDraw
    from photobook_curator.models import Photo
    from photobook_curator.output import write_csv
    from photobook_curator.review_export import plan_from_photos
    from photobook_curator.utils import slugify

    originals = directory / "generated-originals"
    output = directory / "Japan layout test"
    originals.mkdir(parents=True)
    output.mkdir()
    shapes = [(2400, 1600), (1200, 1800), (3000, 1000), (1200, 1200)]
    templates = []
    for number, (width, height) in enumerate(shapes):
        image = Image.new("RGB", (width, height), "#cce5dc")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, height // 7), fill="#153a40")
        draw.rectangle((width // 8, height // 3, width * 7 // 8, height * 5 // 6), fill="#ae5a43")
        draw.polygon(((width // 12, height // 3), (width // 2, height // 6), (width * 11 // 12, height // 3)), fill="#254c43")
        for x, y, color in [(0, 0, "#ed422f"), (width - 100, 0, "#2b62de"),
                            (0, height - 100, "#3bba49"), (width - 100, height - 100, "#f5be23")]:
            draw.rectangle((x, y, x + 99, y + 99), fill=color)
        draw.text((120, 25), f"SYNTHETIC RESPONSIVE TEST / shape {number}", fill="white")
        template = directory / f"template-{number}.jpg"
        image.save(template, quality=88)
        image.close()
        templates.append(template)
    regions = ["Nara"] + [
        f"Transit Hatsukaichi–Fujikawaguchiko über Nishinomiya · Abschnitt {index:02d}"
        if index % 2 else f"Kyoto · Stadtbezirk mit langer Kapitelbezeichnung {index:02d}"
        for index in range(1, chapters)
    ]
    selected = {7} | {67 + round(index * (count - 68) / 158) for index in range(159)}
    photos = []
    for index in range(count):
        chapter = 0 if index < 67 else 1 + ((index - 67) // 61) % (chapters - 1)
        region = regions[chapter]
        path = originals / f"TEST_{index:05d}.jpg"
        shutil.copyfile(templates[index % len(templates)], path)
        width, height = shapes[index % len(shapes)]
        photos.append(Photo(path, path.name, width=width, height=height,
            datetime_taken=datetime(2025, 11, 18, 9, 46) + timedelta(seconds=index * 10),
            region=region, country="Japan", is_candidate=True,
            chapter_folder=f"{chapter + 1:02d}_{slugify(region)}/hauptteil", chapter_type="Hauptteil",
            is_selected=index in selected, book_position=None,
            landmark="Tōdai-ji · Nara – lange Motivbeschreibung für den Layouttest",
            technical_score=96, final_score=96))
    for position, index in enumerate(sorted(selected), 1):
        photos[index].book_position = position
    write_csv(photos, output / "photos_analysis.csv")
    return photos, plan_from_photos(photos), output


BROWSER_CHECK = r'''
const fs=require('fs');
const [port,url,out]=process.argv.slice(2);
(async()=>{
 const tabs=await(await fetch(`http://127.0.0.1:${port}/json`)).json();
 const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 let sequence=0;const pending=new Map,exceptions=[];
 ws.onmessage=event=>{const data=JSON.parse(event.data);if(data.id&&pending.has(data.id)){pending.get(data.id)(data);pending.delete(data.id)}if(data.method==='Runtime.exceptionThrown')exceptions.push(data.params.exceptionDetails.text)};
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout '+method))}},20000).unref()});
 const ev=async expression=>{const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.result?.exceptionDetails)throw Error(JSON.stringify(response.result.exceptionDetails));return response.result.result.value};
 const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const wait=async(expression,message)=>{const until=Date.now()+20000;while(Date.now()<until){if(await ev(expression))return;await pause(50)}throw Error(message)};
 const idle=()=>wait(`document.querySelector('#savedStatus')?.textContent.includes('Zwischenstand gespeichert') && !PhotoToolReview.debug().state.busy`,'Pending view/choice did not save');
 const click=async selector=>{await wait(`Boolean(document.querySelector(${JSON.stringify(selector)}))`,'Missing '+selector);await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);await pause(420);await idle()};
 await send('Page.enable');await send('Runtime.enable');
 const cases=[],sizes=process.env.PHOTO_QA_COMPACT==='1'?[[1093,614],[980,600]]:[[1920,1080],[1366,768],[1536,864],[1280,720],[1093,614],[980,600]];
 await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});
 await wait(`document.documentElement.dataset.appReady==='true' && Boolean(window.PhotoToolReview)`,'Workspace did not initialize');
 const geometry=`(()=>{
   const rect=el=>{if(!el)return null;const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
   const fit=(r,outer={x:0,y:0,right:innerWidth,bottom:innerHeight})=>r&&r.width>0&&r.height>0&&r.x>=outer.x-2&&r.y>=outer.y-2&&r.right<=outer.right+2&&r.bottom<=outer.bottom+2;
   const violations=[],doc=document.documentElement,app=rect(document.querySelector('.app')),workspace=rect(document.querySelector('#workspace'));
   if(doc.scrollHeight>innerHeight+2)violations.push('document vertical overflow '+doc.scrollHeight+' > '+innerHeight);
   if(doc.scrollWidth>innerWidth+2)violations.push('document horizontal overflow');
   for(const selector of ['.app','.main','#workspace','#exportButton','.footnote'])if(!fit(rect(document.querySelector(selector))))violations.push(selector+' outside viewport');
   const nav=document.getElementById('chapterNav'),navRect=rect(nav),navVisible=navRect?.height>0;
   if(!navVisible)violations.push('chapter navigation unavailable');
   if(navVisible&&(!fit(navRect)||nav.scrollHeight<=nav.clientHeight))violations.push('long chapter list lacks bounded scroll');
   const images=[...document.querySelectorAll('.large-image')].map(image=>{const r=rect(image),stage=rect(image.closest('.stage'));if(!image.complete||!image.naturalWidth)violations.push('large image not decoded');if(!fit(r,stage))violations.push('image exceeds stage');if(!fit(stage))violations.push('stage exceeds viewport');if(stage.height<100)violations.push('stage too short');return {rect:r,stage,natural:[image.naturalWidth,image.naturalHeight],objectFit:getComputedStyle(image).objectFit}});
   const layout=PhotoToolReview.debug().view.layout;
   const fixed=layout==='A'?['.strip-card','.info-buttons','.stage-nav']:layout==='B'?['.action-bar','.lanes']:['.contact-layout','.contact-preview','.contact-preview .info-buttons'];
   for(const selector of fixed)if(!fit(rect(document.querySelector(selector))))violations.push(selector+' outside viewport');
   const sheet=document.querySelector('.contact-sheet');
   if(sheet&&sheet.scrollHeight<=sheet.clientHeight)violations.push('contact grid lacks own scroll');
   return {layout,viewport:[innerWidth,innerHeight],document:[doc.scrollWidth,doc.scrollHeight],app,workspace,nav:{rect:navRect,client:nav?.clientHeight,scroll:nav?.scrollHeight},images,violations};
 })()`;
 for(const [width,height] of sizes){
   await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
   await pause(150);
   await click('[data-chapter="all"]');await click('[data-layout="A"]');await click('[data-filter="all"]');
   for(const layout of ['A','B','C']){
     await click(`[data-layout="${layout}"]`);
     await wait(`[...document.querySelectorAll('.large-image')].every(i=>i.complete&&i.naturalWidth>0)`,'Preview failed to decode');
     let metrics=await ev(geometry);
     metrics.case=`${width}x${height}-${layout}`;
     fs.writeFileSync(`${out}/progress.json`,JSON.stringify({case:metrics.case,metrics},null,2));
     if(layout==='C'){
       const page=await ev(`(()=>{const sheet=document.querySelector('.contact-sheet');sheet.scrollTop=sheet.scrollHeight;return {text:document.querySelector('.gallery-paging span')?.textContent,tiles:document.querySelectorAll('.contact-grid>.thumb').length}})()`);
       if(page.tiles!==60)metrics.violations.push('first gallery page is not 60 photos');
       await click('[data-action="gallery-next"]');
       metrics.pageAfterNext=await ev(`document.querySelector('.gallery-paging span')?.textContent`);
       if(!metrics.pageAfterNext?.includes('61–120'))metrics.violations.push('gallery paging did not advance');
     }
     if(layout==='A'){
       // A portrait must fit just as reliably as the initial landscape.
       await click('.virtual-strip .thumb[data-id="1"]');
       await wait(`document.querySelector('.large-image')?.dataset.photoId==='1' && document.querySelector('.large-image').complete`,'Portrait failed to load');
       metrics.portrait=await ev(geometry);
       metrics.violations.push(...metrics.portrait.violations.map(v=>'portrait: '+v));
     }
     const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
     fs.writeFileSync(`${out}/${metrics.case}.png`,Buffer.from(capture.result.data,'base64'));
     cases.push(metrics);
     fs.writeFileSync(`${out}/cases.json`,JSON.stringify(cases,null,2));
   }
   await ev(`(()=>{const nav=document.getElementById('chapterNav');nav.scrollTop=nav.scrollHeight;})()`);
 }
 // Selection rerenders must not jump a deeply scrolled chapter list to the top.
 await click('[data-layout="A"]');
 const chapter=await ev('PhotoToolReview.debug().state.chapters.at(-1).id');
 await ev(`(()=>{const nav=document.getElementById('chapterNav');nav.scrollTop=nav.scrollHeight;[...nav.querySelectorAll('[data-chapter]')].find(b=>b.dataset.chapter===${JSON.stringify(chapter)}).click()})()`);
 await pause(500);
 await idle();
 await click('.virtual-strip .thumb:not(.selected)');
 const navBefore=await ev('document.getElementById("chapterNav").scrollTop');
 const keptBefore=await ev('PhotoToolReview.debug().state.kept.length');
 await click('.info-buttons [data-action="toggle"]');
 const afterAdd=await ev('({top:document.getElementById("chapterNav").scrollTop,count:PhotoToolReview.debug().state.kept.length})');
 await click('#undoButton');
 const afterUndo=await ev('({top:document.getElementById("chapterNav").scrollTop,count:PhotoToolReview.debug().state.kept.length})');
 const navigation={before:navBefore,afterAdd,afterUndo,keptBefore,success:navBefore>100&&Math.abs(afterAdd.top-navBefore)<=2&&Math.abs(afterUndo.top-navBefore)<=2&&afterAdd.count===keptBefore+1&&afterUndo.count===keptBefore};
 await wait(`document.querySelector('#brandIcon img')?.complete && document.querySelector('#brandIcon img')?.naturalWidth>0`,'Program logo did not decode');
 const logo=await ev(`({src:document.querySelector('#brandIcon img').getAttribute('src'),width:document.querySelector('#brandIcon img').naturalWidth})`);
 await click('.info [data-action="location-open"]');
 const location=await ev(`({title:document.querySelector('.modal h2')?.textContent,online:document.querySelector('#locationOnline')?.checked,kept:PhotoToolReview.debug().state.kept.length})`);
 location.success=location.title==='Ortszuordnung prüfen'&&location.online===false&&location.kept===keptBefore;
 await click('.modal [data-action="close-modal"]');
 const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 fs.writeFileSync(`${out}/chapter-scroll-after-undo.png`,Buffer.from(capture.result.data,'base64'));
 const snapshot=await ev('PhotoToolReview.debug().state');
 const result={success:cases.every(c=>c.violations.length===0)&&exceptions.length===0&&navigation.success&&location.success,photos:snapshot.photos.length,chapters:snapshot.chapters.length,selected:snapshot.kept.length,cases,navigation,logo,location,exceptions};
 fs.writeFileSync(`${out}/result.json`,JSON.stringify(result,null,2));
 console.log(JSON.stringify({success:result.success,photos:result.photos,chapters:result.chapters,cases:cases.map(c=>({case:c.case,violations:c.violations}))}));
 ws.close();
 if(!result.success)process.exitCode=2;
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true", help="Use the released 0.5.0 CSS")
    parser.add_argument("--compact", action="store_true", help="Only the two compact viewports plus functional checks")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output must be a new or empty QA directory")
    if not shutil.which("chromium") or not shutil.which("node"):
        parser.error("Chromium and Node are required")
    output.mkdir(parents=True, exist_ok=True)
    from photobook_curator import modern_review
    from photobook_curator.modern_review_session import ReviewSession
    if args.baseline:
        assets = output / "baseline-assets" / "web_review"
        shutil.copytree(Path(__file__).resolve().parents[1] / "photobook_curator/web_review", assets)
        css = subprocess.check_output(["git", "show", "b8da496:photobook_curator/web_review/style.css"])
        (assets / "style.css").write_bytes(css)
        package_assets = Path(__file__).resolve().parents[1] / "photobook_curator/assets"
        if package_assets.is_dir():
            shutil.copytree(package_assets, assets.parent / "assets")
        modern_review.files = lambda package: assets.parent
    session = ReviewSession(*create_fixture(output))
    server = modern_review.ReviewServer(session)
    profile = output / "chromium-profile"
    profile.mkdir()
    harness = output / "layout-check.cjs"
    harness.write_text(BROWSER_CHECK, encoding="utf-8")
    started = time.monotonic()
    with (output / "chromium.log").open("w") as log:
        browser = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            port_file = profile / "DevToolsActivePort"
            while not port_file.is_file():
                if browser.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Chromium did not become ready")
                time.sleep(.05)
            port = port_file.read_text().splitlines()[0]
            url = server.start()
            result = subprocess.run(["node", str(harness), port, url, str(output)],
                                    env={**os.environ, "PHOTO_QA_COMPACT": "1" if args.compact else "0"},
                                    capture_output=True, text=True, timeout=180)
            print(result.stdout or result.stderr)
            if (output / "result.json").is_file():
                data = json.loads((output / "result.json").read_text())
                data["elapsed_seconds"] = round(time.monotonic() - started, 3)
                data["baseline"] = args.baseline
                (output / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            return result.returncode
        finally:
            browser.terminate()
            browser.wait(timeout=8)
            server.close()
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
