"""Explain recorded selection evidence and export local, self-contained reports.

The report distinguishes the latest automatic decision from the current review
selection. It never reads image pixels or reconstructs ranking reasons from a
score. Missing provenance remains explicitly unknown.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
from html import escape
import math
import ntpath
import os
from pathlib import Path
import tempfile
from typing import Iterable, Sequence

from .i18n import get_language
from .models import Photo
from .location_schema import normalize_location_evidence
from .trace_schema import normalize_selection_trace


@dataclass(frozen=True)
class AuditComparison:
    peer_index: int | None
    peer_path: str
    filename: str
    explanation: str


@dataclass(frozen=True)
class PhotoAudit:
    photo_index: int
    filename: str
    path: str
    selected: bool
    chapter: str
    day: str
    primary_code: str
    primary_reasons: tuple[str, ...]
    recorded_decisions: tuple[str, ...]
    quality_hints: tuple[str, ...]
    comparisons: tuple[AuditComparison, ...]
    provenance_available: bool
    automatic_selected: bool | None
    provenance_note: str
    manual_decision: str
    manual_reason: str
    technical_score: float
    final_score: float
    needs_review: bool
    automatic_reasons: tuple[str, ...] = ()
    location_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportSnapshot:
    photos: tuple[PhotoAudit, ...]
    summary: dict
    generated_at: str
    language: str
    project_name: str


def _language(language: str | None) -> str:
    return 'en' if (language or get_language()) == 'en' else 'de'


def _tr(de: str, en: str, language: str) -> str:
    return en if language == 'en' else de


def _number(value, digits=1) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return '?'
    return str(value) if isinstance(value, int) else f'{value:.{digits}f}'


def _score(value) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _source_key(value) -> str:
    raw = str(value)
    if ntpath.splitdrive(raw)[0] or '\\' in raw:
        return ntpath.normcase(ntpath.normpath(raw))
    return os.path.normcase(os.path.normpath(raw))


def _filename(path: str) -> str:
    return ntpath.basename(path.replace('/', '\\')) or path


def _event_text(event: dict, language: str) -> str:
    code, d = event['code'], event['details']
    templates = {
        'eligibility_rejected': ('Durch einen aktivierten Vorfilter ausgeschlossen.', 'Excluded by an enabled pre-filter.'),
        'chapter_budget': ('Kapitelkontingent festgelegt.', 'Chapter capacity allocated.'),
        'candidate_selected': ('In die Vorauswahl für die weitere Bewertung aufgenommen.', 'Included in the shortlist for further assessment.'),
        'candidate_not_selected': ('Ausserhalb der begrenzten Vorauswahl geblieben.', 'Outside the limited shortlist.'),
        'score_computed': ('Gesamtbewertung aus den gespeicherten Einzelbewertungen berechnet.', 'Overall score calculated from the stored component scores.'),
        'chapter_pool': ('Verfügbare Bilder für diesen Kapitel-Auswahlschritt bestimmt.', 'Available photos for this chapter selection step determined.'),
        'food_allocation': ('Plätze zwischen Hauptteil und Essensbildern aufgeteilt.', 'Places divided between main and food photographs.'),
        'day_allocation': ('Plätze für diesen Aufnahmetag zugeteilt.', 'Places allocated to this capture day.'),
        'selection_ranked': ('Im Auswahlschritt nach Bewertung und Szenenmischung eingeordnet.', 'Ranked in this selection step by score and scene mix.'),
        'histogram_rejected': ('In diesem Schritt wegen zu grosser Farbähnlichkeit zu einem bereits gewählten Bild übersprungen.', 'Skipped in this step because its colour histogram was too similar to an already chosen photo.'),
        'landmark_limit_rejected': ('In diesem Schritt war die Grenze für Sehenswürdigkeitsbilder erreicht.', 'The landmark-photo limit was reached in this step.'),
        'people_balance_evaluated': ('Gewichtung zur ausgeglicheneren Darstellung von Personen berücksichtigt.', 'Weighting for a more balanced representation of people considered.'),
        'diversity_selected': ('Im Schritt für Bildvielfalt innerhalb des Kontingents ausgewählt.', 'Chosen within the quota during the diversity selection step.'),
        'diversity_fallback_selected': ('Zum Füllen freier Plätze aufgenommen; der Ähnlichkeitsfilter wurde dabei gelockert.', 'Included to fill vacant places; the similarity filter was relaxed.'),
        'diversity_quota_exhausted': ('Im Auswahlschritt waren die verfügbaren Plätze bereits belegt.', 'The available places in this selection step were already filled.'),
        'forced_keep': ('Aufgrund einer ausdrücklich geschützten Behalten-Vorgabe aufgenommen.', 'Included because of an explicit protected keep instruction.'),
        'forced_quota_displaced': ('Ein Platz wurde für ein geschütztes oder dauerhaft behaltenes Bild benötigt.', 'A place was needed for a protected or permanently kept photo.'),
        'story_role_selected': ('Für eine bislang fehlende Bildrolle im Kapitel aufgenommen.', 'Included to represent a previously missing picture role in the chapter.'),
        'story_role_replaced': ('Für eine vielfältigere Bildmischung im Kapitel durch ein anderes Bild ersetzt.', 'Replaced by another photo to improve the mix of picture roles in the chapter.'),
        'cap_day_removed': ('Wegen der albumweiten Tagesgrenze aus der automatischen Auswahl entfernt.', 'Removed from the automatic selection because of the album-wide day limit.'),
        'cap_chapter_removed': ('Wegen der Kapitelgrenze aus der automatischen Auswahl entfernt.', 'Removed from the automatic selection because of the chapter limit.'),
        'cap_refill_selected': ('Nach Anwendung der Grenzen auf einen noch freien Platz nachgerückt.', 'Filled a remaining place after the limits were applied.'),
        'cap_refill_blocked': ('Beim Nachfüllen durch eine erreichte Grenze nicht aufgenommen.', 'Not included during refill because a limit had been reached.'),
        'selection_finalized': ('Automatische Auswahl für dieses Bild abgeschlossen.', 'Automatic selection for this photo completed.'),
    }
    if code not in templates:
        return _tr('Aufgezeichneter Auswahlschritt wird von dieser Version noch nicht übersetzt',
                   'Recorded selection step is not yet translated by this version', language) + f': {code}'
    result = _tr(*templates[code], language)
    if code == 'eligibility_rejected' and d.get('forced_override') is True:
        result = _tr('Vorfilter hätten dieses Bild ausgeschlossen; eine ausdrückliche Behalten-Vorgabe hat sie überstimmt.',
                     'Pre-filters would have excluded this photo; an explicit keep instruction overrode them.', language)
    elif code == 'histogram_rejected' and d.get('comparison_available') is not True:
        result = _tr('Im Ähnlichkeits-Auswahlschritt übersprungen; ein gemessener Bildvergleich ist nicht aufgezeichnet.',
                     'Skipped in the similarity selection step; no measured image comparison is recorded.', language)
    facts = []
    labels = {
        'quota': ('Kontingent', 'quota'), 'day_quota': ('Tageskontingent', 'day quota'),
        'candidate_limit': ('Vorauswahlgrenze', 'shortlist limit'),
        'eligible_rank': ('Rang unter geeigneten Bildern', 'rank among eligible photos'),
        'day_rank': ('Rang am Tag', 'rank within the day'), 'rank': ('Rang', 'rank'),
        'score_rank': ('Bewertungsrang', 'score rank'), 'mixed_position': ('Position nach Szenenmischung', 'position after scene mixing'),
        'selection_position': ('Position im Auswahlschritt', 'position in selection step'),
        'chapter_quota': ('Kapitelkontingent', 'chapter quota'), 'selected_count': ('Bereits gewählt', 'already selected'),
        'capacity': ('Geeignete Bilder', 'eligible photos'), 'forced': ('Geschützte Plätze', 'protected places'),
        'limit': ('Grenze', 'limit'), 'count': ('Anzahl', 'count'),
        'similarity': ('Gemessene Ähnlichkeit', 'measured similarity'), 'threshold': ('Schwelle', 'threshold'),
        'penalty': ('Personengewichtung', 'people weighting'), 'adjusted_score': ('Gewichtete Bewertung', 'weighted score'),
        'food_ratio': ('Essensanteil', 'food ratio'), 'technical_score': ('Technische Bewertung', 'technical score'),
        'final_score': ('Gesamtbewertung', 'overall score'), 'score': ('Bewertung', 'score'),
        'aesthetic_score': ('Ästhetikbewertung', 'aesthetic score'),
        'technical_weight': ('Gewicht Technik', 'technical weight'), 'aesthetic_weight': ('Gewicht Ästhetik', 'aesthetic weight'),
        'book_position': ('Albumposition', 'album position'),
    }
    for key, pair in labels.items():
        if (key in d and isinstance(d[key], (int, float)) and not isinstance(d[key], bool)
                and (key not in {'similarity', 'threshold'} or code != 'histogram_rejected' or d.get('comparison_available') is True)):
            facts.append(f'{_tr(*pair, language)}: {_number(d[key], 3 if key in {"similarity", "threshold"} else 1)}')
    for key, de, en in (('day', 'Tag', 'Day'), ('kind', 'Bereich', 'Section'), ('role', 'Bildrolle', 'Picture role')):
        if isinstance(d.get(key), str):
            facts.append(f'{_tr(de,en,language)}: {d[key]}')
    filters = d.get('filters')
    if isinstance(filters, list):
        names = {
            'is_duplicate': ('Duplikatmarkierung', 'duplicate marker'), 'duplicate': ('Duplikatmarkierung', 'duplicate marker'),
            'is_burst_reject': ('Serienvariante', 'burst variant'), 'burst': ('Serienvariante', 'burst variant'),
            'is_aside': ('Dokument/Screenshot', 'document/screenshot'), 'aside': ('Dokument/Screenshot', 'document/screenshot'),
            'finger_on_lens': ('Finger vor der Linse', 'finger covering the lens'),
            'is_accidental': ('Mögliche Fehlaufnahme', 'possible accidental shot'),
            'is_weak_night': ('Schwache Nachtaufnahme', 'weak night photograph'),
            'unreadable': ('Datei nicht lesbar', 'unreadable file'), 'manual_reject': ('Dauerhaft abgelehnt', 'permanently rejected'),
            'manual_decision': ('Manuelle Vorgabe', 'manual instruction'),
        }
        facts.extend(_tr(*names.get(value, (str(value), str(value))), language) for value in filters if isinstance(value, str))
    formula = d.get('formula')
    if isinstance(formula, str):
        facts.append(formula)
    if code == 'cap_refill_blocked':
        constraints = {'folder_budget': ('Kapitelkontingent', 'chapter quota'),
                       'day_limit': ('Tagesgrenze', 'day limit'), 'chapter_limit': ('Kapitelgrenze', 'chapter limit')}
        if isinstance(d.get('constraint'), str) and d['constraint'] in constraints:
            facts.append(_tr(*constraints[d['constraint']], language))
    if code == 'forced_keep':
        for key, de, en in [('day_limit_exceeded', 'Tagesgrenze wegen Behalten-Vorgabe überschritten', 'Day limit exceeded by the keep instruction'),
                             ('chapter_limit_exceeded', 'Kapitelgrenze wegen Behalten-Vorgabe überschritten', 'Chapter limit exceeded by the keep instruction')]:
            if d.get(key) is True:
                facts.append(_tr(de, en, language))
    if code == 'score_computed':
        modifier_names = {'ai_keep_rejected': ('KI-Behalten-Empfehlung abgelehnt', 'AI keep recommendation rejected'),
                          'quality_issue': ('Qualitätshinweis', 'quality hint'), 'bad_face': ('Gesichtsqualität', 'face quality'),
                          'landmark': ('Sehenswürdigkeit', 'landmark'), 'smiling': ('Lächeln', 'smiling'),
                          'not_looking_at_camera': ('Blick nicht zur Kamera', 'not looking at camera'),
                          'group_photo': ('Gruppenfoto', 'group photograph')}
        modifiers = d.get('modifiers')
        for modifier in modifiers if isinstance(modifiers, list) else []:
            if (isinstance(modifier, dict) and isinstance(modifier.get('operation'), str)
                    and modifier['operation'] in {'multiply', 'add'}):
                name = str(modifier.get('code', ''))
                label = _tr(*modifier_names.get(name, (name, name)), language)
                operator = '×' if modifier['operation'] == 'multiply' else '+'
                facts.append(f'{label}: {operator}{_number(modifier.get("value"), 2)}')
    return result + (' ' + ' · '.join(facts) if facts else '')


def _quality_hints(photo: Photo, language: str) -> tuple[str, ...]:
    hints = []
    attributes = (
        ('is_duplicate', 'Als ähnlich/Duplikat markiert.', 'Marked as similar/duplicate.'),
        ('is_burst_reject', 'Als nicht gewählte Serienvariante markiert.', 'Marked as an omitted burst variant.'),
        ('is_aside', 'Als Dokument oder Screenshot im separaten Pool markiert.', 'Marked as a document or screenshot in the separate pool.'),
        ('finger_on_lens', 'Hinweis auf einen Finger vor der Linse.', 'Possible finger covering the lens.'),
        ('eyes_closed', 'Hinweis auf geschlossene Augen.', 'Possible closed eyes.'),
        ('bad_face', 'Hinweis auf problematische Gesichtsqualität.', 'Possible face-quality issue.'),
        ('face_cut_off', 'Hinweis auf angeschnittenes Gesicht.', 'Possible cropped face.'),
        ('face_too_small', 'Gesicht für die Qualitätsprüfung sehr klein.', 'Face is very small for quality assessment.'),
        ('is_accidental', 'Als mögliche Fehlaufnahme markiert.', 'Marked as a possible accidental shot.'),
        ('is_weak_night', 'Als schwache Nachtaufnahme markiert.', 'Marked as a weak night photograph.'),
        ('is_too_dark', 'Belichtungshinweis: dunkel.', 'Exposure hint: dark.'),
        ('is_overexposed', 'Belichtungshinweis: überbelichtet.', 'Exposure hint: overexposed.'),
    )
    for attr, de, en in attributes:
        if getattr(photo, attr, False):
            hints.append(_tr(de, en, language))
    if 'unreadable' in photo.flags:
        hints.append(_tr('Datei war bei der Analyse nicht lesbar.', 'The file was unreadable during analysis.', language))
    if photo.quality_issue:
        hints.append(str(photo.quality_issue))
    if photo.ai_reviewed:
        hints.append(_tr('Eine KI-Bewertung ist gespeichert.', 'An AI assessment is stored.', language))
    if not photo.datetime_taken:
        hints.append(_tr('Aufnahmedatum fehlt.', 'Capture date is missing.', language))
    return tuple(dict.fromkeys(hints))


def _location_reasons(photo: Photo, language: str) -> tuple[str, ...]:
    evidence = normalize_location_evidence(getattr(photo, 'location_evidence', {}))
    labels = []
    if photo.region or photo.country:
        labels.append(_tr('Gespeicherter Ort: ', 'Stored location: ', language)
                      + ' · '.join(str(value) for value in (photo.region, photo.country) if value))
    sources = {
        'gps_online': ('Aus den GPS-Koordinaten dieses Bildes mit Online-Ortsauflösung bestimmt.', 'Determined from this photo’s GPS coordinates using online geocoding.'),
        'gps_offline': ('Aus den GPS-Koordinaten dieses Bildes der nächsten bekannten Stadt zugeordnet (Offline-Näherung bis 25 km, keine Stadtteil-Erkennung).', 'Assigned from this photo’s GPS coordinates to the nearest known city (offline approximation within 25 km, no district detection).'),
        'time_nearest': ('Vom zeitlich nächstgelegenen Bild mit bekanntem Ort übernommen; kein GPS-Nachweis für dieses Bild.', 'Inherited from the nearest photo with a known location in time; this is not GPS evidence for this photo.'),
        'manual': ('Als manuelle Ortszuordnung aufgezeichnet.', 'Recorded as a manual location assignment.'),
        'unknown': ('Keine verlässliche Ortsquelle aufgezeichnet.', 'No reliable location source recorded.'),
        'legacy': ('Ältere Ortszuordnung ohne aufgezeichneten Herkunftsnachweis.', 'Older location assignment without recorded provenance.'),
    }
    source = evidence.get('source')
    if source in sources:
        labels.append(_tr(*sources[source], language))
    else:
        labels.append(_tr('Die Herkunft dieser Ortszuordnung wurde nicht aufgezeichnet.', 'The source of this location assignment was not recorded.', language))
    if photo.landmark:
        labels.append(_tr('Motivbeschreibung (kein Ortsnachweis): ', 'Subject description (not location evidence): ', language) + str(photo.landmark))
    if {"manual_chapter", "manual_chapter_override"}.intersection(photo.flags):
        labels.append(_tr('Das Kapitel wurde manuell zugewiesen und wird unabhängig vom ermittelten Ort beibehalten.',
                          'The chapter was assigned manually and is preserved independently of the determined location.', language))
    if source == 'time_nearest' and evidence.get('anchor_path'):
        anchor = str(evidence['anchor_path'])
        description = _tr('Referenzbild: ', 'Reference photo: ', language) + _filename(anchor)
        if isinstance(evidence.get('delta_hours'), (int, float)):
            description += _tr(' · Zeitabstand: ', ' · Time difference: ', language) + _number(evidence['delta_hours'], 2) + ' h'
        labels.append(description)
    warnings = {
        'conflicting_anchors': ('Nahe Referenzbilder weisen auf unterschiedliche Orte hin; Zuordnung prüfen.', 'Nearby reference photos indicate different locations; review the assignment.'),
        'no_nearby_anchor': ('Kein zeitlich nahes Referenzbild mit bekanntem Ort vorhanden.', 'No nearby reference photo with a known location was available.'),
        'missing_datetime': ('Ohne Aufnahmedatum ist keine zeitliche Ortszuordnung möglich.', 'A location cannot be assigned by time without a capture date.'),
        'gps_unresolved': ('GPS-Koordinaten konnten keinem Ort zugeordnet werden.', 'The GPS coordinates could not be resolved to a location.'),
        'invalid_gps': ('Ungültige GPS-Koordinaten aufgezeichnet.', 'Invalid GPS coordinates recorded.'),
    }
    warning = evidence.get('warning') or evidence.get('warning_code')
    if isinstance(warning, str) and warning in warnings:
        labels.append(_tr(*warnings[warning], language))
    candidates = evidence.get('candidates')
    if warning == 'conflicting_anchors' and isinstance(candidates, list):
        for candidate in candidates[:2]:
            if not isinstance(candidate, dict):
                continue
            parts = [str(candidate.get(key)) for key in ('region', 'country') if candidate.get(key)]
            if candidate.get('anchor_path'):
                parts.append(_filename(str(candidate['anchor_path'])))
            if parts:
                labels.append(_tr('Mögliche Referenz: ', 'Possible reference: ', language) + ' · '.join(parts))
    return tuple(labels)


def _build_photo(photo: Photo, index: int, selected: bool, lookup: dict[str, int],
                 photos: Sequence[Photo], language: str) -> PhotoAudit:
    trace = normalize_selection_trace(getattr(photo, 'selection_trace', {}))
    events = trace.get('events', [])
    final = trace.get('final_reason', '')
    decisive = next((event for event in reversed(events) if event['code'] == final), None)
    complete = trace.get('status') in {'selected', 'not_selected'} and decisive is not None
    finalized = next((event for event in reversed(events) if event['code'] == 'selection_finalized'), None)
    recorded_status = (trace.get('status') in {'selected', 'not_selected'}
                       and (complete or (final in {'final_selected', 'final_not_selected'} and finalized
                            and finalized['details'].get('selected') is (trace['status'] == 'selected'))))
    automatic_selected = (trace['status'] == 'selected') if recorded_status else None
    automatic_reasons = ((_event_text(decisive, language),) if complete else
        (_tr('Der automatische Endstatus ist aufgezeichnet; ein genauer Auswahlgrund fehlt.',
             'The final automatic status is recorded; a specific selection reason is missing.', language),)
        if recorded_status else ())
    decision = getattr(photo, 'manual_decision', 'auto')
    manual_reason = str(getattr(photo, 'decision_reason', '') or '')
    primary, primary_code = [], final if complete else 'not_recorded'
    if photo.is_favorite and selected:
        primary_code = 'favorite'
        primary.append(_tr('Favoritenschutz ist aktiv; das Bild ist aktuell im Album.', 'Favorite protection is active; this photo is currently in the album.', language))
    elif decision == 'keep' and selected:
        primary_code = 'manual_keep'
        primary.append(_tr('Auf deinen Wunsch dauerhaft behalten.', 'Permanently kept at your request.', language))
    elif decision == 'reject' and not selected:
        primary_code = 'manual_reject'
        primary.append(_tr('Auf deinen Wunsch dauerhaft ausgeschlossen.', 'Permanently excluded at your request.', language))
    elif recorded_status and selected == automatic_selected:
        primary.extend(automatic_reasons)
    elif recorded_status:
        primary_code = 'review_changed'
        primary.append(_tr('Die aktuelle Auswahl weicht vom letzten automatischen Ergebnis ab.', 'The current selection differs from the last automatic result.', language))
    elif trace and trace.get('status') == 'pending':
        primary_code = 'analysis_pending'
        primary.append(_tr('Der gespeicherte Lauf hat noch keine endgültige Auswahlentscheidung protokolliert.', 'The saved run has not recorded a final selection decision yet.', language))
    else:
        primary.append(_tr('Der genaue automatische Auswahlgrund wurde für dieses Bild nicht aufgezeichnet.', 'The exact automatic selection reason was not recorded for this photo.', language))
    if manual_reason and decision != 'auto':
        primary.append(_tr('Deine Begründung: ', 'Your reason: ', language) + manual_reason)
    inconsistent = ((decision == 'keep' or photo.is_favorite) and not selected) or (decision == 'reject' and selected and not photo.is_favorite)
    if inconsistent:
        primary.append(_tr('Aktuelle Auswahl und gespeicherte Schutz-/Ablehnungsregel widersprechen sich; bitte prüfen.', 'The current selection conflicts with the stored keep/reject rule; please review.', language))
    if recorded_status:
        stamp = trace.get('context', {}).get('started_at', '')
        provenance_note = _tr('Tatsächlich protokollierter automatischer Lauf', 'Recorded automatic run', language)
        if stamp:
            provenance_note += f' · {stamp}'
        if not complete:
            provenance_note += _tr(' · Endstatus bekannt, genauer Auswahlgrund fehlt.', ' · Final status known, specific selection reason missing.', language)
    else:
        provenance_note = _tr('Keine vollständige Entscheidungsaufzeichnung. Vorhandene Hinweise sind keine nachträglich erfundenen Auswahlgründe.', 'No complete decision record. Stored hints are not reconstructed selection reasons.', language)
    history = tuple(_event_text(event, language) for event in events)
    comparisons = []
    seen = set()
    for event in events:
        details = event['details']
        paths = [details['peer_path']] if isinstance(details.get('peer_path'), str) else []
        if isinstance(details.get('peer_paths'), list):
            paths.extend(details['peer_paths'])
        for peer in paths:
            key = _source_key(peer)
            if key == _source_key(photo.path) or (event['code'], key) in seen:
                continue
            seen.add((event['code'], key))
            peer_index = lookup.get(key)
            comparisons.append(AuditComparison(peer_index, peer,
                photos[peer_index].filename if peer_index is not None else _filename(peer),
                _event_text(event, language)))
    hints = _quality_hints(photo, language)
    location = normalize_location_evidence(getattr(photo, 'location_evidence', {}))
    needs_review = bool(inconsistent or (selected and any((photo.bad_face, photo.eyes_closed,
        photo.quality_issue, photo.is_duplicate, photo.is_burst_reject, photo.is_too_dark, photo.is_overexposed,
        photo.face_cut_off, photo.face_too_small, photo.finger_on_lens, photo.is_accidental,
        photo.is_weak_night, photo.is_aside, not photo.datetime_taken, 'unreadable' in photo.flags)))
        or location.get('warning') or location.get('warning_code') or not complete)
    chapter = (photo.chapter_folder or photo.region or _tr('Ohne Kapitel', 'No chapter', language)).split('/')[0]
    day = photo.datetime_taken.date().isoformat() if photo.datetime_taken else _tr('Ohne Datum', 'No date', language)
    return PhotoAudit(index, str(photo.filename), str(photo.path), selected, chapter, day, primary_code,
        tuple(primary), history, hints, tuple(comparisons), complete, automatic_selected, provenance_note,
        decision, manual_reason, _score(photo.technical_score), _score(photo.final_score), needs_review,
        automatic_reasons, _location_reasons(photo, language))


def build_photo_audit(photos: Sequence[Photo], index: int, selected_override: bool | None = None,
                      *, language: str | None = None) -> PhotoAudit:
    if not 0 <= index < len(photos):
        raise IndexError('Photo index outside report snapshot')
    lookup = {_source_key(photo.path): i for i, photo in enumerate(photos)}
    photo = photos[index]
    return _build_photo(photo, index, photo.is_selected if selected_override is None else bool(selected_override),
                        lookup, photos, _language(language))


def build_audit_report(photos: Sequence[Photo], kept: Iterable[int] | None = None,
                       *, language: str | None = None, project_name: str | None = None) -> ReportSnapshot:
    language = _language(language)
    selected = None if kept is None else frozenset(kept)
    lookup = {_source_key(photo.path): i for i, photo in enumerate(photos)}
    audits = tuple(_build_photo(photo, i, photo.is_selected if selected is None else i in selected,
                               lookup, photos, language) for i, photo in enumerate(photos))
    reason_labels = {}
    for item in audits:
        # Aggregate causes rather than making one bucket for every rank/score.
        label = item.primary_reasons[0].partition('. ')[0].rstrip('.') + '.'
        reason_labels[label] = reason_labels.get(label, 0) + 1
    summary = {
        'total': len(audits), 'selected': sum(item.selected for item in audits),
        'omitted': sum(not item.selected for item in audits),
        'needs_review': sum(item.needs_review for item in audits),
        'recorded': sum(item.provenance_available for item in audits),
        'not_recorded': sum(not item.provenance_available for item in audits),
        'chapters': dict(Counter(item.chapter for item in audits)),
        'days': dict(Counter(item.day for item in audits)),
        'chapters_selected': dict(Counter(item.chapter for item in audits if item.selected)),
        'days_selected': dict(Counter(item.day for item in audits if item.selected)),
        'reasons': dict(Counter(item.primary_code for item in audits)),
        'reason_labels': reason_labels,
    }
    return ReportSnapshot(audits, summary, datetime.now(timezone.utc).isoformat(timespec='seconds'),
                          language, str(project_name or _tr('PhotoTool Prüfbericht', 'PhotoTool selection audit', language)))


def _atomic_text(path: Path, callback) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent,
                                         prefix=f'.{path.stem}-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            callback(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def _csv_safe(value) -> str:
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


def _write_csv(snapshot: ReportSnapshot, path: Path) -> Path:
    def write(stream):
        writer = csv.writer(stream)
        writer.writerow(['photo_index', 'filename', 'path', 'selected', 'chapter', 'day', 'primary_reason_code',
            'primary_reasons', 'automatic_selected', 'provenance_available', 'manual_decision', 'manual_reason',
            'technical_score', 'final_score', 'quality_hints', 'recorded_decisions', 'comparison_files',
            'automatic_reasons', 'location_reasons'])
        for item in snapshot.photos:
            row = [item.photo_index, item.filename, item.path, item.selected, item.chapter, item.day, item.primary_code,
                '\n'.join(item.primary_reasons), '' if item.automatic_selected is None else item.automatic_selected,
                item.provenance_available, item.manual_decision, item.manual_reason, item.technical_score,
                item.final_score, '\n'.join(item.quality_hints), '\n'.join(item.recorded_decisions),
                '\n'.join(comparison.peer_path for comparison in item.comparisons),
                '\n'.join(item.automatic_reasons), '\n'.join(item.location_reasons)]
            writer.writerow([_csv_safe(cell) for cell in row])
    return _atomic_text(path, write)


def write_audit_csv(photos: Sequence[Photo], csv_path: Path, kept: Iterable[int] | None = None,
                    *, language: str | None = None, project_name: str | None = None) -> Path:
    return _write_csv(build_audit_report(photos, kept, language=language, project_name=project_name), csv_path)


def write_audit_report(photos: Sequence[Photo], html_path: Path, kept: Iterable[int] | None = None,
                       csv_path: Path | None = None, *, language: str | None = None,
                       project_name: str | None = None) -> Path:
    if csv_path is not None and Path(html_path).resolve() == Path(csv_path).resolve():
        raise ValueError('HTML and CSV report paths must differ')
    snapshot = build_audit_report(photos, kept, language=language, project_name=project_name)
    result = _atomic_text(html_path, lambda stream: _write_html(snapshot, stream))
    if csv_path is not None:
        _write_csv(snapshot, csv_path)
    return result


def _write_html(snapshot: ReportSnapshot, stream) -> None:
    lang = snapshot.language
    tr = lambda de, en: _tr(de, en, lang)
    e = lambda value: escape(str(value), quote=True)
    title = e(snapshot.project_name)
    stream.write(f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; img-src 'none'">
<title>{title}</title><style>
:root{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#e8eaf2;background:#12141c;color-scheme:dark}}*{{box-sizing:border-box}}body{{max-width:1160px;margin:0 auto;padding:32px 20px}}h1{{font-size:30px;margin-bottom:8px}}h2{{font-size:20px}}h3{{font-size:17px}}p,li{{line-height:1.55}}.muted{{color:#aeb7ca}}.intro,.photo,.summary{{background:#1c2030;border:1px solid #333c54;border-radius:10px;padding:20px;margin:16px 0}}.summary{{display:flex;gap:24px;flex-wrap:wrap}}.metric strong{{font-size:27px;display:block}}label{{display:block}}input,select,button{{font:inherit;background:#262c40;color:#e8eaf2;border:1px solid #56627c;border-radius:5px;padding:10px}}.controls{{display:flex;gap:12px;flex-wrap:wrap;align-items:end;position:sticky;top:0;padding:14px;background:#12141c;z-index:2}}.controls label:first-child{{flex:1;min-width:220px}}input{{width:100%;margin-top:5px}}.badge{{display:inline-block;border-radius:16px;padding:4px 10px;background:#35305b;margin:0 8px 5px 0}}.omitted{{background:#343c4b}}.warning{{color:#ffcf87}}code{{overflow-wrap:anywhere;font-size:12px;color:#bdc6d9}}.photo h2{{margin:0 0 9px;overflow-wrap:anywhere}}details{{border-top:1px solid #39435a;margin-top:14px;padding-top:13px}}summary{{cursor:pointer}}a{{color:#c4b9ff}}.columns{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}[hidden]{{display:none!important}}.histogram{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}}.histogram ul{{padding-left:18px;max-height:220px;overflow:auto}}@media print{{:root{{color:#111;background:white;color-scheme:light}}body{{max-width:none;padding:0}}.controls{{display:none}}.intro,.summary,.photo{{background:white;border-color:#aaa;break-inside:avoid}}.muted,code{{color:#333}}.badge{{border:1px solid #aaa;background:white}}.warning{{color:#663700}}}}
</style></head><body><header><h1>{title}</h1><p class="muted">{e(tr('Momentaufnahme deiner Auswahl', 'Snapshot of your selection'))} · {e(snapshot.generated_at)}</p></header>
<section class="intro"><p>{e(tr('Dieser Bericht trennt tatsächliche automatische Auswahlentscheidungen, deine aktuellen Entscheidungen und gespeicherte Qualitätshinweise. Eine niedrige Bewertung beweist nicht, dass ein Foto für dich unwichtig ist.', 'This report separates recorded automatic selection decisions, your current decisions and stored quality hints. A low score does not prove that a photograph is unimportant to you.'))}</p><p class="muted">{e(tr('Lokale Datei ohne externe Dienste, Schrift- oder Bildabrufe. Sie enthält Dateinamen und Quellpfade; nur teilen, wenn diese Informationen mitgeteilt werden sollen.', 'Local file with no external services, font or image requests. It contains file names and source paths; share it only if those details should be disclosed.'))}</p></section>
<section class="summary">''')
    for key, de, en in [('total', 'Bilder', 'Photos'), ('selected', 'Im Album', 'In album'),
                        ('omitted', 'Nicht im Album', 'Outside album'), ('recorded', 'Mit Entscheidungsprotokoll', 'With decision record'),
                        ('needs_review', 'Prüfhinweise', 'Review hints')]:
        stream.write(f'<div class="metric"><strong>{snapshot.summary[key]}</strong>{e(tr(de,en))}</div>')
    stream.write('</section><section class="intro histogram">')
    for key, de, en in [('chapters','Kapitel · alle analysierten Bilder','Chapters · all analyzed photos'),
                        ('days','Aufnahmetage · alle analysierten Bilder','Capture days · all analyzed photos'),
                        ('reason_labels','Aktuelle Auswahlgründe','Current selection reasons')]:
        stream.write(f'<div><h2>{e(tr(de,en))}</h2><ul>')
        for name, count in snapshot.summary[key].items():
            amount = (f'{snapshot.summary[key + "_selected"].get(name, 0)} / {count} '
                      + tr('im Album', 'in album') if key in {'chapters', 'days'} else str(count))
            stream.write(f'<li>{e(name)}: {e(amount)}</li>')
        stream.write('</ul></div>')
    stream.write(f'''</section><section class="controls"><label>{e(tr('Bild, Kapitel, Tag oder Grund suchen','Search photo, chapter, day or reason'))}<input id="query" type="search" autocomplete="off"></label><label>{e(tr('Anzeigen','Show'))}<br><select id="filter"><option value="all">{e(tr('Alle Bilder','All photos'))}</option><option value="selected">{e(tr('Im Album','In album'))}</option><option value="omitted">{e(tr('Nicht im Album','Outside album'))}</option><option value="review">{e(tr('Mit Prüfhinweisen','With review hints'))}</option><option value="legacy">{e(tr('Ohne Entscheidungsprotokoll','Without decision record'))}</option></select></label><button id="expand" type="button">{e(tr('Details ein-/ausblenden','Toggle details'))}</button><span id="visible" aria-live="polite"></span></section><main>''')
    for item in snapshot.photos:
        status = tr('Im Album', 'In album') if item.selected else tr('Nicht im Album', 'Outside album')
        stream.write(f'<article class="photo" id="photo-{item.photo_index}" data-selected="{int(item.selected)}" data-review="{int(item.needs_review)}" data-recorded="{int(item.provenance_available)}">')
        stream.write(f'<h2>{e(item.filename)}</h2><span class="badge {"" if item.selected else "omitted"}">{e(status)}</span>')
        stream.write(f'<span class="muted">{e(item.chapter)} · {e(item.day)}</span><h3>{e(tr("Warum aktuell so ausgewählt?", "Why this current selection?"))}</h3><ul>')
        for reason in item.primary_reasons:
            stream.write(f'<li>{e(reason)}</li>')
        stream.write(f'</ul><p class="muted">{e(tr("Technische Bewertung", "Technical score"))}: {item.technical_score:.1f} · {e(tr("Gesamtbewertung", "Overall score"))}: {item.final_score:.1f}</p>')
        stream.write(f'<p class="muted">{e(item.provenance_note)}</p>')
        if item.automatic_selected is not None:
            automatic = tr('ausgewählt', 'selected') if item.automatic_selected else tr('nicht ausgewählt', 'not selected')
            stream.write(f'<h3>{e(tr("Letzte automatische Auswahl", "Last automatic selection"))}: {e(automatic)}</h3><ul>')
            for reason in item.automatic_reasons:
                stream.write(f'<li>{e(reason)}</li>')
            stream.write('</ul>')
        if item.quality_hints:
            stream.write(f'<h3>{e(tr("Gespeicherte Hinweise – nicht automatisch der Auswahlgrund", "Stored hints – not automatically the selection reason"))}</h3><ul>')
            for hint in item.quality_hints:
                stream.write(f'<li>{e(hint)}</li>')
            stream.write('</ul>')
        if item.location_reasons:
            stream.write(f'<h3>{e(tr("Herkunft der Ortszuordnung", "Location assignment provenance"))}</h3><ul>')
            for reason in item.location_reasons:
                stream.write(f'<li>{e(reason)}</li>')
            stream.write('</ul>')
        stream.write(f'<details><summary>{e(tr("Entscheidungsweg und Vergleiche", "Decision history and comparisons"))}</summary>')
        if item.automatic_selected is not None:
            automatic = tr('ausgewählt', 'selected') if item.automatic_selected else tr('nicht ausgewählt', 'not selected')
            stream.write(f'<p>{e(tr("Letzter automatischer Lauf", "Last automatic run"))}: {e(automatic)}</p>')
        if item.recorded_decisions:
            stream.write('<ol>')
            for reason in item.recorded_decisions:
                stream.write(f'<li>{e(reason)}</li>')
            stream.write('</ol>')
        if item.comparisons:
            stream.write(f'<h3>{e(tr("Tatsächlich protokollierte Vergleiche", "Actually recorded comparisons"))}</h3><ul>')
            for comparison in item.comparisons:
                name = e(comparison.filename)
                if comparison.peer_index is not None:
                    name = f'<a href="#photo-{comparison.peer_index}">{name}</a>'
                stream.write(f'<li>{name}: {e(comparison.explanation)}<br><code>{e(comparison.peer_path)}</code></li>')
            stream.write('</ul>')
        stream.write(f'<p><code>{e(item.path)}</code></p></details></article>')
    stream.write('''</main><script>
const cards=Array.from(document.querySelectorAll('.photo')),query=document.getElementById('query'),filter=document.getElementById('filter');
const searchable=cards.map(card=>card.textContent.toLocaleLowerCase());let timer;
function apply(){const q=query.value.trim().toLocaleLowerCase(),mode=filter.value;let count=0;cards.forEach((card,i)=>{const match=mode==='all'||(mode==='selected'&&card.dataset.selected==='1')||(mode==='omitted'&&card.dataset.selected==='0')||(mode==='review'&&card.dataset.review==='1')||(mode==='legacy'&&card.dataset.recorded==='0');card.hidden=!(match&&searchable[i].includes(q));if(!card.hidden)count++;});document.getElementById('visible').textContent=count+' / '+cards.length;}
query.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,100)});filter.addEventListener('change',apply);document.getElementById('expand').addEventListener('click',()=>{const details=cards.filter(c=>!c.hidden).map(c=>c.querySelector('details'));const open=details.some(d=>!d.open);details.forEach(d=>d.open=open);});apply();
</script></body></html>''')
