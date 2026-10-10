// Experimental teammate SDK implementation retained behind a non-configurable gate.
// No environment variable, token, CLI flag or session can enable this entry point.
import { pathToFileURL } from "node:url";
import { requireLiveCapabilities } from "./execution-gates.mjs";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { timingSafeEqual } from "node:crypto";

export async function startSidecar() {
  requireLiveCapabilities();
// Parity Pulse x BNB Agent Studio sidecar (localhost only).
//
// 1. Altana execution: POST /altana/execute runs one call batch through a scoped Altana
//    session key (on-chain spend limits, call allowlist, expiry) on BSC mainnet. The Python
//    LiveRebalanceExecutor uses it as the "ALTANA" signer after Binance simulation passes.
// 2. x402 selling: GET /x402/parity/:ticker is a paid endpoint (B402 v2 wire, USDT/U on BSC)
//    payable by Agent Studio buyers (`bag x402 buy`) and Altana `fetchWithX402`. It proxies the
//    Parity Pulse tokenized-stock vs equity-index parity signal.
const { BNB, createClient, deserializeSession, signerFromPrivateKey } = await import("@altananetwork/sdk");
const { createX402Merchant, U_TOKEN, USDT_BSC } = await import("@altananetwork/x402-server");
const { privateKeyToAccount } = await import("viem/accounts");
const { bsc } = await import("viem/chains");

const env = process.env;
const PORT = Number(env.SIDECAR_PORT ?? 8787);
const PARITY_API = env.PARITY_API ?? "http://127.0.0.1:8000";
const TOKEN = env.SIDECAR_TOKEN ?? "";
const PERMIT2 = "0x31c2F6FcFF4F8759b3Bd5Bf0e1084A055615c768";

const client = createClient({ chains: [BNB] });

function loadSession() {
  if (!env.ALTANA_SESSION_FILE) return null;
  const stored = JSON.parse(readFileSync(env.ALTANA_SESSION_FILE, "utf8"));
  return deserializeSession(stored.session, signerFromPrivateKey(stored.sessionKey));
}
const session = loadSession();

const merchant =
  env.X402_PAY_TO && env.X402_FACILITATOR_KEY
    ? createX402Merchant({
        chainId: 56,
        payTo: env.X402_PAY_TO,
        price: BigInt(env.X402_PRICE ?? "10000000000000000"), // 0.01 (18-decimals stable)
        rails: [
          { rail: "eip3009", token: U_TOKEN[56] },
          { rail: "permit2-exact", token: USDT_BSC, spender: PERMIT2 },
        ],
        description: "Parity Pulse: tokenized-stock vs equity-index parity (BSC)",
        facilitator: privateKeyToAccount(env.X402_FACILITATOR_KEY),
        rpcUrl: env.BSC_RPC_URL ?? "https://bsc-dataseed.bnbchain.org",
        chain: bsc,
      })
    : null;

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body, (_, v) => (typeof v === "bigint" ? v.toString() : v)));
}

function authorized(req) {
  const given = Buffer.from(req.headers["x-sidecar-token"] ?? "");
  const want = Buffer.from(TOKEN);
  return TOKEN.length >= 16 && given.length === want.length && timingSafeEqual(given, want);
}

async function body(req) {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 262144) throw new Error("body too large");
  }
  return JSON.parse(raw || "{}");
}

const HEX = /^0x[0-9a-fA-F]*$/;
const ADDRESS = /^0x[0-9a-fA-F]{40}$/;

async function handle(req, res) {
  const url = new URL(req.url, "http://localhost");
  if (req.method === "GET" && url.pathname === "/altana/status") {
    if (!session) return json(res, 404, { error: "ALTANA_SESSION_NOT_CONFIGURED" });
    return json(res, 200, {
      wallet: session.walletAddress.toLowerCase(),
      expiry: session.expiry,
      permissions: session.permissions,
      chainId: 56,
    });
  }
  if (req.method === "POST" && url.pathname === "/altana/execute") {
    if (!authorized(req)) return json(res, 401, { error: "UNAUTHORIZED" });
    if (!session) return json(res, 404, { error: "ALTANA_SESSION_NOT_CONFIGURED" });
    if (session.expiry * 1000 <= Date.now()) return json(res, 409, { error: "SESSION_EXPIRED" });
    const { to, data, value } = await body(req);
    if (!ADDRESS.test(to) || !HEX.test(data) || !/^[0-9]+$/.test(String(value))) {
      return json(res, 422, { error: "INVALID_CALL" });
    }
    const result = await client.execute({
      session,
      chainId: 56,
      calls: [{ to, data, value: BigInt(value) }],
    });
    return json(res, result.status === "FAILED" ? 409 : 200, result);
  }
  if (req.method === "POST" && url.pathname === "/altana/sign-typed-data") {
    // ERC-1271 signature for an RFQ order the Python verifier already bounded. The vendor's
    // settlement contract must have been approved once with approveSignatureChecker.
    if (!authorized(req)) return json(res, 401, { error: "UNAUTHORIZED" });
    if (!session) return json(res, 404, { error: "ALTANA_SESSION_NOT_CONFIGURED" });
    const { typedData } = await body(req);
    if (!typedData?.domain || !typedData?.types || !typedData?.message || !typedData?.primaryType) {
      return json(res, 422, { error: "INVALID_TYPED_DATA" });
    }
    if (Number(typedData.domain.chainId) !== 56) return json(res, 422, { error: "WRONG_CHAIN" });
    const { EIP712Domain, ...types } = typedData.types; // viem derives the domain type itself
    const signature = await client.signOrderTypedData({
      session,
      typedData: { ...typedData, types },
    });
    return json(res, 200, { signature, wallet: session.walletAddress.toLowerCase() });
  }
  if (req.method === "GET" && url.pathname === "/x402") {
    return json(res, 200, {
      service: "parity-pulse",
      paid: merchant ? ["/x402/parity/:ticker"] : [],
      challenge: merchant ? merchant.challengeBody() : null,
    });
  }
  const paid = url.pathname.match(/^\/x402\/parity\/([A-Z][A-Z0-9.]{0,15})$/);
  if (req.method === "GET" && paid) {
    if (!merchant) return json(res, 503, { error: "X402_SELLER_NOT_CONFIGURED" });
    const request = new Request(url, { headers: req.headers });
    const { response, receipt } = await merchant.guard(request);
    if (response) {
      res.writeHead(402, { "content-type": "application/json" });
      return res.end(await response.text());
    }
    const upstream = await fetch(`${PARITY_API}/api/live/parity/${paid[1]}`);
    const signal = await upstream.json();
    return json(res, upstream.ok ? 200 : 502, { signal, payment: receipt });
  }
  return json(res, 404, { error: "NOT_FOUND" });
}

createServer((req, res) => {
  handle(req, res).catch(() =>
    json(res, 500, { error: "SIDECAR_ERROR", detail: "Provider failure; details suppressed" }),
  );
}).listen(PORT, "127.0.0.1", () => {
  console.log(
    JSON.stringify({ event: "SIDECAR_READY", port: PORT, altana: Boolean(session), x402: Boolean(merchant) }),
  );
});

}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  startSidecar().catch(() => {
    console.error("AGENTIC_WALLET_LIVE_GATE_BLOCKED: no SDK action performed");
    process.exitCode = 2;
  });
}
