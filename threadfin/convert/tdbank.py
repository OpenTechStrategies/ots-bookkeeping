#!/usr/bin/env python

import datetime
import re
import sys

# Our code
import statement
import transaction
# from beancount.core.data import Transaction as BCTX
import util as u
from dateutil import parser as dateparse
from util import parse_money

rx = {}
rx["blanks"] = re.compile(" +")
rx["two_blanks"] = re.compile("  +")
rx["date"] = re.compile("[0-9][0-9]/[0-9][0-9]")
rx["ccnum"] = re.compile(r"\*+\d+")


class UnimplementedError(Exception):
    pass


class Transaction(transaction.Transaction):
    def as_beancount(self):

        self.vals["date"] = self["date"].strftime("%Y-%m-%d")

        for field in "cardholder code comment payee narration".split(" "):
            self.vals[field] = ""
        self.vals["account"] = CUSTOM["accounts"]["debit"]
        self.vals["account2"] = CUSTOM["accounts"]["credit"]
        self.vals["amount"] = self["amount"].amount
        self.vals["category"] = self["category"]
        self.vals["comment"] = self.get("note", "")
        self.vals["currency"] = self["amount"].currency
        self.vals["narration"] = ""

        if "cardholder" in self:
            self.vals["cardholder"] = self["cardholder"]

        if "comment" in CUSTOM:
            self.vals = self.custom_match_comment(CUSTOM["comment"], self.vals)

        if self.vals["payee"] == "" and self.vals["narration"] == "":
            self.vals["narration"] = self.get("note", "")

        if self["category"] not in [
            "Checks Paid",
            "Deposits",
            "Electronic Deposits",
            "Electronic Payments",
            "Other Credits",
            "Other Withdrawals",
        ]:
            raise UnimplementedError(
                "Can't handle %s in tx dated %s" % (self["category"], self["date"])
            )

        return self.interpolate(self.vals)


class Block(statement.Block):
    """A block of text in a statement that encompasses one type of
    information.  Meant to be subclasses for each type of block.

    The dict's keys map to info pulled from the statement.
    """

    def get_block(self, name=None):
        """Find the block of postings for NAME in self.text, with extraneous
        lines omitted.  This works for blocks that end in subtotal but
        might be interrupted by other text.

        """

        if not name:
            name = self.name

        regex_start = self.regex if self.regex else "^%s[^\n]*?\n" % name
        reg = re.compile(regex_start + "POSTING.*?\n\n", re.DOTALL | re.MULTILINE)
        collect = []
        found_subtotal = False
        for segment in reg.findall(self.text):
            for line in segment.split("\n"):
                collect.append(line)
                if "   Subtotal: " in line:
                    found_subtotal = True
                    break
        ret = "\n".join(collect)

        ## We now have all the postings, but maybe we don't have a
        ## subtotal with it because sometimes the subtotal is
        ## separated from postings by blank lines.  If that's the
        ## case, grab the regex again, but this time make sure we go
        ## all the way to the subtotal.  Extract that, and add it to
        ## our return string.
        if not found_subtotal:
            reg = re.compile(
                regex_start + "POSTING.*?(\n +Subtotal: +[0-9,.]+)",
                re.DOTALL | re.MULTILINE,
            )
            m = reg.search(self.text)
            if not m:
                print(ret)
                self.err("Couldn't find subtotal for %s section" % name)
            ret += m.group(1)

        return ret

        segments = "\n".join(
            ["\n".join(s.strip().split("\n")[2:]) for s in reg.findall(self.text)]
        )

        ## Make sure we can find subtotal, even if it is separated
        ## from register by blank lines.
        reg = re.compile(
            "^%s[^\n]*?\nPOSTING.*?(\n +Subtotal: +[0-9,.]+)" % name,
            re.DOTALL | re.MULTILINE,
        )
        m = reg.search(self.text)
        if not m:
            self.err("Couldn't find subtotal for %s section" % name)
        segments += m.group(1)
        return segments


