"""Official baw read commands only. No shell, authentication, previews or writes."""

import json
import os
import selectors
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.clients.common import unique_object
from app.models.execution import address, units

REQUIRED_CLI_VERSION = "1.10.0"
SKILL_VERSION = "1.12.0"
MAX_OUTPUT = 1_048_576


class WalletReadError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)  # Never expose CLI stderr, stdout or exception text.


def command(operation, **params):
    """Closed command grammar; arbitrary arguments/operations never reach subprocess."""
    if (
        "pending" in params
        and params["pending"] is not None
        and type(params["pending"]) is not bool
    ):
        raise WalletReadError("COMMAND_DENIED")
    simple = {"status", "address", "chains", "settings"}
    if operation == "help" and not params:
        return ("--help",)
    if operation == "contract-help" and not params:
        return ("contract-call", "--help")
    if operation in simple and not params:
        return ("wallet", operation, "--json")
    if operation == "cli-check" and not params:
        return ("cli-check", "--required-version", REQUIRED_CLI_VERSION, "--json")
    if operation in {"balance", "tx-lock"} and not params:
        return ("wallet", operation, "--binanceChainId", "56", "--json")
    if operation == "history" and set(params) <= {"tx_hash", "pending"}:
        args = ["wallet", "tx-history", "--binanceChainId", "56", "--size", "100"]
        if params.get("pending") is True:
            args += ["--type", "pending"]
        elif params.get("pending") not in (None, False):
            raise WalletReadError("COMMAND_DENIED")
        if params.get("tx_hash") is not None:
            from pydantic import TypeAdapter

            from app.models.execution import Hash

            value = TypeAdapter(Hash).validate_python(params["tx_hash"])
            args += ["--tx", value]
        return tuple(args + ["--json"])
    if operation == "orders" and set(params) <= {"order_id", "pending"}:
        args = ["market-order", "list"]
        if params.get("order_id") is not None:
            from pydantic import TypeAdapter

            from app.models.execution import Identifier

            order_id = TypeAdapter(Identifier).validate_python(params["order_id"])
            if order_id.startswith("-"):
                raise WalletReadError("COMMAND_DENIED")
            args += ["--orderId", order_id]
        else:
            args += ["--binanceChainId", "56", "--pageSize", "100", "--page", "1"]
            if params.get("pending") is True:
                args += ["--status", "PENDING"]
        if params.get("pending") not in (None, False, True):
            raise WalletReadError("COMMAND_DENIED")
        return tuple(args + ["--json"])
    if operation == "quote" and set(params) == {"sell", "buy", "quantity", "slippage_bps"}:
        sell, buy = address(params["sell"]), address(params["buy"])
        from app.models.data import financial

        qty, slip = financial(params["quantity"]), financial(params["slippage_bps"])
        if (
            sell == buy
            or not 0 < qty <= Decimal("1e60")
            or len(qty.as_tuple().digits) > 96
            or abs(qty.adjusted()) > 72
            or not 0 <= slip <= 10000
            or len(slip.as_tuple().digits) > 10
            or abs(slip.adjusted()) > 72
        ):
            raise WalletReadError("COMMAND_DENIED")
        return (
            "market-order",
            "quote",
            "--fromTokenQty",
            format(qty, "f"),
            "--fromToken",
            sell,
            "--toToken",
            buy,
            "--binanceChainId",
            "56",
            "--slippage",
            format(slip / Decimal(100), "f"),
            "--json",
        )
    raise WalletReadError("COMMAND_DENIED")


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_OUTPUT:
        raise WalletReadError("OUTPUT_INVALID")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_float=Decimal,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        if not isinstance(value, dict) or type(value.get("success")) is not bool:
            raise ValueError()
        if not value["success"]:
            raise WalletReadError("WALLET_READ_DENIED")
        if "error" in value and value["error"] is not None:
            raise ValueError()
        return value["data"]
    except WalletReadError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise WalletReadError("OUTPUT_INVALID") from None


