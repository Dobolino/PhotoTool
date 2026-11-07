from pathlib import Path
import pytest
from photobook_curator.i18n import get_language, set_language
from photobook_curator.models import Photo
from photobook_curator.selection_reasons import selection_reasons


@pytest.mark.parametrize('language,decision,phrase', [
    ('de', 'keep', 'Dauerhaft behalten'),
    ('de', 'reject', 'Dauerhaft ausgeschlossen'),
    ('en', 'keep', 'Always keep'),
    ('en', 'reject', 'Always exclude'),
])
def test_explanations_show_persistent_intent_and_personal_reason(language, decision, phrase):
    previous = get_language()
    try:
        set_language(language)
        photo = Photo(path=Path('memory.jpg'), filename='memory.jpg',
                      manual_decision=decision, decision_reason='Besonderer Moment')
        explanation = selection_reasons(photo)
        assert any(phrase in line for line in explanation)
        assert any('Besonderer Moment' in line for line in explanation)
        if decision == 'reject':
            assert not any('not recorded' in line or 'nicht gespeichert' in line for line in explanation)
    finally:
        set_language(previous)