class SubtotalBlock(Block):
    def __init__(self, statement, name):
        self.subtotal = parse_money(0)
        Block.__init__(self, statement, name)

    def parse_subtotal(self):
        for line in self.text.split("\n"):
            if "Subtotal" in line:
                parts = rx["blanks"].split(line)
                self.subtotal = parse_money(parts[-1])
                return

    def parse(self):
        if self.name in self.statement.blocks["Account Summary"]["credits"]:
            self.parse_credit_block()
        elif self.name in self.statement.blocks["Account Summary"]["debits"]:
            self.parse_debit_block()

    def parse_debit_block(self):
        self.parse_subtotal()
        lines = self.text.split("\n")
        for i in range(2, len(lines)):
            line = lines[i]
            if rx["date"].match(line):
                parts = rx["two_blanks"].split(line)
                tx = Transaction()
                tx["category"] = self.name
                tx["date"] = self.parse_date(parts[0])
                tx["amount"] = parse_money(parts[2]) * -1
                tx["note"] = parts[1]

                # If posting spans two lines, grab the second line for
                # our note.
                if i + 1 <= len(lines) and not rx["date"].match(lines[i + 1]):
                    tx["note"] = (
                        " ".join(rx["blanks"].split(lines[i + 1].strip()))
                        + " "
                        + tx["note"]
                    )

                self.statement.append(tx)
            elif (
                line.startswith(" ")
                or line.startswith("POSTING DATE  ")
                or line == "%s (continued)" % self.name
                or not line
            ):
                continue
            else:
                self.err("Can't parse this %s line:\n%s" % (self.name, line))

    def parse_credit_block(self):
        self.parse_subtotal()
        lines = self.text.split("\n")[2:] if self.text else []
        for i in range(0, len(lines)):
            line = lines[i]
            if rx["date"].match(line):
                parts = rx["two_blanks"].split(line)
                if len(parts) != 3:
                    self.err("Can't parse this %s line:\n%s" % (self.name, line))
                tx = Transaction()
                tx["category"] = self.name
                tx["date"] = self.parse_date(parts[0])
                tx["amount"] = parse_money(parts[2])
                tx["note"] = parts[1]

                # If posting spans two lines, grab the second line for
                # our note.
                if i + 1 <= len(lines) and not rx["date"].match(lines[i + 1]):
                    tx["note"] = (
                        " ".join(rx["blanks"].split(lines[i + 1].strip()))
                        + " "
                        + tx["note"]
                    )

                self.statement.append(tx)

    def validate(self):

        # Subtotal printed in Account Summary
        try:
            account_summary = self.statement.blocks["Account Summary"]["credits"][
                self.name
            ]
        except KeyError:
            account_summary = self.statement.blocks["Account Summary"]["debits"][
                self.name
            ]

        # Calculated total of postings in statement block
        total = self.statement.sum(self.name)

        # Subtotal printed in statement block
        subtotal = self.subtotal
        if not (account_summary == abs(subtotal) == abs(total)):
            self.err(
                "Subtotals for %s don't add up.\n" % self.name
                + "Subtotal printed in Account Summary: %s\n" % account_summary
                + "Subtotal printed in %s block of the statement: %s\n"
                % (self.name, subtotal)
                + "Subtotal calculated from postings in %s block of the statement: %s\n"
                % (self.name, total)
            )


class AccountSummary(Block):
    def __init__(self, statement):
        name = "Account Summary"
        self.regex = re.compile("ACCOUNT SUMMARY.*?\n\n", re.DOTALL | re.MULTILINE)
        Block.__init__(self, statement, name)

    def get_debit_credit_names(self):
        """Return list of block names that should have debit/credit postings."""
        return [
            c
            for c in self.blocks["Account Summary"]["credits"]
            if c != "Beginning Balance"
        ] + [
            c for c in self.blocks["Account Summary"]["debits"] if c != "Ending Balance"
        ]

    def dump(self):
        for k, v in self["credits"].items():
            print("%s = %s" % (k, v))
        for k, v in self["debits"].items():
            print("%s = %s" % (k, v))
        for k in [s for s in self if s not in ["debits", "credits"]]:
            print("%s = %s" % (k, self[k]))

    def get_block(self):
        return self.re_search()

    def parse(self):
        """The account summary is in two halves.  The left side are subtotals
        of debits and credits.  The right side is other data.  Get it
        all.  Not every line has entries in both columns.  Every
        statement should have an account summary.

        """

        # Keep track of the names of account debit and credit fields
        self["credits"] = {}
        self["debits"] = {}

        c_or_d = "credits"
        for line in self.text.split("\n")[1:]:
            parts = rx["two_blanks"].split(line)
            if len(parts) == 2 or len(parts) == 4:
                self[c_or_d][parts[0]] = parse_money(parts[1])
            if len(parts) == 3 or len(parts) == 4:
                if "%" in parts[-1]:
                    self[parts[-2]] = parts[-1]
                else:
                    self[parts[-2]] = parse_money(parts[-1])
            if len(parts) == 3:
                c_or_d = "debits"

    def validate(self):
        credits = sum([self["credits"][c] for c in self["credits"]])
        debits = sum(
            [self["debits"][c] for c in self["debits"] if c != "Ending Balance"]
        )
        if credits - debits != self["debits"]["Ending Balance"]:
            u.err("Account Summary credits and debits don't total to ending balance.")


