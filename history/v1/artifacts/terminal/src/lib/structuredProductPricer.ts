// Client-side structured-product (barrier option) pricer.
// Ported 1:1 from artifacts/api-server/app/skills.py (build_structured_product
// and the _bs_* / _norm_* / _erf helpers) so traders can tweak inputs and see
// fair value, Greeks and scenario P&L update instantly without an API round-trip.

export type ProductTypeKey =
  | "down_and_out_call"
  | "up_and_out_call"
  | "down_and_in_put"
  | "up_and_in_call";

export interface PricerInputs {
  barrierPct: number; // percent, e.g. 85
  tenorMonths: number; // months
  notional: number; // currency
  strikePct: number; // percent, e.g. 100
}

export interface Scenario {
  label: string;
  spotMove: number;
  finalSpot: number;
  pnl: number;
  returnPct: number;
  probability: number;
}

export interface PricerResult {
  barrier: number;
  barrierPct: number;
  tenor: number; // years
  notional: number;
  strike: number;
  bsPrice: number;
  fairValue: number;
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  scenarios: Scenario[];
}

function erf(x: number): number {
  const sign = x >= 0 ? 1 : -1;
  x = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1.0 / (1.0 + p * x);
  const y =
    1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t) * Math.exp(-x * x);
  return sign * y;
}

function normCdf(x: number): number {
  return 0.5 * (1.0 + erf(x / Math.sqrt(2.0)));
}

function normPdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2.0 * Math.PI);
}

function bsPrice(
  S: number,
  K: number,
  T: number,
  r: number,
  sigma: number,
  optionType: "call" | "put",
): number {
  if (T <= 0 || sigma <= 0) {
    return optionType === "call" ? Math.max(S - K, 0) : Math.max(K - S, 0);
  }
  const d1 =
    (Math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  if (optionType === "call") {
    return S * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2);
  }
  return K * Math.exp(-r * T) * normCdf(-d2) - S * normCdf(-d1);
}

interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

function bsGreeks(
  S: number,
  K: number,
  T: number,
  r: number,
  sigma: number,
  optionType: "call" | "put",
): Greeks {
  if (T <= 0 || sigma <= 0) {
    const delta =
      optionType === "call" ? (S > K ? 1.0 : 0.0) : S < K ? -1.0 : 0.0;
    return { delta, gamma: 0.0, theta: 0.0, vega: 0.0 };
  }
  const d1 =
    (Math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  const pdfD1 = normPdf(d1);
  const delta = optionType === "call" ? normCdf(d1) : normCdf(d1) - 1.0;
  const gamma = pdfD1 / (S * sigma * Math.sqrt(T));
  const vega = (S * pdfD1 * Math.sqrt(T)) / 100.0;
  let theta: number;
  if (optionType === "call") {
    theta =
      (-S * pdfD1 * sigma) / (2 * Math.sqrt(T)) -
      r * K * Math.exp(-r * T) * normCdf(d2);
  } else {
    theta =
      (-S * pdfD1 * sigma) / (2 * Math.sqrt(T)) +
      r * K * Math.exp(-r * T) * normCdf(-d2);
  }
  theta = theta / 365;
  return { delta, gamma, theta, vega };
}

function round(n: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

export function productTypeFromLabel(label: string): ProductTypeKey {
  const raw = (label || "").toLowerCase();
  if (raw.includes("up") && raw.includes("out")) return "up_and_out_call";
  if (raw.includes("down") && raw.includes("in")) return "down_and_in_put";
  if (raw.includes("up") && raw.includes("in")) return "up_and_in_call";
  return "down_and_out_call";
}

// Re-price the barrier product entirely client-side. `S` is the spot price and
// `baseIv` is the (decimal) implied vol — both come unchanged from the server so
// the client math matches the server's pricing model exactly.
export function priceStructuredProduct(
  S: number,
  baseIv: number,
  productType: ProductTypeKey,
  inputs: PricerInputs,
): PricerResult {
  const r = 0.05;
  const tenor = inputs.tenorMonths / 12; // years
  const notional = inputs.notional;
  const strikePct = inputs.strikePct / 100;
  const barrierPct = inputs.barrierPct / 100;

  const K = round(S * strikePct, 2);
  const barrier = round(S * barrierPct, 2);

  const vanillaPrice = bsPrice(S, K, tenor, r, baseIv, "call");
  const vanillaGreeks = bsGreeks(S, K, tenor, r, baseIv, "call");

  let barrierPrice: number;
  if (productType === "down_and_out_call") {
    const lam = (r + 0.5 * baseIv ** 2) / baseIv ** 2;
    const reflS = barrier ** 2 / S;
    const reflPrice = bsPrice(reflS, K, tenor, r, baseIv, "call");
    barrierPrice = vanillaPrice - (barrier / S) ** (2 * lam) * reflPrice;
  } else if (productType === "up_and_out_call") {
    barrierPrice = vanillaPrice * Math.max(0, 1 - Math.max(0, S / barrier - 0.9));
  } else {
    const knockInProb = Math.exp(
      (-2 * Math.log(S / barrier) ** 2) / (baseIv ** 2 * tenor),
    );
    barrierPrice = vanillaPrice * Math.min(1, knockInProb + 0.3);
  }

  barrierPrice = Math.max(0.01, round(barrierPrice, 2));

  const ratio = vanillaPrice > 0 ? barrierPrice / vanillaPrice : 0.5;
  const delta = round(vanillaGreeks.delta * ratio, 4);
  const gamma = round(vanillaGreeks.gamma * ratio, 5);
  const vega = round(vanillaGreeks.vega * ratio, 4);
  const theta = round(vanillaGreeks.theta * ratio, 4);

  const spotMoves = [-0.3, -0.2, -0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2];
  const scenarios: Scenario[] = [];
  for (const move of spotMoves) {
    const finalSpot = round(S * (1 + move), 2);
    const pathMin = move < 0 ? finalSpot : S * 0.99;
    let intrinsic: number;
    let prob: number;
    if (productType === "down_and_out_call" && pathMin <= barrier) {
      intrinsic = 0.0;
      prob = 0.5 * Math.exp(-Math.abs(move) * 2);
    } else if (productType === "up_and_out_call" && finalSpot >= barrier) {
      intrinsic = 0.0;
      prob = 0.3 * Math.exp(-Math.abs(move) * 1.5);
    } else {
      intrinsic = Math.max(finalSpot - K, 0);
      prob = 0.6 * Math.exp(-Math.abs(move) * 1.5);
    }

    const pnlPerShare = intrinsic - barrierPrice;
    const pnlTotal = round((pnlPerShare * notional) / S, 0);
    const returnPct =
      barrierPrice > 0 ? round((pnlPerShare / barrierPrice) * 100, 1) : 0.0;

    const label = `${move >= 0 ? "+" : ""}${Math.trunc(move * 100)}%`;
    scenarios.push({
      label,
      spotMove: round(move * 100, 1),
      finalSpot,
      pnl: pnlTotal,
      returnPct,
      probability: round(prob, 3),
    });
  }

  const fairValue = round((barrierPrice * notional) / S, 2);

  return {
    barrier,
    barrierPct: round(barrierPct * 100, 1),
    tenor,
    notional,
    strike: K,
    bsPrice: vanillaPrice,
    fairValue,
    delta,
    gamma,
    vega,
    theta,
    scenarios,
  };
}
