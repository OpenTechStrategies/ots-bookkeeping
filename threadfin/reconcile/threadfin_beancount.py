"""
Routines related to beancount files.
"""
import datetime
import math
import pprint
import re
import sys
from typing import Any, Dict, List, Optional

import beancount  # type: ignore
import petl as etl  # type: ignore
from beancount import loader
from dateutil import parser as dateparse
from moneyed import Money  # type: ignore

import mustache
import util as u

pp = pprint.PrettyPrinter(indent=4).pprint

settings = {}  # type: Dict[str,Any]


class UnimplementedError(Exception):
    pass


class Transaction(Dict[str, Any]):
    """This is a wrapper class around a beancount transaction."""

    def __init__(self, tx: beancount.core.data.Transaction) -> None:
        dict.__init__(self)
        self.tx = tx

    def as_beancount(self) -> str:
        """Return string with this transaction as a beancount entry."""
        payee = getattr(self.tx, "narration", "")

        if hasattr(self.tx, "category"):
            comment = self.tx.category
        elif "comment" in self.tx.meta:
            comment = self.tx.meta["comment"]
        else:
            comment = ""
        # meta = self.tx.meta['comment']
        # comment = getattr(self.tx, 'category', meta)

        narration = ""

        payer = "Karl"
        if payee[-4:] in "4082 ":
            payer = "James"

        # This stuff definitely should move to a config file somewhere.
        payee_xlation = {
            r"^Amazon Web Services Aws.Amazon.CO": [
                "Amazon Web Services",
                "AWS",
                "split",
            ],
            r"^Amtrak .Com ": ["Amtrak", "", ""],
            r"^Amtrak Hotels ": ["Amtrak Hotels", "", ""],
            r"^Digitalocean.Com Digitalocean. NY.*7681": ["Digital Ocean", "", "split"],
            r"^Google \*Gsuite_Opent": ["Google", "", "split"],
            r"^Linode.Com 855-4546633 NJ": ["Linode", "", "split"],
            r"^Lyft \*Ride": ["Lyft", "", ""],
            r"^Rimu Hosting Cambridge": ["Rimu", "", "split"],
            r"^Twilio .* CA ": ["Twilio", "", "split"],
            r"^United [0-9]+ 800.*TX": ["United Airlines", "", ""],
        }

        # Split means "split this expense between Karl and James"
        split = False

        for regex, replacement in payee_xlation.items():
            if re.search(regex, payee):
                comment += " " + payee
                payee = replacement[0]
                narration = replacement[1]
                if replacement[2] == "split":
                    split = True

        # Once upon a time, I tried to do something smart with the odd
        # pennies, but I don't really recall, and it's not worth
        # solving.
        if split:
            half = float(self["amount"].amount) / 2.0
            up = math.ceil(half * 100) / 100  # round up
            down = math.floor(half * 100) / 100  # round down
        else:
            up = 0
            down = self["amount"].amount

        if payer == "James":
            up, down = down, up

        h = {
            "date": self.tx.date,
            "payee": payee,
            "narration": narration,
            "comment": comment,
            "e_karl": down * -1,
            "e_james": up * -1,
            "a_karl": down,
            "a_james": up,
        }
        b = """{date} txn "{payee}" "{narration}"
  comment: "{comment}"
  Expenses:Karl              {e_karl} USD
  Expenses:James             {e_james} USD
  Assets:Checking:Karl       {a_karl} USD
  Assets:Checking:James      {a_james} USD

""".format(
            **h
        )

        ret = "\n".join([l for l in b.split("\n") if " 0 USD" not in l])
        ret = ret.replace(" ", r"&nbsp;").replace("\n", "<br />\n")
        return ret.strip()

    def dump(self) -> str:
        entry = self.tx
        ret = ""
        for d in dir(entry):
            if d.startswith("_"):
                continue
            if "__call__" in dir(entry.__getattribute__(d)):
                continue
            ret += "%s: %s\n" % (d, entry.__getattribute__(d))
        print(ret)
        return ret
        return "{0.date}".format(entry)

    def get_postings(self, accounts: List[str]) -> List[str]:
        "Return a list of postings that match any of the account names in list ACCOUNTS"

        ret = []
        for p in self.tx.postings:
            for a in accounts:
                if p.account.startswith(a):
                    ret.append(p)
        return ret

    def hits_account(self, account_name: str) -> bool:
        """ACCOUNT_NAME is a (partial) account name

        Returns True iff ACCOUNT_NAME appears at the start of at least
        one of the posting accounts.

        """
        if [p for p in self.tx.postings if p.account.startswith(account_name)]:
            return True
        return False

    def hits_accounts(self, account_names: List[str]) -> bool:
        """ACCOUNT_NAMES is list of (partial) account names

        Returns True iff a name in ACCOUNT_NAMES appears at the start
        of at least one of the posting accounts.

        """
        for name in account_names:
            if self.hits_account(name):
                return True
        return False

    def html(self) -> str:
        # Grab all the metadata fields except the ones whose keys
        # start with underscore and handle linebreaks
        meta = [
            {"item": "%s: %s" % (k, str(self.tx.meta[k]).replace("\n", "<br>"))}
            for k in self.tx.meta
            if not k.startswith("_")
        ]

        # Render and return
        return mustache.render(
            settings["templates"],
            "beancount_tx",
            {
                "amount": self["amount"].amount,
                "meta": meta,
                "narration": self.tx.narration,
                "payee": self.tx.payee,
                "payment_direction": "to" if self["amount"].amount < 0 else "from",
            },
        )

    def calc_amount(self, accounts: List[str]) -> None:
        """Set self['amount'] to the calculated amount in the postings we care
        about."""
        self["amount"] = 0
        for account in accounts:
            self["amount"] += Money(
                sum(
                    [
                        p.units.number
                        for p in self.tx.postings
                        if p.account.startswith(account)
                    ]
                ),
                currency="USD",
            )