class DailyBalance(Block):
    def __init__(self, statement, name):
        self.regex = re.compile(
            "^DAILY BALANCE SUMMARY\n.*?\n\n", re.DOTALL | re.MULTILINE
        )
        Block.__init__(self, statement, name)

    def get_block(self):
        block = "\n".join(
            [
                "\n".join(block.strip().split("\n")[2:])
                for block in self.regex.findall(self.text)
            ]
        )
        return block

    def parse(self):
        for line in self.text.split("\n"):
            if not line or not rx["date"].match(line):
                continue

            parts = rx["blanks"].split(line)
            if len(parts) == 2:
                self[self.parse_date(parts[0])] = parse_money(parts[1])
            elif len(parts) == 4:
                self[self.parse_date(parts[0])] = parse_money(parts[1])
                self[self.parse_date(parts[2])] = parse_money(parts[3])
            else:
                self.err("Parse error: can't parse daily balances in line\n%s" % (line))

    def validate(self):
        last_daily_bal = self[sorted(self.keys())[-1]]
        end_bal = self.statement.blocks["Account Summary"]["debits"]["Ending Balance"]
        if not last_daily_bal == end_bal:
            self.err(
                "Last daily balance (%s) != Account Summary ending balance (%s)"
                % (last_daily_bal, end_bal)
            )

        calc_daily_bal = {}
        for tx in self.statement:
            if tx["date"] in calc_daily_bal:
                calc_daily_bal[tx["date"]] += tx["amount"]
            else:
                calc_daily_bal[tx["date"]] = tx["amount"]

        # Put transactions in date order
        self.statement.sort(key=lambda x: x["date"])

        running = self.statement.blocks["Account Summary"]["credits"][
            "Beginning Balance"
        ]
        for tx in self.statement:
            running += tx["amount"]
            if tx["date"] in self:
                # TODO: check daily balance
                pass
                # print(tx)
                # print(self[tx['date']])


class ChecksPaid(SubtotalBlock):
    def __init__(self, *args, **kwargs):
        self.regex = "^Checks Paid +No. Checks.*?\n"  #: [0-9,.]+[^\n]+\n"
        SubtotalBlock.__init__(self, *args, **kwargs)

    def parse(self):
        self.parse_subtotal()
        for line in self.text.split("\n")[2:]:
            if not line or not rx["date"].match(line):
                continue
            parts = rx["blanks"].split(line)
            if not len(parts) in (3, 6):
                self.err("Can't parse %s line:\n%s" % (self.name, line))
            for i in range(0, len(parts), 3):
                tx = Transaction()
                tx["category"] = self.name
                tx["date"] = self.parse_date(parts[i])
                tx["code"] = int(parts[i + 1])
                tx["amount"] = parse_money(parts[i + 2]) * -1
                self.statement.append(tx)


class Deposits(SubtotalBlock):
    pass


class ElectronicDeposits(SubtotalBlock):
    pass


class ElectronicPayments(SubtotalBlock):
    pass


class OtherCredits(SubtotalBlock):
    pass


class OtherWithdrawals(SubtotalBlock):
    pass


class Statement(statement.Statement):
    """TD Bank Statement Parser"""

    def __init__(self, pdfname, custom):

        """PDFNAME is the filename of the pdf

        CUSTOM is the yaml loaded from a custom data file.  It has a
        key called "comment" that leads to a dict, whose keys are
        regex patterns or dumb string (if they're just [A-Z ]).
        Payload is a dict with some combination of payee, narration,
        and tags.  If the key matches the comment, we set tx fields as
        per the payload.

        CUSTOM also has a key called "cardholders" that has a dict
        with keys matching people names that hash to lists of last
        four digits of credit cards.  We use this to match cc
        transactions to people.

        """
        statement.Statement.__init__(self, pdfname, custom)
        key = "Bank Deposits FDIC Insured | TD Bank, N.A. | Equal Housing Lender"
        if not key in self.text:
            self.bank = ""
            return
        self.bank = "TDBank"

        # Make custom available to transactions without passing it all
        # the way through.
        global CUSTOM
        CUSTOM = custom

        self.beanfile_preamble = ";; -*- mode: org; mode: beancount; -*-\n"

    def parse(self):
        self.blocks = {}
        self.blocks["Account Summary"] = AccountSummary(self)
        self.blocks["Account Summary"].parse()

        ## For each debit/credit section listed in the account
        ## summary, get the corresponding section from the statement
        ## and parse it for transactions.
        blocks_needed = [
            c
            for c in self.blocks["Account Summary"]["credits"]
            if c != "Beginning Balance"
        ] + [
            c for c in self.blocks["Account Summary"]["debits"] if c != "Ending Balance"
        ]
        for block in blocks_needed:
            cmd = 'self.blocks["%s"] = %s(self, "%s")' % (
                block,
                block.replace(" ", ""),
                block,
            )
            exec(cmd)
            self.blocks[block].parse()

        # Get the daily balances printed in the statement and compare
        # them to the daily totals we calculate from the postings.
        self.blocks["Daily Balance"] = DailyBalance(self, "Daily Balance")
        self.blocks["Daily Balance"].parse()

    def sanity_check(self, *args, **kwargs):
        """Override the original sanity check, which is pretty specific to
        Chase."""
        for block in self.blocks:
            self.blocks[block].validate()
