#!/usr/bin/env python3
"""
Generic statement base class
"""

from transaction import Transactions
import util as u
from util import parse_money
import sys
import subprocess
import datetime
import os
import pprint
pp = pprint.PrettyPrinter(indent=4).pprint

# our code


class UnimplementedError(Exception):
    pass


class Block(dict):
    """A block of text in a statement that encompasses one type of
    information.  Meant to be subclasses for each type of block.

    The dict's keys map to info pulled from the statement.
    """

    def __init__(self, statement, name):
        """STATEMENT is the statement object.

        NAME is the name of this section of the statement"""
        self.statement = statement
        self.name = name
        self.text = statement.text
        self.regex = getattr(self, "regex", "")
        self.text = self.get_block()
        dict.__init__(self)

    def dump(self):
        for k, v in self.items():
            print("%s -=> %s" % (k, v))

    def err(self, msg):
        """Add pdf name to error"""
        u.err("In %s: %s" % (self.statement.pdfname, msg))

    def get_block(self):
        return self.re_search()

    def parse_date(self, datestring):
        """Date is a parsable string and we need to return a date object using
        the datestring and the year from the statement pdf.  If we're
        in a December PDF and we see a January date, it's the next
        year.  If we're in January and we see a December date, it's the previous year.

        """
        d = u.parse_date(datestring)
        if self.statement.month == 12 and d.month == 1:
            return u.parse_date("%s-%s" %
                                (self.statement.year + 1, d.strftime("%m-%d")))
        if self.statement.month == 1 and d.month == 12:
            return u.parse_date("%s-%s" %
                                (self.statement.year - 1, d.strftime("%m-%d")))
        return u.parse_date(
            "%s-%s" %
            (self.statement.year, d.strftime("%m-%d")))

    def re_search(self, string=None, regex=None, entire_match=False):
        """Run the regex search against the string, look for the first group,
        and return it else None.  If no parens mark off a group,
        return the whole match if found.

        STRING defaults to self.text

        REGEX is the compiled regex to search for, defaults to self.regex

        If ENTIRE_MATCH is set, return the whole match, even if there are subgroups in the regex.

        """
        if not regex:
            regex = self.regex

        m = regex.search(string if string else self.text)
        if not m:
            return None
        if entire_match:
            return m.group(0).strip()
        try:
            return m.group(1).strip()
        except IndexError:
            return m.group(0).strip()

    def parse(self, *args):
        self.err(
            "Generic parse method should be overridden for %s." %
            self.name)

    def validate(self, *args):
        self.err(
            "Generic validation method should be overridden for %s." %
            self.name)


class Statement(Transactions):
    """A Statement is a set of transactions with additional info/methods
    related to the bank statement.

    TODO: actually use the Transactions class instead of self['transactions']

    """

    def __init__(self, fname, custom):
        """FNAME is the filename of the pdf or csv

        CUSTOM is a data structure that lets us customize the data
        import.  For example, it could let us identify the people
        associated with credit card numbers.  Each bank's parser can
        use it differently.

        This init sets some defaults.

        When inheriting:

         * call the parent (this func) to get this setup done

         * check that the statement matches the bank type you're
        implementing.  If it doesn't, set self.bank to "" and return.

         * set self.bank to the bank name

        """

        self.pdfname_full = fname
        self.pdfname = os.path.split(fname)[1]
        self.custom = custom
        self.beancount_fname = os.path.splitext(fname)[0] + ".beancount"
        self.set_year_month()

        # Init some vars
        self.daily_bal = {}
        self.transactions = []
        self.paid_checks_total = 0
        self.deposits = 0

        if fname.endswith("pdf"):
            self.text = u.pdf2txt(fname)
        else:
            self.text = u.slurp(fname, decode=None)

    def set_year_month(self):
        """We set the year and month based on the statement filename, but if
        your statements don't come with those kinds of filenames,
        override this function

        """
        try:
            stub = os.path.splitext(os.path.basename(self.pdfname))[0]
            self.year = int(stub.split("_")[0])
            self.month = int(stub.split("_")[1])
        except BaseException:
            self.year = "0"
            self.month = "0"

    def as_beancount(self):
        ret = ''
        txn = self if self else self.transactions
        for tx in sorted(txn, key=lambda tx: tx['date']):
            ret += tx.as_beancount()
        return ret

    def balance_assertions(self, account=None):
        ret = ""

        if not account:
            account = self.custom['accounts']['debit']

        for date in sorted(self.daily_bal.keys()):
            ret += ("%s balance %s        %s %s\n" % (date + datetime.timedelta(1),
                                                      account,
                                                      self.daily_bal[date].amount,
                                                      self.daily_bal[date].currency))
        return ret

    def open_accounts(self):
        # Wrangle open accounts
        accounts = []
        ca = self.custom['accounts']
        debit = ca['debit']
        credit = ca['credit']
        if debit != "Expenses":
            accounts.append(debit)
        if credit != "Expenses":
            accounts.append(credit)
        accounts.extend(ca.get('other', []))
        return "\n".join(["2010-01-01 open %s" % o for o in accounts]) + "\n"

    def parse(self):
        """
        Extract some stuff from a statement pdf:

        begin_bal = beginning balance
        end_bal = ending balance
        paid_checks_total = total checks paid that month
        """
        raise UnimplementedError("Must implement parse function!")

    def sanity_check(self):
        """Make sure things add up.  Check that the sum of transactions adds
        up to the difference between start and end balance, etc.

        """
        raise UnimplementedError("Must implement sanity_check function!")

    def sum(self, category=None):
        """Sum all the transactions or just those in a category.  Returns an
        Money type."""
        if category:
            s = sum([e['amount'] for e in self if e['category'] == category])
        else:
            s = sum([e['amount'] for e in self])
        if isinstance(s, type(0)):
            # This only happens if it's zero, but we have to deal with it.
            s = parse_money(s)
        return s

    def write_beancount(self):
        bc = self.as_beancount()
        with open(self.beancount_fname, 'w') as fh:
            fh.write(self.beanfile_preamble)
            fh.write(self.open_accounts())
            fh.write(bc)
        # if u.run_command("bean-check %s" % self.beancount_fname):
            # u.err("bean-check has errors for %s" % self.beancount_fname)
        return bc
