/* Native library navigation; no fetch interception or private data cache. */
(() => {
    'use strict';
    let dialog, tree, treeStatus, controller, timer, sequence = 0, lastPayload = '';
    const node = (tag, text, className) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (className) element.className = className;
        return element;
    };
    function close() {
        if (!dialog || dialog.hidden) return;
        window.MathBankModal.close(dialog);
        dialog.hidden = true;
    }
    function ensureDialog() {
        if (dialog) return;
        dialog = node('div', undefined, 'library-dialog-overlay');
        dialog.id = 'libraryTreeDialog'; dialog.hidden = true;
        dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-labelledby', 'libraryTreeTitle');
        const panel = node('div', undefined, 'library-tree-panel');
        const heading = node('div', undefined, 'library-panel-heading');
        const title = node('h2', '章节目录'); title.id = 'libraryTreeTitle';
        const exit = node('button', '关闭', 'glass-btn'); exit.type = 'button'; exit.onclick = close;
        heading.append(title, exit);
        const help = node('p', '数字为全库数量，点击后与现有筛选条件共同生效。待归类：教材、章节、题型或难度缺失/失效；待细分到小节：已有有效章节，但未对应本章具体小节。独立知识点标注另行管理。', 'library-help');
        treeStatus = node('p'); treeStatus.setAttribute('role', 'status');
        const retry = node('button', '刷新目录', 'glass-btn'); retry.type = 'button'; retry.onclick = refresh;
        tree = node('nav'); tree.id = 'libraryTree'; tree.setAttribute('aria-label', '教材章节与小节');
        panel.append(heading, help, retry, treeStatus, tree);
        dialog.append(panel); document.body.append(dialog);
        dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
    }
    function selectPath(path, status = '') {
        // Set dependent selects together, then reuse the native cascade once.
        ['filterCompulsory', 'filterChapter', 'filterKnowledge'].forEach((id, index) => {
            setEditorMetadataValue(document.getElementById(id), path[index] || '');
        });
        populateFilterDropdowns();
        document.getElementById('filterClassification').value = status;
        currentBankPage = 1;
        close();
        if (activeSidebarTab !== 'bank') switchSidebarTab('bank');
        else loadQuestions();
    }
    function entry(label, count, path, status = '') {
        const button = node('button', undefined, 'library-tree-entry');
        button.type = 'button'; button.dataset.path = JSON.stringify([path, status]);
        button.append(node('span', label), node('span', String(count), 'library-count'));
        button.setAttribute('aria-label', `${label}，${count} 道题`);
        button.onclick = () => selectPath(path, status);
        return button;
    }
    function group(label, count, path) {
        const details = node('details'); details.dataset.path = JSON.stringify(path);
        const summary = node('summary', `${label}（${count}）`); summary.tabIndex = 0;
        summary.dataset.path = JSON.stringify(['expand', path]);
        details.append(summary, entry(path.length === 1 ? '本册全部题目' : '本章全部题目', count, path));
        return details;
    }
    function renderTree(data) {
        const expanded = new Set([...tree.querySelectorAll('details[open]')].map(item => item.dataset.path));
        const focused = document.activeElement?.dataset.path;
        const children = [entry('全部题目', data.total, []), entry('待归类', data.unclassified, [], 'unclassified'),
            entry('待细分到小节', data.section_unassigned || 0, [], 'section_unassigned')];
        data.books.forEach(book => {
            const bookNode = group(book.name, book.count, [book.name]);
            bookNode.append(entry('章节待归类', book.unassigned, [book.name], 'book_unassigned'));
            book.chapters.forEach(chapter => {
                const chapterNode = group(chapter.name, chapter.count, [book.name, chapter.name]);
                chapterNode.append(entry('待细分到小节', chapter.section_unassigned || 0, [book.name, chapter.name], 'section_unassigned'));
                chapter.sections.forEach(section => chapterNode.append(entry(section.name, section.count, [book.name, chapter.name, section.name])));
                bookNode.append(chapterNode);
            });
            children.push(bookNode);
        });
        tree.replaceChildren(...children);
        tree.querySelectorAll('details').forEach(item => { item.open = expanded.has(item.dataset.path); });
        if (focused) [...tree.querySelectorAll('button,summary')].find(item => item.dataset.path === focused)?.focus({preventScroll: true});
    }
    function renderStatistics(data) {
        const coverage = data.coverage;
        const metrics = [
            ['全库题目', data.total, '题'],
            ['待归类', data.unclassified, '题'],
            ['教材小节覆盖', `${coverage.covered_sections}/${coverage.total_sections}`, ''],
            ['已确认知识点', coverage.confirmed_points, '个'],
            ['知识点待确认', coverage.pending_questions, '题'],
        ];
        document.getElementById('libraryCoverage').replaceChildren(...metrics.map(([label, value, unit]) => {
            const item = node('div', undefined, 'library-coverage-item');
            const amount = node('dd');
            amount.append(node('strong', String(value)));
            if (unit) amount.append(node('span', unit));
            item.append(node('dt', label), amount);
            return item;
        }));
        const host = document.getElementById('libraryDistributions');
        const expanded = new Set([...host.querySelectorAll('details[open]')].map(item => item.dataset.dimension));
        host.replaceChildren();
        [['question_type', '题型'], ['difficulty', '难度'], ['tag', '标签'], ['source', '来源']].forEach(([key, label]) => {
            const section = node('section', undefined, 'library-distribution');
            section.dataset.dimension = key;
            section.append(node('h3', label));
            const rows = data.dimensions[key];
            const list = node('ul');
            const max = rows.reduce((value, item) => Math.max(value, item.count), 1);
            const makeRow = item => {
                const row = node('li');
                row.append(node('span', item.label), node('strong', String(item.count)));
                const bar = node('progress'); bar.max = max; bar.value = item.count;
                bar.setAttribute('aria-label', `${item.label}，${item.count} 道题`);
                row.append(bar); return row;
            };
            rows.slice(0, 6).forEach(item => list.append(makeRow(item)));
            if (!rows.length) list.append(node('li', '暂无题目', 'library-distribution-empty'));
            section.append(list);
            if (rows.length > 6) {
                const details = node('details'); details.dataset.dimension = key; details.open = expanded.has(key);
                const summary = node('summary', `其余 ${rows.length - 6} 项`); summary.tabIndex = 0;
                details.append(summary);
                const rest = node('ul');
                const more = node('button', '继续显示', 'glass-btn'); more.type = 'button';
                let offset = 6;
                const appendBatch = () => {
                    rows.slice(offset, offset + 30).forEach(item => rest.append(makeRow(item)));
                    offset += 30; more.hidden = offset >= rows.length;
                };
                more.onclick = appendBatch;
                details.addEventListener('toggle', () => { if (details.open && offset === 6) appendBatch(); });
                if (details.open) appendBatch();
                details.append(rest, more); section.append(details);
            }
            host.append(section);
        });
    }
    async function refresh() {
        clearTimeout(timer); ensureDialog();
        const current = ++sequence;
        controller?.abort(); controller = new AbortController();
        const status = document.getElementById('libraryStatsStatus');
        const refreshButton = document.getElementById('libraryStatsRefresh');
        const refreshIcon = refreshButton.querySelector('i');
        refreshIcon.classList.add('fa-spin');
        refreshButton.disabled = true;
        refreshButton.setAttribute('aria-busy', 'true');
        status.dataset.state = 'loading';
        status.textContent = treeStatus.textContent = lastPayload ? '正在更新…' : '正在读取…';
        try {
            const response = await fetch('/api/library/overview', {signal: controller.signal});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (current !== sequence) return;
            if (!data || !Array.isArray(data.books) || !data.dimensions || !data.coverage) throw new Error('响应格式无效');
            const serialized = JSON.stringify(data);
            if (serialized !== lastPayload) {
                renderTree(data); renderStatistics(data); lastPayload = serialized;
            }
            status.textContent = treeStatus.textContent = '已更新 · 全库统计';
            status.dataset.state = 'ready';
        } catch (error) {
            if (current !== sequence || error.name === 'AbortError') return;
            status.textContent = treeStatus.textContent = lastPayload
                ? '更新失败，暂保留上次统计；请点击刷新重试。' : '统计读取失败，请点击刷新重试。';
            status.dataset.state = 'error';
        } finally {
            if (current === sequence) {
                refreshIcon.classList.remove('fa-spin');
                refreshButton.disabled = false;
                refreshButton.removeAttribute('aria-busy');
            }
        }
    }
    function scheduleRefresh() { clearTimeout(timer); timer = setTimeout(refresh, 200); }
    function open() {
        ensureDialog(); dialog.hidden = false;
        window.MathBankModal.open(dialog, {onEscape: close}); refresh();
    }
    window.LibraryBrowser = {open, close, refresh, scheduleRefresh};
})();
