from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from PIL import Image
import pytest
from photobook_curator.models import Photo, BookPlan, Region
from photobook_curator.review_gui import ReviewWindow
from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, apply_selection_draft
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv


def make_photos(tmp_path):
    result=[]
    for n in range(5):
        path=tmp_path/f'{n}.jpg'
        Image.new('RGB',(400,260),(50*n,100,120)).save(path)
        result.append(Photo(path=path,filename=path.name,region='Kyoto',
            chapter_folder='01_Kyoto/hauptteil' if n<2 else None,
            is_selected=n<2,is_candidate=True,width=400,height=260))
    return result


@pytest.fixture
def review(tmp_path, monkeypatch):
    try:
        root=tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable')
    root.withdraw()
    monkeypatch.setattr(ReviewWindow,'_open_large',lambda self:None)
    win=ReviewWindow(root,make_photos(tmp_path),BookPlan(regions=[Region(name='Kyoto',photo_indices=list(range(5)))]),tmp_path)
    win.withdraw();root.update()
    yield win,root
    if win.winfo_exists():
        win._close()
    root.destroy()


def test_preview_does_not_change_selection_and_added_variants_stay_separate(review):
    win,root=review
    folder=win._grid_folder
    win._expanded_alts.add(folder);win._render()
    variants=[h for h in win._hit_tiles if h['kind']=='photo' and h['mode']=='add']
    assert len(variants)==3
    chosen=variants[0]['idx']
    win._open_photo_preview(chosen,folder)
    assert win.kept=={0,1}
    assert set(win._slide_indices)=={2,3,4}
    win._slide_toggle_current()
    assert chosen in win.kept and win.photos[chosen].review_added
    assert win.photos[chosen].chapter_folder==folder
    win._slide_next()
    assert win._slide_indices[win._slide_pos]!=chosen
    win._exit_slideshow()
    titles=[win.canvas.itemcget(item,'text') for item in win.canvas.find_all()
            if win.canvas.type(item)=='text']
    assert 'Album-Auswahl · 2' in titles
    assert 'Hinzugefügt · 1' in titles
    win._undo()
    assert chosen not in win.kept and not win.photos[chosen].review_added
    win._redo()
    assert chosen in win._session_added


def test_pause_restores_preview_position_selection_and_variant_origin(review,tmp_path):
    win,root=review
    win._expanded_alts.add(win._grid_folder);win._render()
    win._open_photo_preview(2,win._grid_folder)
    win._slide_toggle_current();win._slide_next()
    current=win._slide_indices[win._slide_pos]
    win._close()
    fresh=make_photos(tmp_path)
    resumed=ReviewWindow(root,fresh,BookPlan(regions=[Region(name='Kyoto',photo_indices=list(range(5)))]),tmp_path)
    resumed.withdraw()
    try:
        assert resumed.kept=={0,1,2}
        assert resumed._session_added=={2}
        assert resumed._slideshow
        assert resumed._slide_indices[resumed._slide_pos]==current
        assert resumed._preview_pool==[2,3,4]
        resumed._exit_slideshow()
        assert resumed._preview_pool is None
    finally:
        resumed._close()


def test_draft_restores_removed_metadata_and_csv_persists_origin(tmp_path):
    photos=make_photos(tmp_path)
    photos[0].chapter_folder='02_Osaka/hauptteil'
    photos[0].flags=['manual_reject'];photos[0].review_added=True
    save_selection_draft(tmp_path,photos,{1},review_state={'folder':'02_Osaka/hauptteil'})
    fresh=make_photos(tmp_path)
    assert apply_selection_draft(fresh,load_selection_draft(tmp_path))=={1}
    assert fresh[0].chapter_folder=='02_Osaka/hauptteil'
    assert fresh[0].flags==['manual_reject'] and fresh[0].review_added
    path=tmp_path/'photos_analysis.csv';write_csv(fresh,path)
    assert load_photos_from_csv(path)[0].review_added


def test_save_error_keeps_window_open(review, monkeypatch):
    win,root=review
    def fail(*args,**kwargs):
        raise OSError('disk full')
    monkeypatch.setattr('photobook_curator.review_gui.save_selection_draft',fail)
    messages=[]
    monkeypatch.setattr('photobook_curator.review_gui.messagebox.showerror',lambda *a,**k:messages.append(a))
    win._close()
    assert win.winfo_exists() and messages and 'disk full' in messages[0][1]
    monkeypatch.undo()


def test_open_output_folder_uses_stored_analysis_without_pipeline(tmp_path,monkeypatch):
    from photobook_curator.gui import PhotobookApp
    folder=tmp_path/'existing';folder.mkdir()
    write_csv(make_photos(tmp_path),folder/'photos_analysis.csv')
    chosen=[]
    fake=SimpleNamespace(output_var=SimpleNamespace(set=chosen.append),_open_review=lambda:chosen.append('review'))
    monkeypatch.setattr('photobook_curator.gui.filedialog.askdirectory',lambda **_:str(folder))
    PhotobookApp._open_existing_review(fake)
    assert chosen==[str(folder),'review']


def test_return_from_variants_restores_album_photo_after_adding_and_restart(review,tmp_path):
    win,root=review
    win._open_photo_preview(1,win._grid_folder)
    win._alt_idx=2
    win._preview_alternatives()
    assert win._preview_kind=='variants'
    win._slide_toggle_current()
    win._close()
    resumed=ReviewWindow(root,make_photos(tmp_path),BookPlan(regions=[Region(name='Kyoto',photo_indices=list(range(5)))]),tmp_path)
    resumed.withdraw()
    try:
        assert resumed._preview_kind=='variants' and resumed._album_return
        resumed._return_to_album_slideshow()
        assert resumed._slideshow and resumed._preview_kind=='album'
        assert resumed._slide_indices[resumed._slide_pos]==1
        assert resumed._slide_indices==[0,1]
        assert 2 in resumed.kept
    finally:
        resumed._close()