class Register(List[Transaction]):
    """Model a beancount register as a series of Transactions"""

    def __init__(self, account: Dict[str, Any]) -> None:
        """ACCOUNT is a dict containing some information about an account:

        It probably has a 'ledger_file' field.  It might have a
        'ledger_accounts' field.

        'ledger_file' -=> filespec for beancount file
        'ledger_accounts' -=> a list of asset accounts we care about

        """

        self.fname = account.get("ledger_file", "")
        self.accounts = account.get("ledger_accounts", "")
        self.register_text = self.load_reg_text()
        self.register_lines = [l for l in self.register_text.split("\n") if l]

        # Use beancount's loader to load our entries
        entries, self.errors, self.options = loader.load_file(account["ledger_file"])

        # Entries come sorted from the beancount loader, so let's
        # just save them and be happy.
        self.extend(entries)

    def get_accounts(self) -> List[beancount.core.data.Open]:
        return [e for e in self if isinstance(e, beancount.core.data.Open)]

    def get_txs(
        self, date: Optional[datetime.datetime] = None
    ) -> List[beancount.core.data.Transaction]:
        if not date:
            return [
                Transaction(e)
                for e in self
                if isinstance(e, beancount.core.data.Transaction)
            ]

        # if isinstance(date, str):
        #     date = dateparse.parse(date).date()

        return [e for e in self.get_txs() if e.tx.date == date]

    def load_reg_text(
        self,
        start: Optional[datetime.datetime] = None,
        end: Optional[datetime.datetime] = None,
    ) -> str:
        """Return a string with ledger register entries for the account in
        self.account.  Get the register from beancount and return it

        START is an optional start date, it will include from that day forward.

        END is an optional end date, it will exclude from that day forward.

        START and END aren't implemented yet.

        """

        if start or end:
            raise UnimplementedError("Start and End not implemented yet")

        lines = []  # type: List[str]
        for account in self.accounts:
            query = (
                f"SELECT id, date, account, position, balance "
                "WHERE account~'{account}'"
            )
            query_result = u.bean_query(self.fname, query).split("\n")[2:]
            if not lines:
                lines = query_result
            else:
                lines.extend(query_result[2:])

        # Remove cruft
        # lines = [l for l in lines
        #         if l
        #         and not '----------' in l
        #         and not l.strip().startswith('date')]

        ret = "\n".join(lines)
        return ret

    def load_txs(self) -> None:
        """Load transactions into the register.

        It appears this code doesnt get called from anywhere in our codebase.
        It also appears to reference self.account, when that var doesn't exist.
        Maybe we should remove it."""

        query = (
            "SELECT id, date, account, payee, position, balance WHERE account~'%s'"
            % (self.account)
        )
        csv = u.bean_query_csv(self.fname, query)
        reg = etl.fromcsv(u.OpenableIOString(csv))

        # Save the rows because we can't reopen our byte stream
        rows = []
        for row in reg:
            rows.append(row)

        headers = rows[0]
        for row in rows[1:]:
            row_dict = {}
            for i in range(len(headers)):
                row_dict[headers[i]] = row[i].strip()
            row_dict["date"] = dateparse.parse(row_dict["date"])
            a, c = re.split(" +", row_dict["position"])
            row_dict["amount"] = Money(a, c)
            self.append(Transaction(row_dict))

    def parse_line(self, line: str) -> Dict[str, Any]:
        """Parse the date and amount out of the register LINE.

        Returns a dict with date and amount keys."""

        parts = [t for t in line.split(" ") if t]
        if len(parts) != 6:
            print(line)
            print(parts)
        return {}
        sys.exit()
        return {
            "id": parts[0],
            "date": dateparse.parse(parts[1]),
            "account": parts[2],
            "amount": parts[3],
            "total": parts[4],
        }


def get_register(account: Dict[str, Any]) -> Register:
    """Returns a Register class for beancount.

    ACCOUNT is a dict with at least a 'ledger_file' field.

    """

    reg = Register(account)
    if len(reg) == 0:
        u.err("Register is empty of journal entries.")
    return reg
