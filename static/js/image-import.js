/* Screenshot entry and ordered image pages; recognition remains in the existing flows. */
(() => {
    'use strict';
    const state = {active: false, mode: 'single', images: [], generation: 0, opening: false};
    const byId = id => document.getElementById(id);
    const isImage = file => file && (/^image\/(png|jpeg|webp|gif)$/i.test(file.type)
        || (!file.type && /\.(png|jpe?g|webp|gif)$/i.test(file.name || '')));
    const busy = () => {
        const loading = byId('importLoadingState');
        return state.opening || Boolean(byId('runParseBtn')?.disabled && loading && !loading.classList.contains('hidden'));
    };
    function message(text) {
        if (byId('importImageStatus')) byId('importImageStatus').textContent = text;
    }
    function canChange() {
        if (!busy()) return true;
        showToast('正在处理，请先中止任务或等待完成。', 'info');
        return false;
    }
    function refresh() {
        byId('importImagePanel').hidden = !state.active;
        byId('importDocumentMode').setAttribute('aria-pressed', String(!state.active));
        byId('importImageMode').setAttribute('aria-pressed', String(state.active));
        byId('importImageSingle').setAttribute('aria-pressed', String(state.mode === 'single'));
        byId('importImageMultiple').setAttribute('aria-pressed', String(state.mode === 'multiple'));
        document.querySelectorAll('[data-import-document]').forEach(node => node.classList.toggle('image-import-hidden', state.active));
        const single = state.active && state.mode === 'single';
        byId('importGenerateAnswers')?.closest('.import-config-card')?.classList.toggle('image-import-hidden', single);
        byId('importImageModeHint').textContent = state.mode === 'single'
            ? '一张截图录入一道题。识别后在题目编辑器核对文字、选项和配图，再保存入库。'
            : '支持一图多题、多张连续页面。先用上移／下移调整页序，再开始拆题；跨图题目会按此顺序合并处理，结果请逐题核对。';
        if (!busy()) {
            const label = single ? '识别这道题' : state.active ? '开始拆题' : '开始解析';
            byId('runParseBtn').innerHTML = '<i class="fa-solid fa-wand-magic-sparkles" aria-hidden="true"></i><span>' + label + '</span>';
        }
    }
    function select(active) {
        if (!canChange()) return false;
        state.active = active;
        state.generation += 1;
        refresh();
        return true;
    }
    function setMode(mode) {
        if (!canChange()) return;
        if (mode === 'single' && state.images.length > 1) {
            message('单题模式只用一张截图。请先移除多余图片，或继续使用多题拆分。');
            return;
        }
        state.mode = mode;
        state.generation += 1;
        refresh();
    }
    function renderImages() {
        const list = byId('importImageList');
        list.replaceChildren();
        state.images.forEach((entry, index) => {
            const row = document.createElement('li');
            const preview = document.createElement('img');
            preview.src = entry.url;
            preview.alt = '第 ' + (index + 1) + ' 张待识别图片';
            const name = document.createElement('span');
            name.textContent = (index + 1) + '. ' + entry.file.name;
            name.title = entry.file.name;
            const controls = document.createElement('div');
            for (const [label, delta] of [['上移', -1], ['下移', 1], ['移除', 0]]) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = label;
                button.setAttribute('aria-label', label + '第 ' + (index + 1) + ' 张图片');
                button.disabled = delta !== 0 && (index + delta < 0 || index + delta >= state.images.length);
                button.onclick = () => {
                    if (!canChange()) return;
                    if (delta === 0) {
                        URL.revokeObjectURL(entry.url);
                        state.images.splice(index, 1);
                    } else {
                        [state.images[index], state.images[index + delta]] = [state.images[index + delta], entry];
                    }
                    state.generation += 1;
                    renderImages();
                    const next = list.children[Math.min(index + delta, state.images.length - 1)];
                    next?.querySelector('button:not([disabled])')?.focus({preventScroll: true});
                };
                controls.appendChild(button);
            }
            row.append(preview, name, controls);
            list.appendChild(row);
        });
        const megabytes = state.images.reduce((sum, item) => sum + item.file.size, 0) / (1024 * 1024);
        message(state.images.length ? '已选择 ' + state.images.length + ' 张图片，共 ' + megabytes.toFixed(1) + 'MB。尚未发送识别请求。' : '尚未选择图片。');
        refresh();
    }
    function addFiles(files) {
        if (!canChange()) return false;
        const incoming = Array.from(files || []);
        if (!incoming.length) return false;
        let error = '';
        if (incoming.some(file => !isImage(file))) error = '请选择 PNG、JPEG、WebP 或 GIF 图片。';
        else if (state.images.length + incoming.length > 20) error = '一次最多选择 20 张图片，请分批导入。';
        else if (incoming.some(file => file.size > 10 * 1024 * 1024)) error = '单张图片不能超过 10MB。';
        else if ([...state.images.map(item => item.file), ...incoming].reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) error = '图片总大小不能超过 50MB。';
        if (error) {
            message(error);
            showToast(error, 'warning');
            return false;
        }
        state.images.push(...incoming.map(file => ({file, url: URL.createObjectURL(file)})));
        state.active = true;
        state.generation += 1;
        if (state.images.length > 1) state.mode = 'multiple';
        if (!byId('importPaperTitle').value.trim()) {
            byId('importPaperTitle').value = incoming[0].name.replace(/\.[^.]+$/, '') || '图片试卷';
        }
        renderImages();
        return true;
    }
    async function openSingle() {
        if (state.images.length !== 1) {
            message('请先上传或粘贴一张完整的单题截图；一图多题请选择“整页／多题拆分”。');
            byId('importImageDropzone').focus();
            return;
        }
        if (state.opening) return;
        const file = state.images[0].file, generation = state.generation;
        state.opening = true;
        try {
            await openNewQuestionEditor({sourceTab: 'ocr', onReady: () => {
                if (!state.active || generation !== state.generation) return;
                const source = byId('editSource');
                if (source) source.value = byId('importPaperTitle').value.trim();
                runContentOcr(file);
            }});
        } finally {
            state.opening = false;
            refresh();
        }
    }
    function reset() {
        state.images.forEach(entry => URL.revokeObjectURL(entry.url));
        state.images = [];
        state.mode = 'single';
        state.generation += 1;
        if (byId('importImageFiles')) byId('importImageFiles').value = '';
        renderImages();
    }
    window.PhysicsBankImageImport = {
        isImage, addFiles, select, openSingle, reset,
        isSingle: () => state.active && state.mode === 'single',
        isActive: () => state.active,
        filesForSplit: () => state.active && state.mode === 'multiple' ? state.images.map(entry => entry.file) : [],
    };
    document.addEventListener('DOMContentLoaded', () => {
        if (!byId('importImagePanel')) return;
        byId('importDocumentMode').onclick = () => select(false);
        byId('importImageMode').onclick = () => select(true);
        byId('importImageSingle').onclick = () => setMode('single');
        byId('importImageMultiple').onclick = () => setMode('multiple');
        const input = byId('importImageFiles'), zone = byId('importImageDropzone');
        zone.onclick = () => { if (canChange()) input.click(); };
        zone.onkeydown = event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); zone.click(); }
        };
        input.onchange = () => { addFiles(input.files); input.value = ''; };
        new MutationObserver(refresh).observe(byId('runParseBtn'), {attributes: true, attributeFilter: ['disabled']});
        ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => {
            event.preventDefault(); event.stopPropagation(); zone.classList.add('is-dragging');
        }));
        ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
            event.preventDefault(); event.stopPropagation(); zone.classList.remove('is-dragging');
            if (type === 'drop') addFiles(event.dataTransfer.files);
        }));
        window.addEventListener('paste', event => {
            const workspace = byId('importWorkspaceSection'), editor = byId('editorSection');
            if (!state.active || workspace.classList.contains('hidden') || !editor.classList.contains('hidden')) return;
            const files = Array.from(event.clipboardData?.items || []).filter(item => item.kind === 'file' && item.type.startsWith('image/'))
                .map(item => item.getAsFile()).filter(Boolean);
            if (!files.length) return;
            event.preventDefault(); event.stopImmediatePropagation();
            addFiles(files);
        }, true);
        refresh();
    });
    window.addEventListener('pagehide', () => state.images.forEach(entry => URL.revokeObjectURL(entry.url)));
})();
