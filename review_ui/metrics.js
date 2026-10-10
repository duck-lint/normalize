/* Deterministic, read-only aggregation of human lexicon review scope.
   "Forms" are canonical word groups; "occurrences" are source findings.
   A proposed repair is not necessarily an independently approved repair. */
(function (root) {
  'use strict';
  function summarize(groups, decisions) {
    const result = {
      forms: groups.length, occurrences: 0, pending: 0, accepted: 0, rejected: 0,
      proposedOccurrences: 0, verifiedOccurrences: 0, eligibleForms: 0,
      bulkEligibleForms: 0
    };
    for (const group of groups) {
      const status = decisions[group.key]?.decision || 'pending';
      result[status] += 1;
      result.occurrences += group.count;
      result.proposedOccurrences += group.repair_count;
      result.verifiedOccurrences += group.verified_repair_count;
      if (!group.already_known && group.eligible_count > 0) result.eligibleForms++;
      if (status === 'pending' && !group.already_known &&
          group.repair_count === group.count &&
          group.verified_repair_count === group.count) result.bulkEligibleForms++;
    }
    return result;
  }
  // Deterministic selection after the selected word falls out of a filtered list.
  function retainedOrNext(groups, selectedKey, previousIndex) {
    if (groups.some(group => group.key === selectedKey)) return selectedKey;
    const index = Math.min(Math.max(previousIndex, 0), groups.length - 1);
    return groups[index]?.key || null;
  }
  const api = {summarize, retainedOrNext};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ReviewMetrics = api;
})(typeof window !== 'undefined' ? window : globalThis);
