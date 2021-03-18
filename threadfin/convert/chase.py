#!/usr/bin/env python

import datetime
import re
import sys

# Our code
import statement
import transaction
import util as u
from dateutil import parser as dateparse
from util import parse_money

rx = {}
rx["date"] = re.compile("[0-9][0-9]/[0-9][0-9]")
rx["checknum"] = re.compile(r"(\d\d*)\s+([* ^]*) *(\S*) *(\d\d/\d\d) *(\S*)")


class Transaction(transaction.Transaction):
    def as_beancount(self):
        self.vals["date"] = self["date"].strftime("%Y-%m-%d")
        self.vals["unfiled"] = ":Unfiled"
        self.vals["comment"] = self.get("note", "")
        self.vals["amount"] = self["amount"].amount
        self.vals["currency"] = self["amount"].currency
        self.vals["account"] = CUSTOM["accounts"]["debit"] + ":James:Karl"
        self.vals["account2"] = CUSTOM["accounts"]["credit"] + ":James:Karl"

        tx = self
        h = self.vals

        if tx["category"] == "FEES":
            h["payee"] = "Chase Bank"
            h["narration"] = "Bank Fees"
        elif tx["category"] == "CHECK":
            h["narration"] = "Check Paid"
            # h['code'] = '   code: %s\n' % tx['number']
            h["code"] = tx["number"]
        elif tx["category"] == "DEPOSIT":
            h["narration"] = "Deposit"
            h["account2"] = "Income:James:Karl"
        elif tx["category"] == "ATM/DEBIT":
            h["narration"] = "ATM/Debit Card"
            for holder in CUSTOM["cardholders"]:
                if tx["note"][-4:] in CUSTOM["cardholders"][holder]:
                    # Assume card holder owns the expense, but override below
                    # if needed.
                    split = holder
                    h["cardholder"] = holder
            if not h["cardholder"] or not split:
                u.err("Unknown cardholder: %s" % tx)

            h = self.custom_match_comment(CUSTOM["comment"], h)
            if "split" in h:
                split = h["split"]

            h["account"] = "%s:%s" % (CUSTOM["accounts"]["debit"], split)
            h["account2"] = "%s:%s" % (CUSTOM["accounts"]["credit"], split)
        elif tx["category"] == "E-WITHDRAW":
            h["narration"] = "E-Withdraw"
        elif tx["category"] == "OTHER-WITHDRAW":
            h["narration"] = "Other-Withdraw"
        else:
            raise UnimplementedError("Can't handle %s" % tx["category"])

        return self.interpolate(h)


