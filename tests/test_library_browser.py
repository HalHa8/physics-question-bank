"""Real UI/API trials on an isolated synthetic database; no external AI calls."""

import os
import pytest
from test_preview_browser import browser  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get('MATHBANK_TEST_BROWSER') != '1', reason='opt-in browser')


@pytest.fixture(scope='module')
def library_browser(browser):
    browser.evaluate("selectWorkspace('bank', '本地题库'); true")
    browser.command('wait', '--fn', '!!window.systemMetadata && !!Object.keys(categoryTree).length')
    result = browser.evaluate(r"""(async () => {
        const book = Object.keys(categoryTree)[0], chapter = Object.keys(categoryTree[book])[0];
        const section = categoryTree[book][chapter][0];
        window.__libraryTrial = {book, chapter, section, ids: []};
        for (let index = 0; index < 3; index++) {
            const form = new FormData();
            form.set('content', '目录回归题 ' + index);
            form.set('question_type', index === 2 ? 'single_choice' : 'experiment');
            form.set('difficulty', systemMetadata.difficulties[0].value);
            form.set('category_compulsory', book);
            form.set('category_chapter', index === 1 ? '' : chapter);
            form.set('category_knowledge', index === 1 ? '' : section);
            form.set('tags', index === 0 ? '力，力,运动' : '');
            form.set('source', index === 0 ? '<img src=x onerror=alert(1)>' : '试卷乙');
            const response = await fetch('/api/questions', {method:'POST', body:form});
            const data = await response.json();
            if (!response.ok) throw new Error(JSON.stringify(data));
            __libraryTrial.ids.push(data.question.id);
        }
        loadQuestions(); await LibraryBrowser.refresh(); return __libraryTrial.ids;
    })()""")
    assert len(result) == 3
    browser.command('wait', '--fn', "document.querySelectorAll('#questionsList .question-card').length === 3")
    yield browser


def test_metadata_filter_updates_and_keeps_historical_selection(library_browser):
    browser = library_browser
    assert browser.evaluate(r"""(() => {
        const filter = document.getElementById('filterType');
        const before = systemMetadata.question_types;
        systemMetadata.question_types = [...before, {value:'trial_custom',label:'自定义试验题'}];
        populateMetadataDropdowns();
        filter.value = 'trial_custom'; populateMetadataDropdowns();
        const added = filter.value === 'trial_custom' && filter.selectedOptions[0].textContent === '自定义试验题';
        systemMetadata.question_types = before; populateMetadataDropdowns();
        const retained = filter.value === 'trial_custom';
        filter.value = ''; populateMetadataDropdowns();
        return added && retained && filter.value === '' && [...filter.options].some(x=>x.value==='experiment');
    })()""")


def test_tree_paths_compose_with_type_and_clear(library_browser):
    browser = library_browser
    browser.evaluate("document.getElementById('filterType').value='experiment'; LibraryBrowser.open(); true")
    browser.command('wait', '--fn', "document.querySelectorAll('#libraryTree button').length > 6")
    browser.evaluate(r"""(() => {
        const path = [__libraryTrial.book, __libraryTrial.chapter, __libraryTrial.section];
        const button = [...document.querySelectorAll('#libraryTree button')].find(x=>x.dataset.path===JSON.stringify([path,'']));
        button.closest('details').open = true; button.closest('details').parentElement.open = true;
        button.click(); return true;
    })()""")
    browser.command('wait', '--fn', "document.querySelectorAll('#questionsList .question-card').length === 1")
    assert browser.evaluate("document.getElementById('filterKnowledge').value === __libraryTrial.section && !document.querySelector('main').inert")
    browser.evaluate("clearBankFilters(); true")
    browser.command('wait', '--fn', "document.querySelectorAll('#questionsList .question-card').length === 3")


