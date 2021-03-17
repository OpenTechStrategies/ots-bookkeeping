#!/usr/bin/env python3
"""
Model a register of entries.
"""
import pprint

import util as u
from transaction import Transactions

pp = pprint.PrettyPrinter(indent=4).pprint


class UnimplementedError(Exception):
    pass


class UninheritedError(Exception):
    pass


class Register(Transactions):
    """A Register is a list of the transactions from an account"""

    def __init__(self, account):
        """ACCOUNT is a dict containing some information about an account:

        It probably has a 'ledger_file' field.  It might have a
        'ledger_accounts' field.

        'ledger_file' -=> filespec for beancount file
        'ledger_accounts' -=> a list of asset accounts we care about

        """
        Transactions.__init__(self)

        if str(type(self)) == "<class 'register.Register'>":
            raise UninheritedError(
                "Don't call this module directly. Use register.get_register(account)"
            )

        self.fname = account.get("ledger_file", "")
        self.accounts = account.get("ledger_accounts", "")
        self.register_text = self.load_reg_text()
        self.register_lines = [l for l in self.register_text.split("\n") if l]

    def get_txs(self, date=None):
        """ "Return the register we've loaded as a set of Transactions.

        if DATE is specified, just get transactions from that date.

        Override this in beancount.Register"""
        raise UnimplementedError("get_txs not implemented yet")

    def register_text(*arg):
        raise UnimplementedError("Register text should be overridden by inheritance.")


# We do imports after defining the Register class because the things
# we import depend on it. Circular imports!  Isn't Python grand?
