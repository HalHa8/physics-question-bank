// Independent manual physics labels; no AI calls, textbook edits or parallel
// editor session. All untrusted names/aliases are inserted with textContent.
(function () {
    'use strict';
    let selected = [];
    const filter = { points: [], match: 'any', role: 'all', unlabeled: false };
    const searches = { editor: { sequence: 0 }, filter: { sequence: 0 } };
    const ids = {
        editor: { search: 'knowledgePointSearch', results: 'knowledgePointResults', status: 'knowledgePointStatus' },
        filter: { search: 'filterPointSearch', results: 'filterPointResults', status: 'filterPointStatus' }
    };
    const byId = id => document.getElementById(id);
    const copy = value => JSON.parse(JSON.stringify(value));
    const snapshot = () => selected.map(point => ({ code: point.code, role: point.role, status: 'confirmed' }));
    function button(text, handler, label) {
        const node = document.createElement('button');
        node.type = 'button'; node.className = 'glass-btn kp-button'; node.textContent = text;
        if (label) node.setAttribute('aria-label', label);
        node.addEventListener('click', handler);
        return node;
    }
    function changed() {
        renderSelection();
        if (typeof window.refreshEditorFeedback === 'function') window.refreshEditorFeedback();
    }
    function renderSelection() {
        const host = byId('knowledgePointSelection');
        const summary = byId('knowledgePointSummary');
        if (host) {
            host.replaceChildren();
            selected.forEach(point => {
                const row = document.createElement('div'); row.className = 'kp-selected-row';
                const name = document.createElement('span'); name.textContent = point.name || point.code;
                const role = document.createElement('select'); role.className = 'glass-select';
                role.setAttribute('aria-label', (point.name || point.code) + '的主辅角色');
                [['main', '主要考查'], ['auxiliary', '辅助知识']].forEach(([value, text]) => {
                    const option = document.createElement('option'); option.value = value; option.textContent = text; role.append(option);
                });
                role.value = point.role;
                role.addEventListener('change', () => { point.role = role.value; changed(); });
                row.append(name, role, button('移除', () => { selected = selected.filter(item => item.code !== point.code); changed(); }, '移除知识点' + (point.name || point.code)));
                host.append(row);
            });
            if (!selected.length) host.textContent = '尚未标注；不影响保存或入库。';
        }
        if (summary) {
            summary.textContent = selected.length ? '考查知识点：' + selected.map(point => (point.name || point.code) + (point.role === 'auxiliary' ? '（辅）' : '（主）')).join('、') : '考查知识点：尚未标注';
        }
    }
    function cancelSearch(context) {
        const state = searches[context]; state.sequence += 1;
        if (state.controller) state.controller.abort();
        if (state.timer) clearTimeout(state.timer);
    }
    function hydrate(question) {
        cancelSearch('editor');
        const seen = new Set();
        selected = (Array.isArray(question && question.knowledge_points) ? question.knowledge_points : []).filter(point => {
            if (!point || typeof point.code !== 'string' || seen.has(point.code)) return false;
            seen.add(point.code); return true;
        }).map(point => ({ code: point.code, name: point.name || point.code, role: point.role === 'auxiliary' ? 'auxiliary' : 'main', status: 'confirmed' }));
        if (byId(ids.editor.search)) byId(ids.editor.search).value = '';
        if (byId(ids.editor.results)) byId(ids.editor.results).replaceChildren();
        if (byId(ids.editor.status)) byId(ids.editor.status).textContent = '';
        if (byId('newKnowledgePointName')) byId('newKnowledgePointName').value = '';
        if (byId('newKnowledgePointAliases')) byId('newKnowledgePointAliases').value = '';
        renderSelection();
    }
    function add(point, context) {
        const list = context === 'editor' ? selected : filter.points;
        if (list.some(item => item.code === point.code)) return;
        if (list.length >= 64) { byId(ids[context].status).textContent = '最多选择64个知识点。'; return; }
        list.push({ code: point.code, name: point.name, role: 'main', status: 'confirmed' });
        if (context === 'editor') changed();
        else { filter.unlabeled = false; byId('filterPointsUnlabeled').checked = false; reloadFilter(); }
    }
    async function search(context) {
        cancelSearch(context);
        const state = searches[context], identity = state.sequence;
        const session = context === 'editor' ? window.EditorState.snapshot() : null;
        const input = byId(ids[context].search), host = byId(ids[context].results), status = byId(ids[context].status);
        if (!input || !host || !status) return;
        const query = input.value.trim();
        state.controller = new AbortController();
        status.textContent = '正在查询知识点…'; host.replaceChildren();
        try {
            const response = await fetch('/api/knowledge-points?' + new URLSearchParams({ q: query, limit: '40' }), { signal: state.controller.signal });
            const data = await response.json();
            if (identity !== state.sequence || (session && !window.EditorState.isCurrent(session))) return;
            if (!response.ok) throw new Error(data.detail || '查询失败');
            status.textContent = data.total > data.items.length ? '找到' + data.total + '项，显示前40项，请输入更具体的词。' : '找到' + data.total + '项；点击名称选择。';
            data.items.forEach(point => {
                const node = button(point.name, () => add(point, context), '选择知识点' + point.name);
                node.dataset.pointCode = point.code; host.append(node);
            });
        } catch (error) {
            if (identity === state.sequence && error.name !== 'AbortError' && (!session || window.EditorState.isCurrent(session))) status.textContent = '知识点查询失败，可重新输入或点击查询重试。';
        }
    }
    function renderFilter() {
        const host = byId('filterPointSelection');
        if (!host) return;
        host.replaceChildren();
        filter.points.forEach(point => host.append(button(point.name + ' ×', () => {
            filter.points = filter.points.filter(item => item.code !== point.code); reloadFilter();
        }, '移除筛选知识点' + point.name)));
    }
    function reloadFilter() {
        renderFilter();
        if (typeof window.updateBankFilterSummary === 'function') window.updateBankFilterSummary();
        // These are script-level lexical bindings in the existing editor.
        if (typeof currentBankPage !== 'undefined') currentBankPage = 1;
        if (typeof currentDraftPage !== 'undefined') currentDraftPage = 1;
        if (typeof activeSidebarTab !== 'undefined' && activeSidebarTab === 'drafts') window.loadDrafts();
        else if (typeof window.loadQuestions === 'function') window.loadQuestions();
    }
    function clearFilters() {
        filter.points = []; filter.match = 'any'; filter.role = 'all'; filter.unlabeled = false;
        cancelSearch('filter'); renderFilter();
        if (byId('filterPointMatch')) byId('filterPointMatch').value = 'any';
        if (byId('filterPointRole')) byId('filterPointRole').value = 'all';
        if (byId('filterPointsUnlabeled')) byId('filterPointsUnlabeled').checked = false;
        if (byId(ids.filter.search)) byId(ids.filter.search).value = '';
        if (byId(ids.filter.results)) byId(ids.filter.results).replaceChildren();
        if (byId(ids.filter.status)) byId(ids.filter.status).textContent = '';
    }
    function appendFilters(params) {
        if (filter.points.length) params.set('knowledge_points', filter.points.map(point => point.code).join(','));
        if (filter.points.length) { params.set('point_match', filter.match); params.set('point_role', filter.role); }
        if (filter.unlabeled) params.set('point_unlabeled', 'true');
    }
    function matchesDraft(question) {
        const points = Array.isArray(question.knowledge_points) ? question.knowledge_points : [];
        if (filter.unlabeled) return points.length === 0;
        const codes = new Set(points.filter(point => filter.role === 'all' || point.role === 'main').map(point => point.code));
        return !filter.points.length || (filter.match === 'all' ? filter.points.every(point => codes.has(point.code)) : filter.points.some(point => codes.has(point.code)));
    }
    async function createPoint() {
        const input = byId('newKnowledgePointName'), control = byId('createKnowledgePointBtn'), status = byId(ids.editor.status);
        const name = input.value.trim(); if (!name || control.disabled) return;
        const session = window.EditorState.snapshot();
        const aliasesInput = byId('newKnowledgePointAliases');
        const aliasesText = aliasesInput ? aliasesInput.value : '';
        const aliases = aliasesText.split(/[,，]/).map(value => value.trim()).filter(Boolean);
        control.disabled = true; control.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch('/api/knowledge-points', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, aliases }) });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || '创建失败');
            if (window.EditorState.isCurrent(session) && input.value.trim() === name && (!aliasesInput || aliasesInput.value === aliasesText)) {
                add(data.point, 'editor'); input.value = ''; if (aliasesInput) aliasesInput.value = ''; status.textContent = '知识点已创建并选中，题目标注仍需正常保存。';
            }
        } catch (error) {
            if (window.EditorState.isCurrent(session)) status.textContent = error.message + '；若网络中断，请先搜索名称确认是否已创建，再决定是否重试。';
        } finally { control.disabled = false; control.removeAttribute('aria-busy'); }
    }
    window.KnowledgePointState = Object.freeze({ snapshot, export: () => copy(selected), key: () => JSON.stringify(snapshot()), hydrate, reset: () => hydrate({}) });
    window.PhysicsKnowledgePoints = Object.freeze({ search, appendFilters, matchesDraft, clearFilters, filterCount: () => filter.points.length + Number(filter.unlabeled) });
    document.addEventListener('DOMContentLoaded', () => {
        Object.keys(ids).forEach(context => {
            const input = byId(ids[context].search);
            if (input) input.addEventListener('input', () => {
                cancelSearch(context); searches[context].timer = setTimeout(() => search(context), 200);
            });
            const control = byId(context === 'editor' ? 'searchKnowledgePointsBtn' : 'searchFilterPointsBtn');
            if (control) control.addEventListener('click', () => search(context));
        });
        ['filterPointMatch', 'filterPointRole', 'filterPointsUnlabeled'].forEach(id => {
            const node = byId(id); if (!node) return;
            node.addEventListener('change', () => {
                filter.match = byId('filterPointMatch').value; filter.role = byId('filterPointRole').value;
                filter.unlabeled = byId('filterPointsUnlabeled').checked;
                if (filter.unlabeled) filter.points = [];
                reloadFilter();
            });
        });
        if (byId('createKnowledgePointBtn')) byId('createKnowledgePointBtn').addEventListener('click', createPoint);
        renderSelection();
    });
}());
