// Server-owned blocked snapshot; environment/HTTP/SDK state cannot override it.
export const LIVE_GATES = Object.freeze({
  SWAP_LIVE_GATE: "BLOCKED",
  RFQ_LIVE_GATE: "BLOCKED",
  AGENTIC_WALLET_LIVE_GATE: "BLOCKED",
});
export function requireLiveCapabilities() {
  throw new Error("AGENTIC_WALLET_LIVE_GATE_BLOCKED");
}
