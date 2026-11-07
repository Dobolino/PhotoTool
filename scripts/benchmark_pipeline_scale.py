"""Synthetic full-pipeline benchmark with repeated 24 MP JPEG templates.

Example (fixture and output stay in the explicitly chosen work directory):
  python scripts/benchmark_pipeline_scale.py generate --work-dir /tmp/phototool-bench
  python scripts/benchmark_pipeline_scale.py run --work-dir /tmp/phototool-bench
  python scripts/benchmark_pipeline_scale.py run --work-dir /tmp/phototool-bench \
      --target 200 --coverage .8 --max-per-day 18 --max-per-chapter 60 \
      --report-name report-japan-caps.json

Reuses ten geometric JPEG templates with EXIF dates over fourteen days and GPS
for Tokyo/Kyoto/Osaka. Files are physically copied, not hardlinked. This is not a
real-photo quality evaluation: repeated templates make reduction artificially
easy. Faces, embeddings, AI, network geocoding, HEIC and GUI are excluded.
Generation is separate from measured pipeline time. Peak RSS includes imports.
"""
from __future__ import annotations
import argparse
import json
import random
import sys
import time
from collections import Counter
try:
    import resource
except ImportError:
    resource = None
from pathlib import Path
from datetime import datetime, timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE: Path

def generate():
    from PIL import Image, ImageDraw
    import piexif
    from scripts.create_sample_dataset import make_exif
    inp=BASE/'input'
    if inp.exists() and any(inp.iterdir()):
        raise SystemExit('Input directory is not empty; use run or a new --work-dir.')
    inp.mkdir(parents=True,exist_ok=True)
    templates=[]
    for scene in range(10):
        rng=random.Random(2026+scene)
        image=Image.new('RGB',(750,500),(80+rng.randrange(80),100+rng.randrange(70),130+rng.randrange(80)))
        draw=ImageDraw.Draw(image)
        for shape in range(32):
            x=rng.randrange(700); y=rng.randrange(450)
            color=tuple(rng.randrange(30,240) for _ in range(3))
            draw.rectangle((x,y,min(749,x+rng.randrange(20,220)),min(499,y+rng.randrange(20,160))),fill=color)
        image=image.resize((6000,4000),Image.Resampling.BILINEAR)
        path=BASE/f'template-{scene}.jpg'; image.save(path,quality=90); image.close()
        templates.append(path.read_bytes())
    physical_bytes=0
    for index in range(args.photos):
        day=index*14//args.photos
        first=(day*args.photos+13)//14
        within=index-first
        scene=within%10
        burst_index=within//10
        dt=datetime(2026,4,1,9)+timedelta(days=day,minutes=scene*45,seconds=burst_index*2)
        lat,lon=(35.6812,139.7671) if day<5 else ((35.0116,135.7681) if day<10 else (34.6937,135.5023))
        path=inp/f'day-{day+1:02d}'/f'{index:04d}-scene-{scene}.jpg';path.parent.mkdir(exist_ok=True)
        piexif.insert(make_exif(dt,lat,lon,camera='Synthetic benchmark JPEG'),templates[scene],str(path))
        physical_bytes+=path.stat().st_size
    print(json.dumps({'files':args.photos,'pixels':[6000,4000],'days':14,'templates':10,'input_bytes':physical_bytes,'generation_seconds':round(time.perf_counter()-started,3)}))

def run():
    if not (BASE/'input').is_dir():
        raise SystemExit('Input directory is missing; run the generate stage first.')
    from photobook_curator.pipeline import PipelineConfig,run_pipeline
    out=BASE/'output'
    cfg=PipelineConfig(input_dir=BASE/'input',output_dir=out,target_n=args.target,coverage_intensity=args.coverage,max_per_day=args.max_per_day,max_per_chapter=args.max_per_chapter,geocode=False,ai_review=False,enable_faces=False,enable_content_clusters=False)
    cache_existed=(out/'analysis_cache.sqlite').is_file()
    begin=time.perf_counter()
    result=run_pipeline(cfg)
    elapsed=time.perf_counter()-begin
    photos=result['photo_objects']
    days=Counter(p.datetime_taken.date().isoformat() for p in photos if p.is_selected and p.datetime_taken)
    chapters=Counter(folder.split('/')[0] for _,folder,_ in result['order'])
    rss_mib=(round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1) if resource is not None else None)
    if rss_mib is not None and sys.platform=='darwin':
        rss_mib=round(rss_mib/1024,1)
    report={
        'kind':'synthetic_end_to_end_jpeg_no_inference',
        'photos':result['photos'],'source_pixels':[6000,4000],'days':14,'repeated_templates':10,
        'pipeline_seconds':round(elapsed,3),'process_peak_rss_mib':rss_mib,
        'cache_existed_before_run':cache_existed,'target':args.target,'coverage_intensity':args.coverage,'max_per_day':args.max_per_day,'max_per_chapter':args.max_per_chapter,
        'day_counts':dict(sorted(days.items())),'chapter_counts':dict(chapters),
        'day_cap_satisfied':args.max_per_day<=0 or all(n<=args.max_per_day for n in days.values()),
        'chapter_cap_satisfied':args.max_per_chapter<=0 or all(n<=args.max_per_chapter for n in chapters.values()),
        'selected':result['selected'],'regions':result['regions'],'candidates':result['candidates'],
        'unreadable':sum('unreadable' in p.flags for p in photos),
        'duplicates':sum(p.is_duplicate for p in photos),'burst_rejects':sum(p.is_burst_reject for p in photos),
        'selected_files':len(list((out/'selected').rglob('*.jpg'))),
        'csv_exists':(out/'photos_analysis.csv').is_file(),'overview_exists':(out/'inhaltsverzeichnis.md').is_file(),
        'enabled':['scan_EXIF_GPS','local_quality','document_filter','accidental_filter','weak_night_filter','local_aesthetic','pHash','bursts','regions','selection','CSV','copy_export'],
        'excluded':['faces','embeddings','AI','geocoding_network','HEIC','GUI'],
    }
    report['exported_count_matches_selection']=report['selected_files']==report['selected']
    path=BASE/args.report_name
    path.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not all(report[key] for key in ('day_cap_satisfied', 'chapter_cap_satisfied', 'exported_count_matches_selection')):
        raise RuntimeError('Benchmark constraint checks failed; see the JSON report.')

def main():
    global args, BASE, started
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['generate','run'])
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--photos',type=int,default=2000)
    parser.add_argument('--target',type=int,default=80)
    parser.add_argument('--coverage',type=float,default=0.0)
    parser.add_argument('--max-per-day',type=int,default=0)
    parser.add_argument('--max-per-chapter',type=int,default=0)
    parser.add_argument('--report-name',default='report.json')
    args=parser.parse_args()
    if args.photos<1 or args.target<1 or min(args.max_per_day,args.max_per_chapter)<0 or not 0<=args.coverage<=1:
        parser.error('positive photo/target counts, nonnegative caps and coverage in [0,1] required')
    BASE=args.work_dir.resolve()
    BASE.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    if args.mode=='generate':generate()
    else:run()


if __name__ == "__main__":
    main()