class Statement(statement.Statement):
    def __init__(self, pdfname, custom):
        """PDFNAME is the filename of the pdf"""
        statement.Statement.__init__(self, pdfname, custom)
        if not ("JPMorgan Chase Bank, N.A." in self.text and "Chase.com" in self.text):
            self.bank = ""
            return
        self.bank = "Chase"

        # Make custom available to transactions without passing it all
        # the way through.
        global CUSTOM
        CUSTOM = custom

        self.beanfile_preamble = (
            ";; -*- mode: org; mode: beancount; -*-\n"
            + 'plugin "plugins.share_postings" "James Karl"\n\n'
        )

    def parse(self):
        txt = self.text
        mode = "start"
        lines = txt.split("\n")
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            if line.startswith("CHECKING SUMMARY") or mode == "CHECKING SUMMARY":
                mode = "CHECKING SUMMARY"
                if line.startswith("Beginning Balance"):
                    self.begin_bal = parse_money(line.split(" ")[-1])
                if line.startswith("Deposits and Additions"):
                    self.deposits = parse_money(line.split(" ")[-1])
                if line.startswith("Checks Paid"):
                    parts = line.split()
                    if parts[-2] == "-":
                        parts[-1] = "-" + parts[-1]
                    self.paid_checks_total = parse_money(parts[-1])
                if line.startswith("ATM & Debit Card Withdrawals"):
                    parts = line.split()
                    if parts[-2] == "-":
                        parts[-1] = "-" + parts[-1]
                    self.card_withdrawals = parse_money(parts[-1])
                if line.startswith("Electronic Withdrawals"):
                    parts = line.split()
                    if parts[-2] == "-":
                        parts[-1] = "-" + parts[-1]
                    self.electronic_withdrawals = parse_money(parts[-1])
                if line.startswith("Other Withdrawals"):
                    parts = line.split()
                    if parts[-2] == "-":
                        parts[-1] = "-" + parts[-1]
                    self.other_withdrawals = parse_money(parts[-1])
                if line.startswith("Fees"):
                    parts = line.split()
                    if parts[-2] == "-":
                        parts[-1] = "-" + parts[-1]
                    self.fees = parse_money(parts[-1])
                if line.startswith("Ending Balance"):
                    self.end_bal = parse_money(line.split()[-1])
            if (
                line.startswith("DEPOSITS AND ADDITIONS")
                or mode == "DEPOSITS AND ADDITIONS"
            ):
                mode = "DEPOSITS AND ADDITIONS"
                if line[2] == "/" and line[-1] in "0123456789":  # It's a transaction
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t["category"] = "DEPOSIT"
                    t["date"] = parts[0]
                    t["amount"] = parse_money(parts[-1])
                    if len(parts) == 4:
                        t["type"] = parts[1]
                        t["note"] = parts[2]
                        if t["note"][2] == "/" and t["date"] != t["note"][:5]:
                            t["date2"] = t["note"][:5]
                    elif len(parts) == 3:
                        t["type"] = parts[1]
                    self.transactions.append(t)
            if line.startswith("CHECKS PAID") or mode == "CHECKS PAID":
                mode = "CHECKS PAID"
                m = rx["checknum"].match(line)
                if m:
                    t = Transaction()
                    t["category"] = "CHECK"
                    t["number"] = int(m.groups()[0])
                    t["symbols"] = m.groups()[1].strip()
                    t["note"] = m.groups()[2].strip()
                    t["date"] = m.groups()[3]
                    t["amount"] = parse_money(m.groups()[4]) * -1
                    # print self.year, t
                    self.transactions.append(t)

            if (
                line.startswith("ATM & DEBIT CARD WITHDRAWALS")
                or mode == "ATM & DEBIT CARD WITHDRAWALS"
            ):
                mode = "ATM & DEBIT CARD WITHDRAWALS"
                if line[2] == "/":
                    parts = [l.strip() for l in line.split("  ") if l]

                    # Catch an odd pdftotext corner case, where we
                    # get just the date, with the rest of the data
                    # pushed down a couple rows
                    if (
                        len(parts) == 1
                        and parts[0][2] == "/"
                        and "*end*atm debit withdrawal" in lines[i + 1]
                    ):
                        line = line + lines[i + 2]
                        lines[i + 2] = ""
                        parts = [l.strip() for l in line.split("  ") if l]

                    t = Transaction()
                    t["category"] = "ATM/DEBIT"
                    t["date"] = parts[0]
                    t["amount"] = parse_money(parts[-1]) * -1
                    if len(parts) == 3:
                        m = rx["date"].search(parts[1])
                        if not m:
                            sys.writeln("Can't parse this")
                            sys.exit()
                        if t["date"] != m.group():
                            t["date2"] = m.group()
                        t["type"] = parts[1][: m.start()].strip()
                        t["note"] = parts[1][m.end() :].strip()
                    elif len(parts) == 4:
                        t["type"] = parts[1]
                        t["note"] = parts[2]
                    elif len(parts) == 5 or len(parts) == 6:
                        t["type"] = parts[1]
                        if len(parts) == 6:
                            parts[3] = parts[3] + parts[4]
                        if parts[2][2] == "/":
                            if t["date"] != parts[2][:5]:
                                t["date2"] = parts[2][:5]
                            t["note"] = parts[2][5:] + " " + parts[3]
                        else:
                            t["note"] = parts[2] + " " + parts[3]
                    else:
                        sys.stderr.write("Can't parse ATM/DEBIT parts")
                        sys.stderr.write(str(parts))
                        sys.exit(-1)

                    # Handle a secondary date at the start of the note
                    if t["note"][2] == "/":
                        if t["note"][:5] != t["date"]:
                            t["date2"] = t["note"][:5]
                        t["note"] = t["note"][5:].strip()
                    t["note"] = t["note"].strip()

                    if t["note"][-4:] in ["9743", "5071", "4082"]:
                        t["cardholder"] = "James"
                    if t["note"][-4:] in ["2238", "7681"]:
                        t["cardholder"] = "Karl"

                    self.transactions.append(t)
            if (
                line.startswith("ATM & DEBIT CARD SUMMARY")
                or mode == "ATM & DEBIT CARD SUMMARY"
            ):
                mode = "ATM & DEBIT CARD SUMMARY"
            if line.startswith("ELECTRONIC WITHDRAWALS") or mode == "E-WITHDRAW":
                mode = "E-WITHDRAW"
                if line[2] == "/":
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t["category"] = "E-WITHDRAW"
                    t["date"] = parts[0]
                    t["amount"] = parse_money(parts[-1]) * -1
                    t["note"] = " ".join(parts[1:-1])
                    if t["note"][2] == "/":
                        if t["note"][:5] != t["date"]:
                            t["date2"] = t["note"][:5]
                        t["note"] = t["note"][5:].strip()
                    self.transactions.append(t)
            if line.startswith("OTHER WITHDRAWALS") or mode == "OTHER-WITHDRAW":
                mode = "OTHER-WITHDRAW"
                if line[2] == "/":
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t["category"] = "OTHER-WITHDRAW"
                    t["date"] = parts[0]
                    t["amount"] = parse_money(parts[-1]) * -1
                    t["note"] = " ".join(parts[1:-1])
                    if t["note"][2] == "/":
                        if t["note"][:5] != t["date"]:
                            t["date2"] = t["note"][:5]
                        t["note"] = t["note"][5:].strip()
                    self.transactions.append(t)
            if (
                line.startswith("FEES")
                or line.startswith("FEES AND OTHER WITHDRAWALS")
                or mode == "FEES AND OTHER WITHDRAWALS"
            ):
                mode = "FEES AND OTHER WITHDRAWALS"
                if line[2] == "/":
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t["category"] = "FEES"
                    t["date"] = parts[0]
                    t["amount"] = parse_money(parts[-1]) * -1
                    t["note"] = " ".join(parts[1:-1])
                    if t["note"][2] == "/":
                        if t["note"][:5] != t["date"]:
                            t["date2"] = t["note"][:5]
                        t["note"] = t["note"][5:].strip()
                    self.transactions.append(t)
            if (
                line.startswith("DAILY ENDING BALANCE")
                or mode == "DAILY ENDING BALANCE"
            ):
                mode = "DAILY ENDING BALANCE"
                # line could have 0 or more dates
                if line[2] == "/":
                    parts = line.split()

                    # Catch an odd pdftotext corner case, where we
                    # get just the date, with the rest of the data
                    # pushed down a couple rows
                    if (
                        len(parts) == 1
                        and parts[0][2] == "/"
                        and "*end*daily ending balance2" in lines[i + 1]
                    ):
                        line = line + lines[i + 2]
                        lines[i + 2] = ""
                        parts = line.split()

                    for p in range(0, len(parts), 2):
                        d = "%s/%s" % (self.year, parts[p])
                        self.daily_bal[dateparse.parse(d).date()] = parse_money(
                            parts[p + 1]
                        )
            if (
                line.startswith("SERVICE CHARGE SUMMARY")
                or mode == "SERVICE CHARGE SUMMARY"
            ):
                mode = "SERVICE CHARGE SUMMARY"

        # Turn the dates from strings into proper dates
        for t in self.transactions:
            if "date" in t:
                if not isinstance(t["date"], type(datetime.datetime.now())):
                    t["date"] = dateparse.parse("%s/%s" % (self.year, t["date"])).date()
            else:
                sys.stderr.writeln("No date in transaction:")
                sys.stderr.writeln(t.dump())
                sys.exit(-1)
            if "date2" in t:
                t["date2"] = dateparse.parse("%s/%s" % (self.year, t["date2"])).date()

    def sanity_check(self):
        """Make sure things add up."""

        total = self.begin_bal

        # Make sure deposits add up
        t = parse_money(
            sum([t["amount"] for t in self.transactions if t["category"] == "DEPOSIT"])
        )
        if t != parse_money(self.deposits):
            u.err(
                "%s deposits (%s) don't add up to %s\n"
                % (self.pdfname, t, self.deposits)
            )
        total += t

        # Make sure checks add up
        t = parse_money(
            sum([t["amount"] for t in self.transactions if t["category"] == "CHECK"])
        )
        if t != parse_money(self.paid_checks_total):
            sys.stderr.write(
                "%s/%s total check mismatch (%s != %s)\n"
                % (self.year, self.month, t, self.paid_checks_total)
            )
            sys.stderr.write(
                "".join(
                    [t.dump() for t in self.transactions if t["category"] == "CHECK"]
                )
            )
            sys.stderr.write("\n")
            sys.exit(-1)
        total += t

        # TODO: check the summary of checks paid against everything else

        # Make sure card withdrawals add up
        t = parse_money(
            sum(
                [t["amount"] for t in self.transactions if t["category"] == "ATM/DEBIT"]
            )
        )
        try:
            if t != self.card_withdrawals:
                u.err(
                    "%s card withdrawals (%s) don't add up to %s\n"
                    % (self.pdfname, t, self.card_withdrawals)
                )
            total += t
        except AttributeError:
            pass

        # Make sure e-withdrawals add up
        t = parse_money(
            sum(
                [
                    t["amount"]
                    for t in self.transactions
                    if t["category"] == "E-WITHDRAW"
                ]
            )
        )
        try:
            if t != self.electronic_withdrawals:
                sys.stderr.write(
                    "%s e-withdrawals (%s) don't add up to %s\n"
                    % (self.pdfname, t, self.electronic_withdrawals)
                )
                print(
                    "\n".join(
                        [
                            t.dump()
                            for t in self.transactions
                            if t["category"] == "E-WITHDRAW"
                        ]
                    )
                )
                sys.exit(-1)
            total += t
        except AttributeError:
            pass

        # Make sure other withdrawals add up
        t = parse_money(
            sum(
                [
                    t["amount"]
                    for t in self.transactions
                    if t["category"] == "OTHER-WITHDRAW"
                ]
            )
        )
        try:
            if t != self.other_withdrawals:
                u.err(
                    "%s other withdrawals (%s) don't add up to %s\n"
                    % (self.pdfname, t, self.other_withdrawals)
                )
            total += t
        except AttributeError:
            pass

        # Make sure fees and other withdrawals add up
        t = parse_money(
            sum([t["amount"] for t in self.transactions if t["category"] == "FEES"])
        )
        try:
            if t != self.fees:
                u.err(
                    "%s fees and other withdrawals (%s) don't add up to %s\n"
                    % (self.pdfname, t, self.fees)
                )
            total += t
        except AttributeError:
            pass

        # Check that the daily balances printed on the statement
        # match the daily balances we calculate by totting up all the
        # transactions.
        curr = None
        running = 0
        cumulative = self.begin_bal
        for tx in sorted(self.transactions, key=lambda k: k["date"]):
            if curr != tx["date"]:
                if curr and running:
                    if cumulative != self.daily_bal[curr]:
                        u.err(
                            "%s doesn't add up. " % self.pdfname
                            + "Daily balance in statements (%s) != daily bal calculated from statement (%s)\n"
                            % (self.daily_bal[curr], cumulative)
                        )
                running = 0
                curr = tx["date"]
            cumulative += tx["amount"]
            running += tx["amount"]

        # Make sure total amounts add up to the delta between start/end balances
        # Do this check last so a more specific one triggers errors before we
        # get here
        if total != self.end_bal:
            u.err(
                "%s transactions (%s) don't add up to ending balance (%s)\n"
                % (self.pdfname, total, self.end_bal)
                + "There's %s unaccounted\n" % (total - self.end_bal)
            )
