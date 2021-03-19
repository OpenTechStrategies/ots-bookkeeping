#!/usr/bin/env python

import datetime
import re
import sys

from dateutil import parser as dateparse

# Our code
import statement
import transaction
# from beancount.core.data import Transaction as BCTX
import util as u
from statement import Block
from util import parse_money

rx = {}
rx["blanks"] = re.compile(" +")
rx["two_blanks"] = re.compile("  +")
rx["date"] = re.compile(r"\d\d/\d\d")
rx["ccnum"] = re.compile(r"\*+\d+")
rx["tx_entry"] = re.compile(r" ?[A-Z][a-z][a-z] \d\d?[^$]+\$[\d,]+\.\d\d")


class UnimplementedError(Exception):
    pass


class Transaction(transaction.Transaction):
    def as_beancount(self):

        self.vals["date"] = self["date"].strftime("%Y-%m-%d")

        for field in "cardholder code comment payee narration".split(" "):
            self.vals[field] = ""
        self.vals["account"] = "Expenses:CapitalOne"
        self.vals["account2"] = "Liabilities:CapitalOne"
        self.vals["amount"] = self["amount"].amount
        self.vals["category"] = self["category"]
        self.vals["comment"] = self.get("note", "")
        self.vals["currency"] = self["amount"].currency
        self.vals["narration"] = self.get("narration", "")

        if "comment" in CUSTOM:
            self.vals = self.custom_match_comment(CUSTOM["comment"], self.vals)

        if self.vals["payee"] == "" and self.vals["narration"] == "":
            self.vals["narration"] = self.get("note", "")

        if not self["category"] in ["Transactions", "Fees", "Credits"]:
            raise UnimplementedError(
                "Can't handle %s in tx dated %s" % (self["category"], self["date"])
            )

        return self.interpolate(self.vals)


class AccountSummary(Block):
    def __init__(self, statement):
        name = "Account Summary"
        self.regex = re.compile(
            "^ +Payment Information +Account Summary\n.*?Available Credit for Cash.*?\n\n",
            re.DOTALL | re.MULTILINE,
        )
        Block.__init__(self, statement, name)

    def parse(self):
        """The account summary is in two halves.  The left side is payment
        info and the right is account summary. Get it all.  Not every
        line has entries in both columns.  Every statement should have
        an account summary.

        """

        if not self.text:
            self.err("No lines to parse for block %s" % self.name)

        lines = self.text.split("\n")
        for i in range(len(lines)):
            line = lines[i]
            parts = rx["two_blanks"].split(line.strip())
            if len(parts) >= 2:
                for k in [
                    "Available Credit",
                    "Cash Advances",
                    "Credit Limit",
                    "Fees Charged",
                    "Interest Charged",
                    "New Balance",
                    "Other Credits",
                    "Previous Balance",
                    "Payments",
                    "Transactions",
                ]:
                    if parts[-2].startswith(k):
                        if parts[-1][0] in "-+=":
                            parts[-1] = parts[-1][1:].strip()
                        if parts[-1][0] == "$":
                            parts[-1] = u.parse_money(parts[-1])
                        self[k] = parts[-1]

            if parts[0] == "Payment Due Date":
                self["Payment Due Date"] = u.parse_date(
                    rx["two_blanks"].split(lines[i + 2].strip())[0]
                )

            if parts[0] == "New Balance" and parts[1] == "Minimum Payment Due":
                parts_next = rx["two_blanks"].split(lines[i + 1].strip())
                self["New Balance Left"] = u.parse_money(parts_next[0])
                self["Minimum Payment Due"] = u.parse_money(parts_next[1])

    def validate(self):
        # Validate account summary's new balance
        if self["New Balance Left"] != self["New Balance"]:
            u.err(
                "Left New Balance entry doesn't match the right: %s != %s"
                % (self["New Balance Left"], self["New Balance"])
            )

        # Validate account summary
        tot = sum(
            [
                self[s]
                for s in [
                    "Previous Balance",
                    "Transactions",
                    "Cash Advances",
                    "Fees Charged",
                    "Interest Charged",
                ]
            ]
        )
        tot = tot - self["Payments"] - self["Other Credits"]
        if tot != self["New Balance"]:
            self.err(
                "Account Summary total doesn't add up to new balance: %s != %s"
                % (tot, self["New Balance"])
            )


class TransactionsBlock(Block):
    def __init__(self, statement):
        name = "Transactions"
        self.regex = re.compile(
            "^       +Transactions.*?    Interest Charge Calculation.*",
            re.DOTALL | re.MULTILINE,
        )
        Block.__init__(self, statement, name)

    def parse(self):
        "The transaction log is in two columns.  Get it all."

        if not self.text:
            self.err("No lines to parse for block %s" % self.name)

        lines = self.text.split("\n")

        # Get left column width
        left_col_width = 0
        for i in range(len(lines)):
            line = lines[i]
            if not line:
                continue
            m = rx["tx_entry"].match(line)
            if m:
                left_col_width = max(left_col_width, len(m.group()))
        if left_col_width == 0:
            self.err("Can't find left column width while parsing %s" % self.name)

        for i in range(len(lines)):
            line = lines[i]
            if not line:
                continue
            for entry in rx["tx_entry"].findall(line):
                parts = rx["two_blanks"].split(entry.strip())

                parts[0] = self.parse_date(parts[0])

                # Combine middle parts if there's more than one
                if len(parts) > 3:
                    parts = [parts[0], " ".join(parts[1:-1]), parts[-1]]

                # Handle credits
                if parts[-1].startswith("-"):
                    parts[-1] = u.parse_money(parts[-1][1:]) * -1
                else:
                    parts[-1] = u.parse_money(parts[-1])

                # Get next line if there's text there
                half = (
                    lines[i + 1][:72] if line.index(entry) < 40 else lines[i + 1][72:]
                )
                if half.strip():
                    if (
                        not half[:3]
                        in "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dev"
                    ):
                        parts[1] += " " + half.strip()

                category = self.name if parts[2].amount >= 0 else "Credits"
                if parts[1] == "PAST DUE FEE":
                    category = "Fees"
                # Make tx
                tx = Transaction()
                tx["category"] = category
                tx["date"] = parts[0]
                tx["amount"] = parts[2]
                tx["note"] = parts[1]
                self.statement.append(tx)

    def validate(self):
        a = self.statement.sum("Transactions")
        b = self.statement.blocks["Account Summary"]["Transactions"]
        if a != b:
            self.err(
                "Account summary transactions != sum of transactions: %s - %s = %s"
                % (b, a, b - a)
            )


class Statement(statement.Statement):
    """Capital One Platinum Mastercard Monthly Statement Parser"""

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
        key = "Platinum MasterCard Account"
        if key not in self.text:
            self.bank = ""
            return
        self.bank = "Capital One Platinum Mastercard"

        # Make custom available to transactions without passing it all
        # the way through.
        global CUSTOM
        CUSTOM = custom

        self.beanfile_preamble = ";; -*- mode: org; mode: beancount; -*-\n"

    def parse(self):
        self.blocks = {}
        self.blocks["Account Summary"] = AccountSummary(self)
        self.blocks["Account Summary"].parse()
        self.blocks["Transactions"] = TransactionsBlock(self)
        self.blocks["Transactions"].parse()

    def sanity_check(self, *args, **kwargs):
        for block in self.blocks:
            self.blocks[block].validate()
