"""Grouped bank filters in an isolated app; no production data or AI calls."""

import pytest

from test_preview_browser import browser, pytestmark  # noqa: F401


def open_filters(browser, width=1600, dark=False):
    browser.command('set', 'viewport', str(width), '1000' if width > 600 else '812')
    browser.evaluate("selectWorkspace('bank','题库管理'); clearBankFilters(); true")
    browser.command('wait', '--fn', "document.getElementById('filterCompulsory').options.length > 1")
    browser.evaluate(f"document.documentElement.classList.toggle('dark',{str(dark).lower()}); true")
    if not browser.evaluate("document.querySelector('.bank-filter-toggle').getAttribute('aria-expanded')==='true'"):
        browser.command('click', '.bank-filter-toggle')
    browser.settle()
    # The shared controls animate their height after changing breakpoints.
    browser.command('wait', '--fn', "[...document.querySelectorAll('.bank-filter-field input,.bank-filter-field select')].every(el=>el.getBoundingClientRect().height >= (innerWidth<=960?44:40))")


@pytest.mark.parametrize('width', [2259, 1600, 768, 375])
@pytest.mark.parametrize('dark', [False, True])
def test_filter_groups_align_and_have_only_one_knowledge_entry(browser, width, dark):
    open_filters(browser, width, dark)
    result = browser.evaluate(r"""(() => {
        const panel=document.querySelector('.bank-filter-toolbar');
        const groups=[...document.querySelectorAll('.bank-filter-group')];
        const ids=['filterCompulsory','filterChapter','filterKnowledge','filterType',
            'filterDifficulty','filterClassification','filterSource'];
        const controls=ids.map(id=>document.getElementById(id));
        const sameRow=selectors=>{
            const rects=selectors.map(selector=>document.querySelector(selector).getBoundingClientRect());
            return rects.every(rect=>Math.abs(rect.top-rects[0].top)<1 && Math.abs(rect.height-rects[0].height)<1);
        };
        return {
            groups:groups.map(group=>group.getAttribute('aria-labelledby')),
            labels:controls.every(control=>control.labels.length===1),
            height:controls.every(control=>control.getBoundingClientRect().height >= (innerWidth<=960?44:40)),
            heights:controls.map(control=>[control.id,control.getBoundingClientRect().height,getComputedStyle(control).height]),
            fits:panel.scrollWidth<=panel.clientWidth+1 && groups.every(group=>group.scrollWidth<=group.clientWidth+1)
                && document.documentElement.scrollWidth<=innerWidth,
            aligned:innerWidth<=960 || (sameRow(['#filterCompulsory','#filterChapter','#filterKnowledge'])
                && sameRow(['#filterType','#filterDifficulty','#filterClassification','#filterSource'])),
            compact:innerWidth<=960 || panel.getBoundingClientRect().height<260,
            single:!document.querySelector('.kp-filter-panel') && document.querySelectorAll('#bankKnowledgePointPicker .mb-kp-toggle').length===1,
            disabled:document.getElementById('filterChapter').disabled && document.getElementById('filterKnowledge').disabled,
        };
    })()""")
    assert result.pop('groups') == ['bankLocationFiltersTitle','bankAttributeFiltersTitle']
    heights = result.pop('heights')
    assert all(result.values()), {'failed':[key for key,value in result.items() if not value], 'heights':heights}
    browser.command('screenshot', str(browser.root / f'bank-filters-{width}-{dark}.png'))


def test_grouped_filters_preserve_selection_and_knowledge_popup(browser):
    open_filters(browser)
    book = browser.evaluate("document.getElementById('filterCompulsory').options[1].value")
    browser.command('select', '#filterCompulsory', book)
    chapter = browser.evaluate("document.getElementById('filterChapter').options[1].value")
    browser.command('select', '#filterChapter', chapter)
    section = browser.evaluate("document.getElementById('filterKnowledge').options[1].value")
    browser.command('select', '#filterKnowledge', section)
    browser.command('select', '#filterType', 'experiment')
    browser.command('fill', '#filterSource', '布局回归来源')
    browser.command('wait', '--fn', "document.getElementById('clearBankFiltersBtn').hidden===false")
    before = browser.evaluate("['filterCompulsory','filterChapter','filterKnowledge','filterType','filterSource'].map(id=>document.getElementById(id).value)")
    browser.command('click', '.bank-filter-toggle')
    assert browser.evaluate("!document.getElementById('bankFilterFields').checkVisibility()")
    browser.command('click', '.bank-filter-toggle')
    assert browser.evaluate("['filterCompulsory','filterChapter','filterKnowledge','filterType','filterSource'].map(id=>document.getElementById(id).value)") == before
    browser.command('click', '#bankKnowledgePointPicker .mb-kp-toggle')
    browser.command('wait', '--fn', "document.getElementById('mb-kp-picker-bank').checkVisibility()")
    assert browser.evaluate("document.querySelector('#mb-kp-picker-bank input[type=search]').checkVisibility()")
    browser.command('press', 'Escape')
    browser.command('click', '#clearBankFiltersBtn')
    assert browser.evaluate("['filterCompulsory','filterChapter','filterKnowledge','filterType','filterSource'].every(id=>document.getElementById(id).value==='')")
    assert browser.evaluate("document.getElementById('filterChapter').disabled && document.getElementById('filterKnowledge').disabled")
