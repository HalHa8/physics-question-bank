/* Compatibility names only. KnowledgePointState in api.js is the sole state. */
(function () {
    'use strict';
    window.PhysicsKnowledgePoints = Object.freeze({
        search: () => window.loadKnowledgePointCatalog ? window.loadKnowledgePointCatalog(true) : Promise.resolve([]),
        matchesDraft: item => window.KnowledgePointState.matches(item.knowledge_points || []),
        appendFilters: params => window.KnowledgePointState.appendParams(params),
        clearFilters: () => window.KnowledgePointState.setFilter('bank', {
            knowledge_point_codes: [], knowledge_point_mode: 'any', knowledge_point_role: 'main',
            knowledge_point_status: 'all', knowledge_point_unlabeled: false
        }),
        filterCount: () => {
            const f = window.KnowledgePointState.filter('bank');
            return f.knowledge_point_codes.length + Number(f.knowledge_point_unlabeled);
        }
    });
}());
