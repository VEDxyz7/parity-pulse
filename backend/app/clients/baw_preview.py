"""Official contract-call preview only, reusing the bounded read-only subprocess."""

from app.clients.baw_cli import BawReadOnlyClient, WalletReadError, decode, verify_argv
from app.models.execution import EvmTransaction, address, hex_data, units


def preview_command(tx):
    tx = EvmTransaction.model_validate_json(tx.model_dump_json())
    return (
        "contract-call",
        "preview",
        "--binanceChainId",
        "56",
        "--from",
        tx.sender,
        "--to",
        tx.to,
        "--value",
        tx.value,
        "--inputData",
        tx.data,
        "--json",
    )


def verify_preview_argv(args):
    if isinstance(args, tuple) and args[:2] == ("contract-call", "preview"):
        if (
            len(args) != 13
            or args[2::2]
            != ("--binanceChainId", "--from", "--to", "--value", "--inputData", "--json")
            or args[3] != "56"
        ):
            raise WalletReadError("COMMAND_DENIED")
        try:
            if (
                address(args[5]) != args[5]
                or address(args[7]) != args[7]
                or units(args[9]) != args[9]
                or hex_data(args[11]) != args[11]
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise WalletReadError("COMMAND_DENIED") from None
    else:
        verify_argv(args)


class BawPreviewClient(BawReadOnlyClient):
    """No execute, auth or message-signing command is accepted by this client."""

    def _verify(self, args):
        verify_preview_argv(args)

    def preview(self, tx):
        if not self.version_verified:
            raise WalletReadError("CLI_VERSION_NOT_VERIFIED")
        started = self.clock()
        result = decode(self._run(preview_command(tx)))
        return result, started, self.clock()
