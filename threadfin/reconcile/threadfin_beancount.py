"""
Routines related to beancount files.
"""
import math
import util as u
import sys
import register
import subprocess
import re

import beancount
from beancount import loader
from dateutil import parser as dateparse
import io
from money import Money
import mustache
import os
import petl as etl
import pprint
pp = pprint.PrettyPrinter(indent=4).pprint


class UnimplementedError(Exception):
    pass


class OpenableIOString():
    def __init__(self, in_string, byte=True):
        """PETL expects an openable file-like object, but all we have is an
        iostring.  Rather than write it to disk and then call PETL to
        read it, we'll wrap the iostring in this class that implements
        open.

        If BYTES is true, we'll encode as a byte stream, otherwise,
        we'll use stream io.  PETL wants bytes, as it tries to open
        with 'wb'.  Hmm... maybe we should just encode as needed in
        the open method.

        """
        if byte:
            self.io = io.BytesIO(in_string.encode("UTF-8"))
        else:
            self.io = io.StringIO(in_string)

    def open(self, *args, **kwargs):
        return self.io


def dump_entry(self):
    return self


class Transaction(dict):
    def __init__(self, tx):
        dict.__init__(self)
        self.tx = tx

    def as_beancount(self):
        """Return string with this transaction as a beancount entry."""
        payee = getattr(self.tx, 'narration', '')
        comment = getattr(self.tx, 'category', '')
        narration = ''

        payer = "Karl"
        if payee[-4:] in "4082 ":
            payer = "James"

        payee_xlation = {
            r"^Amazon Web Services Aws.Amazon.CO": ["Amazon Web Services", "AWS", "split"],
            r"^Amtrak .Com ": ["Amtrak", "", ""],
            r"^Amtrak Hotels ": ["Amtrak Hotels", "", ""],
            r"^Digitalocean.Com Digitalocean. NY.*7681": ["Digital Ocean", "", "split"],
            r"^Google \*Gsuite_Opent": ["Google", "", "split"],
            r"^Linode.Com 855-4546633 NJ": ["Linode", "", "split"],
            r"^Lyft \*Ride": ["Lyft", "", ""],
            r"^Rimu Hosting Cambridge": ["Rimu", "", "split"],
            r"^Twilio .* CA ": ["Twilio", "", "split"],
            r"^United [0-9]+ 800.*TX": ["United Airlines", "", ""]
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
            half = float(self['amount'].amount) / 2.0
            up = math.ceil(half * 100) / 100  # round up
            down = math.floor(half * 100) / 100  # round down
        else:
            up = 0
            down = self['amount'].amount

        if payer == "James":
            up, down = down, up

        h = {'date': self.tx.date,
             'payee': payee,
             'narration': narration,
             'comment': comment,
             'e_karl': down * -1,
             'e_james': up * -1,
             'a_karl': down,
             'a_james': up}
        b = """{date} txn "{payee}" "{narration}"
  comment: "{comment}"
  Expenses:Karl              {e_karl} USD
  Expenses:James             {e_james} USD
  Assets:Checking:Karl       {a_karl} USD
  Assets:Checking:James      {a_james} USD

""".format(**h)

        ret = "\n".join([l for l in b.split("\n") if " 0 USD" not in l])
        ret = ret.replace(' ', r'&nbsp;').replace("\n", "<br />\n")
        return ret.strip()

    def dump(self):
        entry = self.tx
        ret = ""
        for d in dir(entry):
            if d.startswith('_'):
                continue
            if "__call__" in dir(entry.__getattribute__(d)):
                continue
            ret += "%s: %s\n" % (d, entry.__getattribute__(d))
        print(ret)
        return ret
        return("{0.date}".format(entry))

    def get_postings(self, accounts):
        "Return a list of postings that match any of the account names in list ACCOUNTS"

        ret = []
        for p in self.tx.postings:
            for a in accounts:
                if p.account.startswith(a):
                    ret.append(p)
        return ret

    def hits_account(self, account_name):
        """ACCOUNT_NAME is a string with a (partial) account name

        Returns True iff ACCOUNT_NAME appears at the start of at least
        one of the posting accounts.

        """
        if [p for p in self.tx.postings if p.account.startswith(account_name)]:
            return True
        return False

    def hits_accounts(self, account_names):
        """ACCOUNT_NAMES is a list of strings with (partial) account names

        Returns True iff a name in ACCOUNT_NAMES appears at the start
        of at least one of the posting accounts.

        """
        for name in account_names:
            if self.hits_account(name):
                return True
        return False

    def html(self):
        # Grab all the metadata fields except the ones whose keys
        # start with underscore and handle linebreaks
        meta = [{'item': "%s: %s" % (k, str(self.tx.meta[k]).replace(
            "\n", "<br>"))} for k in self.tx.meta if not k.startswith('_')]

        # Render and return
        return mustache.render(
            settings['templates'],
            "beancount_tx",
            {
                'amount': self["amount"].amount,
                'meta': meta,
                'narration': self.tx.narration,
                'payee': self.tx.payee,
                'payment_direction': "to" if self["amount"].amount < 0 else "from"})

    def calc_amount(self, accounts):
        """Set self['amount'] to the calculated amount in the postings we care
        about."""
        self['amount'] = 0
        for account in accounts:
            self['amount'] += Money(sum(
                [p.units.number for p in self.tx.postings if p.account.startswith(account)]), currency="USD")


def get_register(account):
    """Returns a Register class for beancount.

    ACCOUNT is a dict with at least a 'ledger_file' field.

    """

    reg = Register(account)
    if len(reg) == 0:
        u.err("Register is empty of journal entries.")
    return reg


class Register(register.Register):
    """Model a beancount register as a series of Transactions"""

    def __init__(self, account):
        register.Register.__init__(self, account)

        # Use beancount's loader to load our entries
        entries, self.errors, self.options = loader.load_file(
            account['ledger_file'])

        # Entries come sorted from the beancount loader, so let's
        # just save them and be happy.
        self.extend(entries)

    def get_accounts(self):
        return [e for e in self if isinstance(e, beancount.core.data.Open)]

    def get_txs(self, date=None):
        if not date:
            return [
                Transaction(e) for e in self if isinstance(
                    e, beancount.core.data.Transaction)]

        if isinstance(date, type("")):
            date = dateparse.parse(date).date()

        return [e for e in self.get_txs() if e.tx.date == date]

    def load_reg_text(self, start=None, end=None):
        """Return a string with ledger register entries for the account in
        self.account.  Get the register from beancount and return it

        START is an optional start date, it will include from that day forward.

        END is an optional end date, it will exclude from that day forward.

        START and END aren't implemented yet.

        """

        if start or end:
            raise UnimplementedError("Start and End not implemented yet")

        lines = []
        for account in self.accounts:
            query = "SELECT id, date, account, position, balance WHERE account~'%s'" % (
                account)
            query = u.bean_query(self.fname, query).split("\n")[2:]
            if not lines:
                lines = query
            else:
                lines.extend(query[2:])

        # Remove cruft
        # lines = [l for l in lines
        #         if l
        #         and not '----------' in l
        #         and not l.strip().startswith('date')]

        ret = "\n".join(lines)
        return ret

    def load_txs(self):
        """Load transactions into the register."""
        query = "SELECT id, date, account, payee, position, balance WHERE account~'%s'" % (
            self.account)
        csv = u.bean_query_csv(self.fname, query)
        reg = etl.fromcsv(OpenableIOString(csv))

        # Save the rows because we can't reopen our byte stream
        rows = []
        for row in reg:
            rows.append(row)

        headers = rows[0]
        row_dicts = []
        for row in rows[1:]:
            row_dict = {}
            for i in range(len(headers)):
                row_dict[headers[i]] = row[i].strip()
            row_dict['date'] = dateparse.parse(row_dict['date'])
            a, c = re.split(' +', row_dict['position'])
            row_dict['amount'] = Money(a, c)
            self.append(transaction.Transaction(row_dict))

    def parse_line(self, line):
        """Parse the date and amount out of the register LINE.

        Returns a dict with date and amount keys."""

        parts = [t for t in line.split(' ') if t]
        if len(parts) != 6:
            print(line)
            print(parts)
        return {}
        sys.exit()
        return {
            'id': parts[0],
            'date': dateparse.parse(parts[1]),
            'account': parts[2],
            'amount': parts[3],
            'total': parts[4]}
