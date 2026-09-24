/* Synthetic questions only. Loaded into the actual app by test_preview_browser.py. */
window.MathBankBrowserChecks = {
    async settle() {
        await document.fonts.ready;
        for (let i = 0; i < 8; i++) await new Promise(requestAnimationFrame);
    },
    seed(count, repeats, short = false) {
        document.activeElement.blur();
        const state = window.PaperStore;
        state.cart = [];
        state.questionsMap = {};
        Object.assign(state.meta, {
            paper_type: 'exam', title: '分页回归验证', subtitle: '',
            show_secret: false, show_notice: true, solution_space_default: '0', section_order: [],
        });
        document.getElementById('paperMetaTitle').value = state.meta.title;
        document.getElementById('paperMetaSubtitle').value = state.meta.subtitle;
        state.cartQuestionLoad = {
            loading: false, error: '', missingIds: [], confirmedMissingIds: [], failedIds: [],
        };
        for (let id = 1; id <= count; id++) {
            state.cart.push({id, score: 5, solution_space: 0});
            state.questionsMap[id] = {
                id, question_type: 'single_choice', difficulty: 'normal', image_paths: [],
                content: short ? `这是第${id}题：已知 $x=1$，求 $x+1$。` :
                    '设 $A,B$ 为非空集合，定义集合的运算，判断下面结论是否正确。'.repeat(repeats) +
                    String.raw`\begin{choices}\item 若 $A=\{x|-2\le x\le 3\}$，则 $B=\{x|1\le x\le 2\}$。\item 若 $A=\{1,2,3\}$，非空集合 $B$ 满足 $A+B=A$。\item 若非空集合 $A,B$ 满足 $A*B=A$，则 $1\in B$。\item 对所有实数 $x$，都有 $f(x)>0$。\end{choices}`,
            };
        }
        window.renderPaperCanvas();
        document.getElementById('a4PaperPreviewSheet').scrollTop = 0;
    },
    measure() {
        return [...document.querySelectorAll('.a4-paper-sheet')].map(page => {
            const footer = page.querySelector('.paper-page-footer').getBoundingClientRect();
            return {
                expanded: page.classList.contains('a4-paper-sheet--expanded'),
                height: page.getBoundingClientRect().height,
                questions: [...page.querySelectorAll('.paper-page-block[data-paper-block-type="question"]')].map(block => ({
                    id: Number(block.querySelector('[data-qid]').dataset.qid),
                    overflow: block.getBoundingClientRect().bottom - footer.top + 12,
                })),
            };
        });
    },
    async drag(fromId, toId, before = false, cancel = false, dropOnPlaceholder = false, returnToSelf = false) {
        const first = document.querySelector(`.paper-q-item[data-qid="${fromId}"]`);
        const target = document.querySelector(`.paper-q-item[data-qid="${toId}"]`);
        const dataTransfer = new DataTransfer();
        first.dispatchEvent(new DragEvent('dragstart', {bubbles: true, cancelable: true, dataTransfer}));
        await new Promise(resolve => setTimeout(resolve, 0));
        await this.settle();
        const bounds = target.getBoundingClientRect();
        target.dispatchEvent(new DragEvent('dragover', {
            bubbles: true, cancelable: true, dataTransfer,
            clientY: before ? bounds.top + 1 : bounds.bottom - 1,
        }));
        await this.settle();
        if (returnToSelf) {
            first.dispatchEvent(new DragEvent('dragover', {
                bubbles: true, cancelable: true, dataTransfer,
                clientY: first.getBoundingClientRect().bottom - 1,
            }));
            await this.settle();
        }
        const dropTarget = returnToSelf ? first : dropOnPlaceholder ? document.querySelector('.paper-drag-placeholder') : target;
        if (!cancel) dropTarget.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer}));
        first.dispatchEvent(new DragEvent('dragend', {bubbles: true, cancelable: true, dataTransfer}));
        return window.PaperStore.cart.map(item => item.id);
    },
};
true;
