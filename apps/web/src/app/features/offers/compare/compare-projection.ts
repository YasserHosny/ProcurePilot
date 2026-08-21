import type {
  Offer,
  OfferComparison,
  Recommendation,
  RecommendationConfidence,
  RecommendationRiskNote,
} from '../offers-api';

export interface ProjectedOffer extends Offer {
  readonly projected_landed_cost: {
    readonly amount: string;
    readonly currency: string;
  };
  readonly projected_unit_price: {
    readonly amount: string;
    readonly currency: string;
  };
}

export interface ProjectedComparison {
  readonly requested_quantity: string;
  readonly offers: readonly ProjectedOffer[];
  readonly recommendation: Recommendation | null;
}

const TIE_BREAK_RULES = [
  'cheapest_cost',
  'match_confidence',
  'reliability',
  'lead_time',
  'validity_window',
  'supplier_name',
  'supplier_id',
];

/**
 * Pure client-side projection utility that recomputes offer totals and re-scores
 * recommendations instantly (<150ms budget) without making network calls (SC-002).
 */
export function projectComparison(
  originalComparison: OfferComparison | null,
  newQuantityStr: string,
  now: Date = new Date(),
): ProjectedComparison | null {
  if (!originalComparison) return null;

  const newQty = parseFloat(newQuantityStr);
  if (isNaN(newQty) || newQty <= 0) {
    return {
      requested_quantity: newQuantityStr,
      offers: originalComparison.offers.map((o) => ({
        ...o,
        projected_landed_cost: o.landed_cost,
        projected_unit_price: o.normalised_unit_price,
      })),
      recommendation: originalComparison.recommendation,
    };
  }

  // 1. Calculate projected landed cost for each offer
  const projectedOffers: ProjectedOffer[] = originalComparison.offers.map((offer) => {
    const origReqQty = parseFloat(offer.requested_quantity) || 1.0;
    const origTotalAmt = parseFloat(offer.landed_cost.amount) || 0.0;
    const unitLandedCost = origTotalAmt / origReqQty;
    const newTotal = unitLandedCost * newQty;

    return {
      ...offer,
      projected_landed_cost: {
        amount: newTotal.toFixed(4),
        currency: offer.landed_cost.currency,
      },
      projected_unit_price: offer.normalised_unit_price,
    };
  });

  // 2. Filter eligible (non-expired) offers for recommendation
  const eligibleOffers = projectedOffers.filter((o) => {
    if (o.is_expired) return false;
    if (o.valid_to) {
      const validToDate = new Date(o.valid_to);
      if (validToDate.getTime() < now.getTime()) return false;
    }
    return true;
  });

  if (eligibleOffers.length === 0) {
    return {
      requested_quantity: newQuantityStr,
      offers: projectedOffers,
      recommendation: null,
    };
  }

  // 3. Find cheapest eligible projected total
  const totals = eligibleOffers.map((o) => parseFloat(o.projected_landed_cost.amount));
  const cheapestTotal = Math.min(...totals);

  // 4. Score each eligible offer (Research R2)
  interface ScoredCandidate {
    offer: ProjectedOffer;
    cost_score: number;
    match_confidence_score: number;
    reliability_score: number;
    lead_time_score: number;
    total_score: number;
  }

  const candidates: ScoredCandidate[] = eligibleOffers.map((offer) => {
    const offerTotal = parseFloat(offer.projected_landed_cost.amount);
    const cost_score = offerTotal > 0 ? Math.min(1.0, Math.max(0.0, cheapestTotal / offerTotal)) : 1.0;
    const match_confidence_score = Math.min(1.0, Math.max(0.0, parseFloat(offer.match_confidence) || 0.0));
    const reliability_score =
      offer.reliability_score !== null && offer.reliability_score !== undefined
        ? Math.min(1.0, Math.max(0.0, parseFloat(offer.reliability_score)))
        : 0.5;
    const lead_time_score =
      offer.lead_time_days !== null && offer.lead_time_days !== undefined
        ? 1.0 - Math.min(Math.max(0, offer.lead_time_days), 30) / 30.0
        : 0.5;

    const weightedScore =
      0.55 * cost_score +
      0.20 * match_confidence_score +
      0.15 * reliability_score +
      0.10 * lead_time_score;

    // Round to 4 decimal places for comparison
    const total_score = Math.round(weightedScore * 10000) / 10000;

    return {
      offer,
      cost_score,
      match_confidence_score,
      reliability_score,
      lead_time_score,
      total_score,
    };
  });

  // 5. Sort candidates by score, applying deterministic tie-breaks (Research R3)
  let tieBreakApplied = false;

  candidates.sort((a, b) => {
    if (Math.abs(a.total_score - b.total_score) > 0.00001) {
      return b.total_score - a.total_score;
    }

    // Scores tied, tie-break applied
    tieBreakApplied = true;

    // 1. Lower projected_total.amount
    const totalA = parseFloat(a.offer.projected_landed_cost.amount);
    const totalB = parseFloat(b.offer.projected_landed_cost.amount);
    if (Math.abs(totalA - totalB) > 0.0001) {
      return totalA - totalB;
    }

    // 2. Higher match_confidence
    const confA = parseFloat(a.offer.match_confidence) || 0;
    const confB = parseFloat(b.offer.match_confidence) || 0;
    if (Math.abs(confA - confB) > 0.0001) {
      return confB - confA;
    }

    // 3. Higher reliability_score (null last)
    const relA = a.offer.reliability_score !== null && a.offer.reliability_score !== undefined ? parseFloat(a.offer.reliability_score) : -1;
    const relB = b.offer.reliability_score !== null && b.offer.reliability_score !== undefined ? parseFloat(b.offer.reliability_score) : -1;
    if (relA !== relB) {
      return relB - relA;
    }

    // 4. Lower lead_time_days (null last)
    const leadA = a.offer.lead_time_days !== null && a.offer.lead_time_days !== undefined ? a.offer.lead_time_days : 999999;
    const leadB = b.offer.lead_time_days !== null && b.offer.lead_time_days !== undefined ? b.offer.lead_time_days : 999999;
    if (leadA !== leadB) {
      return leadA - leadB;
    }

    // 5. Later valid_to (null is open-ended => first)
    const timeA = a.offer.valid_to ? new Date(a.offer.valid_to).getTime() : Infinity;
    const timeB = b.offer.valid_to ? new Date(b.offer.valid_to).getTime() : Infinity;
    if (timeA !== timeB) {
      return timeB - timeA;
    }

    // 6. Lexicographic supplier.name
    const nameCmp = a.offer.supplier_name.localeCompare(b.offer.supplier_name);
    if (nameCmp !== 0) return nameCmp;

    // 7. Lexicographic supplier.id
    return a.offer.supplier_id.localeCompare(b.offer.supplier_id);
  });

  const winner = candidates[0];
  const runnerUp = candidates.length > 1 ? candidates[1] : null;
  const winningMargin = runnerUp ? Math.max(0, winner.total_score - runnerUp.total_score) : null;

  // 6. Calibrate confidence
  let confidence: RecommendationConfidence = 'low';
  if (winner.total_score >= 0.85) {
    if (winningMargin === null || winningMargin >= 0.05) {
      confidence = 'high';
    } else {
      confidence = 'medium';
    }
  } else if (winner.total_score >= 0.7) {
    confidence = 'medium';
  } else {
    confidence = 'low';
  }

  // 7. Risk notes
  const risk_notes: RecommendationRiskNote[] = [];
  if (winner.offer.valid_to) {
    const validToDate = new Date(winner.offer.valid_to);
    const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    if (validToDate.getTime() <= sevenDaysFromNow.getTime()) {
      risk_notes.push('price_expiring_soon');
    }
  }
  if (parseFloat(winner.offer.match_confidence) < 0.85) {
    risk_notes.push('low_match_confidence');
  }
  if (
    winner.offer.reliability_score !== null &&
    winner.offer.reliability_score !== undefined &&
    parseFloat(winner.offer.reliability_score) < 0.6
  ) {
    risk_notes.push('low_supplier_reliability');
  }

  const recommendation: Recommendation = {
    recommended_offer_id: winner.offer.id,
    score: winner.total_score.toFixed(4),
    confidence,
    valid_from: winner.offer.valid_from,
    valid_to: winner.offer.valid_to,
    risk_notes,
    evidence: {
      weights: {
        cost: '0.55',
        match_confidence: '0.20',
        reliability: '0.15',
        lead_time: '0.10',
      },
      components: {
        cost: winner.cost_score.toFixed(4),
        match_confidence: winner.match_confidence_score.toFixed(4),
        reliability: winner.reliability_score.toFixed(4),
        lead_time: winner.lead_time_score.toFixed(4),
      },
      winning_margin: winningMargin !== null ? winningMargin.toFixed(4) : null,
      tie_break: {
        applied: tieBreakApplied,
        rule: TIE_BREAK_RULES,
      },
    },
  };

  return {
    requested_quantity: newQuantityStr,
    offers: projectedOffers,
    recommendation,
  };
}