def verify_argv(args):
    """Defense in depth: even the subprocess boundary cannot accept raw write arguments."""
    if not isinstance(args, tuple) or not all(isinstance(v, str) for v in args):
        raise WalletReadError("COMMAND_DENIED")
    for operation in (
        "help",
        "contract-help",
        "cli-check",
        "status",
        "chains",
        "address",
        "settings",
        "balance",
        "tx-lock",
    ):
        if args == command(operation):
            return
    if len(args) < 3 or args[-1] != "--json" or (len(args) - 3) % 2:
        raise WalletReadError("COMMAND_DENIED")
    pairs = list(zip(args[2:-1:2], args[3:-1:2], strict=True))
    flags = dict(pairs)
    if len(pairs) != len(flags):
        raise WalletReadError("COMMAND_DENIED")
    if args[:2] == ("market-order", "list"):
        if set(flags) == {"--orderId"}:
            expected = command("orders", order_id=flags["--orderId"])
        elif flags.get("--status") in {None, "PENDING"}:
            expected = command("orders", pending=flags.get("--status") == "PENDING")
        else:
            raise WalletReadError("COMMAND_DENIED")
    elif args[:2] == ("wallet", "tx-history"):
        if flags.get("--type") not in {None, "pending"}:
            raise WalletReadError("COMMAND_DENIED")
        expected = command(
            "history", tx_hash=flags.get("--tx"), pending=flags.get("--type") == "pending"
        )
    elif args[:2] == ("market-order", "quote") and set(flags) == {
        "--fromTokenQty",
        "--fromToken",
        "--toToken",
        "--binanceChainId",
        "--slippage",
    }:
        from decimal import localcontext

        from app.models.data import financial

        with localcontext() as ctx:
            ctx.prec = 256
            slip = financial(flags["--slippage"])
            if abs(slip.adjusted()) > 72:
                raise WalletReadError("COMMAND_DENIED")
            expected = command(
                "quote",
                sell=flags["--fromToken"],
                buy=flags["--toToken"],
                quantity=flags["--fromTokenQty"],
                slippage_bps=slip * 100,
            )
    else:
        raise WalletReadError("COMMAND_DENIED")
    if args != expected:
        raise WalletReadError("COMMAND_DENIED")


class BawReadOnlyClient:
    fixture_only = False

    def __init__(self, *, enabled=False, executable=None, timeout=10, clock=None):
        if type(enabled) is not bool or not 1 <= timeout <= 10:
            raise ValueError("Explicit read-only worker with bounded timeout required")
        self.enabled, self.timeout = enabled, timeout
        self.clock = clock or (lambda: datetime.now(UTC))
        found = executable or (shutil.which("baw") if enabled else None)
        self.executable = Path(found).resolve() if found else None
        self.version_verified = False

    def _verify(self, args):
        verify_argv(args)

    def _run(self, args):
        try:
            self._verify(args)
        except (ValueError, TypeError, KeyError):
            raise WalletReadError("COMMAND_DENIED") from None
        if not self.enabled:
            raise WalletReadError("WORKER_READS_DISABLED")
        if self.executable is None or not self.executable.is_file():
            raise WalletReadError("BAW_UNAVAILABLE")
        # Session remains CLI-owned. Do not pass project/API secrets or NODE_OPTIONS.
        env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ}
        process = None
        try:
            process = subprocess.Popen(
                [str(self.executable), *args],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            result = bytearray()
            deadline = time.monotonic() + self.timeout
            with selectors.DefaultSelector() as ready:
                ready.register(process.stdout, selectors.EVENT_READ)
                while True:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise WalletReadError("WALLET_READ_TIMEOUT")
                    if not ready.select(min(left, 0.25)):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    result.extend(chunk)
                    if len(result) > MAX_OUTPUT:
                        raise WalletReadError("OUTPUT_TOO_LARGE")
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if process.returncode != 0:
                raise WalletReadError("CLI_READ_FAILED")
            return bytes(result)
        except (OSError, subprocess.SubprocessError):
            raise WalletReadError("CLI_READ_UNAVAILABLE") from None
        finally:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                process.stdout.close()

    def read(self, operation, **params):
        try:
            args = command(operation, **params)
        except (ValueError, TypeError):
            raise WalletReadError("COMMAND_DENIED") from None
        if operation != "cli-check" and not self.version_verified:
            check = decode(self._run(command("cli-check")))
            if (
                not isinstance(check, dict)
                or check.get("currentCliVersion") != REQUIRED_CLI_VERSION
                or check.get("needUpdateCli") is not False
            ):
                raise WalletReadError("CLI_VERSION_NOT_VERIFIED")
            self.version_verified = True
        start = self.clock()
        payload = decode(self._run(args))
        return payload, start, self.clock()

    def mutate(self, *_args, **_kwargs):
        raise WalletReadError("WALLET_MUTATION_DISABLED")


def human_base_units(quantity, decimals):
    from decimal import localcontext

    from app.models.data import financial

    qty = financial(quantity)
    if type(decimals) is not int or not 0 <= decimals <= 36 or qty < 0:
        raise ValueError("Invalid verified token units")
    if len(qty.as_tuple().digits) > 96 or abs(qty.adjusted()) > 72:
        raise ValueError("Unsupported financial precision")
    with localcontext() as ctx:
        ctx.prec = 256
        result = qty * Decimal(10) ** decimals
        if result != result.to_integral_value():
            raise ValueError("Balance has unverified fractional base units")
    return units(format(result, ".0f"))
