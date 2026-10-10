// Experimental teammate SDK implementation retained behind a non-configurable gate.
// No environment variable, token, CLI flag or session can enable this entry point.
import { pathToFileURL } from "node:url";
import { requireLiveCapabilities } from "./execution-gates.mjs";
import { writeFileSync } from "node:fs";

export async function grantSession() {
  requireLiveCapabilities();
// One-time setup: create (or reuse) the operator's Altana wallet on BSC mainnet and grant
// Parity Pulse a scoped session key. Optional: mint an ERC-8004 agent identity.
//
//   ALTANA_OWNER_PRIVATE_KEY=0x... ALTANA_SESSION_FILE=./altana-session.json \
//   SESSION_DAILY_USDT=50 SESSION_DAYS=3 node grant-session.mjs [--register-agent]
//
// The session may only: call the Binance LiquidMesh router (swaps), call approve() on USDT
// and the configured stock tokens, spend at most SESSION_DAILY_USDT USDT/day and
// SESSION_DAILY_BNB/day for relay gas, until expiry. Revoke any time from the owner key.
const {
  BNB,
  createClient,
  createPrivateKeySigner,
  registerErc8004Agent,
  serializeSession,
  signerFromPrivateKey,
} = await import("@altananetwork/sdk");

const env = process.env;
const ROUTER = (env.SWAP_ROUTER ?? "0xb44446b0c8e56988c34f7ff73ae904982b5fdda5").toLowerCase();
const USDT = "0x55d398326f99059ff775485246999027b3197955";
const STOCKS = (env.STOCK_TOKENS ??
  "0x02fca66c1d1afb4e2a7884261eb00f63598a7436,0xa9ee28c80f960b889dfbd1902055218cba016f75")
  .split(",")
  .map((a) => a.trim().toLowerCase());
const usd = BigInt(env.SESSION_DAILY_USDT ?? "50");
const bnbWei = BigInt(Math.round(Number(env.SESSION_DAILY_BNB ?? "0.01") * 1e18));
const days = Number(env.SESSION_DAYS ?? "3");

if (!env.ALTANA_OWNER_PRIVATE_KEY || !env.ALTANA_SESSION_FILE) {
  console.error("ALTANA_OWNER_PRIVATE_KEY and ALTANA_SESSION_FILE are required");
  process.exit(2);
}

const client = createClient({ chains: [BNB] });
const owner = signerFromPrivateKey(env.ALTANA_OWNER_PRIVATE_KEY);
const wallet = await client.createWallet({ signer: owner });
console.log(JSON.stringify({ event: "ALTANA_WALLET", address: wallet.address }));

const sessionSigner = createPrivateKeySigner();
const session = await client.grantSession({
  wallet,
  signer: owner,
  chainId: 56,
  sessionSigner,
  expiry: Math.floor(Date.now() / 1000) + days * 86400,
  permissions: {
    calls: [
      { to: ROUTER },
      { signature: "approve(address,uint256)", to: USDT },
      ...STOCKS.map((to) => ({ signature: "approve(address,uint256)", to })),
    ],
    spend: [
      { limit: usd * 10n ** 18n, period: "day", token: USDT },
      { limit: bnbWei, period: "day" },
    ],
  },
});
writeFileSync(
  env.ALTANA_SESSION_FILE,
  JSON.stringify({ session: serializeSession(session), sessionKey: sessionSigner._privateKey }),
  { mode: 0o600 },
);
console.log(
  JSON.stringify({
    event: "ALTANA_SESSION_GRANTED",
    wallet: session.walletAddress,
    expiry: session.expiry,
    tx: session.transactionHash ?? null,
  }),
);

// RFQ via CowSwap with an Altana wallet needs the settlement contract approved as an
// ERC-1271 signature checker: --approve-checker 0x9008D19f58AAbD9eD0D60971565AA8510560ab41
const checkerFlag = process.argv.indexOf("--approve-checker");
if (checkerFlag > 0) {
  const checker = process.argv[checkerFlag + 1];
  const result = await client.approveSignatureChecker({ wallet, signer: owner, session, checker, chainId: 56 });
  console.log(JSON.stringify({ event: "SIGNATURE_CHECKER_APPROVED", checker, tx: result.transactionHash ?? null }));
}

if (process.argv.includes("--register-agent")) {
  const card = {
    type: "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
    name: "Parity Pulse",
    description:
      "Tokenized-stock portfolio rebalancer on BSC: drift-band rebalancing across Ondo and bStock " +
      "representations with Binance-simulated, capped, on-chain-reconciled execution.",
    services: env.X402_PUBLIC_URL ? [{ name: "x402", endpoint: env.X402_PUBLIC_URL }] : [],
  };
  const agentUri =
    "data:application/json;base64," + Buffer.from(JSON.stringify(card)).toString("base64");
  const result = await registerErc8004Agent(wallet, owner, { agentUri }, { network: BNB });
  console.log(JSON.stringify({ event: "ERC8004_REGISTERED", agentId: result.agentId.toString(), tx: result.transactionHash ?? null }));
}

}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  grantSession().catch(() => {
    console.error("AGENTIC_WALLET_LIVE_GATE_BLOCKED: no SDK action performed");
    process.exitCode = 2;
  });
}