def test_unclassified_count_updates_after_edit_with_same_total(library_browser):
    browser = library_browser
    browser.evaluate("LibraryBrowser.open(); true")
    browser.command('wait', '--fn', "document.querySelector('#libraryTree').textContent.includes('待归类')")
    browser.evaluate("[...document.querySelectorAll('#libraryTree button')].find(x=>x.dataset.path===JSON.stringify([[],'unclassified'])).click(); true")
    browser.command('wait', '--fn', "document.querySelectorAll('#questionsList .question-card').length === 1")
    assert browser.evaluate("document.querySelector('#questionsList .question-card').dataset.id === String(__libraryTrial.ids[1])")
    assert browser.evaluate(r"""(async () => {
        const form = new FormData();
        form.set('content', '目录回归题 1'); form.set('question_type','experiment');
        form.set('difficulty', systemMetadata.difficulties[0].value);
        form.set('category_compulsory', __libraryTrial.book);
        form.set('category_chapter', __libraryTrial.chapter);
        form.set('category_knowledge', __libraryTrial.section);
        const response=await fetch('/api/questions/'+__libraryTrial.ids[1],{method:'PUT',body:form});
        if(!response.ok)throw new Error(await response.text());
        loadQuestions(); return true;
    })()""")
    browser.command('wait', '--fn', "document.getElementById('libraryCoverage').textContent.includes('待归类 0 题')")
    assert browser.evaluate("document.getElementById('libraryCoverage').textContent.includes('共 3 题')")
    browser.evaluate("clearBankFilters(); true")


def test_stats_failure_keeps_previous_values_and_untrusted_labels_are_text(library_browser):
    browser = library_browser
    assert browser.evaluate(r"""(async () => {
        await LibraryBrowser.refresh();
        const before = document.getElementById('libraryCoverage').textContent;
        const original = window.fetch;
        try {
            window.fetch = (url,...args) => String(url).includes('/api/library/overview')
                ? Promise.resolve(new Response('{}',{status:503})) : original(url,...args);
            await LibraryBrowser.refresh();
            return document.getElementById('libraryCoverage').textContent === before
                && document.getElementById('libraryStatsStatus').textContent.includes('保留')
                && !document.querySelector('#libraryDistributions img')
                && document.getElementById('libraryDistributions').textContent.includes('<img');
        } finally { window.fetch = original; }
    })()""")
    browser.evaluate("LibraryBrowser.refresh().then(()=>true)")


def test_late_statistics_cannot_overwrite_newer_response(library_browser):
    browser = library_browser
    assert browser.evaluate(r"""(async () => {
        await LibraryBrowser.refresh();
        const original = window.fetch;
        const data = await (await original('/api/library/overview')).json();
        let release;
        try {
            window.fetch = () => new Promise(resolve => { release=resolve; });
            const slow = LibraryBrowser.refresh();
            window.fetch = () => Promise.resolve(new Response(JSON.stringify(data)));
            await LibraryBrowser.refresh();
            release(new Response(JSON.stringify({...data,total:999})));
            await slow;
            return !document.getElementById('libraryCoverage').textContent.includes('999');
        } finally { window.fetch=original; }
    })()""")


def test_mobile_dark_drawer_keyboard_and_original_dashboard_cards(library_browser):
    browser = library_browser
    browser.command('set', 'viewport', '375', '812')
    browser.evaluate("document.documentElement.classList.add('dark'); selectWorkspace('bank','题库'); true")
    browser.command('click', '#libraryTreeToggle')
    browser.command('wait', '--fn', "document.activeElement.id === 'libraryTreeTitle'")
    assert browser.evaluate(r"""(() => {
        const dialog = document.getElementById('libraryTreeDialog'), panel = dialog.firstElementChild;
        return document.querySelector('main').inert && panel.scrollWidth <= panel.clientWidth + 1
            && panel.getBoundingClientRect().right <= innerWidth
            && getComputedStyle(panel).backgroundColor !== 'rgb(255, 255, 255)';
    })()""")
    browser.command('screenshot', str(browser.root / 'library-drawer-dark.png'))
    browser.command('press', 'Escape')
    assert browser.evaluate("document.getElementById('libraryTreeDialog').hidden && document.activeElement.id === 'libraryTreeToggle' && !document.querySelector('main').inert")
    browser.evaluate("selectWorkspace('dashboard','首页'); true")
    assert browser.evaluate("document.querySelectorAll('.dashboard-stat-grid .dashboard-stat-card').length===4 && document.querySelectorAll('#libraryDistributions > section').length===4 && document.documentElement.scrollWidth<=innerWidth")
    browser.command('screenshot', str(browser.root / 'library-mobile-dark.png'))
    browser.command('set', 'viewport', '1600', '1100')
    browser.evaluate("document.documentElement.classList.remove('dark'); true")
    browser.settle()
    browser.command('wait', '--fn', "getComputedStyle(document.querySelector('#libraryStatistics button')).color === getComputedStyle(document.getElementById('libraryStatsTitle')).color")
    browser.command('screenshot', str(browser.root / 'library-desktop.png'))
