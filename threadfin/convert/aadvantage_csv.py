#!/usr/bin/env python3

"""This is a parser for the csv emitted by the Barclay American
Airlind AAdvantage card's website.  Convert.py uses it and
`threadfin.yaml` to turn that csv data into beancount entries.

The CSV has lines like this:
Barclays Bank Delaware
Account Number: XXXXXXXXXXXX0101
Account Balance as of June 25 2020:    $dddd.cc

    12/28/2019,"EXXONMOBIL    97662472","DEBIT",-34.18
    12/17/2019,"NEWEGG INC","DEBIT",-57.69
    12/11/2019,"AA ADMIRALS CLUB LAX","DEBIT",-15.05

You'll notice they are in descending date order, though that shouldn't
matter much here.
"""

import csv
import io
import pprint
import sys

import util as u
import statement
import transaction

pp = pprint.PrettyPrinter(indent=4).pprint

class UnimplementedError(Exception):
    pass


class Transaction(transaction.Transaction):
    def as_beancount(self):

        self.vals['date'] = self['date'].strftime("%Y-%m-%d")

        for field in 'cardholder code comment payee narration'.split(' '):
            self.vals[field] = ''
        self.vals['account'] = "Expenses:AAdvantage"
        self.vals['account2'] = "Liabilities:AAdvantage"
        self.vals['amount'] = self['amount'].amount
        self.vals['category'] = self['category']
        self.vals['comment'] = self.get('note', '')
        self.vals['currency'] = self['amount'].currency
        self.vals['narration'] = self.get('narration', '')

        if 'comment' in CUSTOM:
            self.vals = self.custom_match_comment(CUSTOM['comment'], self.vals)

        if self.vals['payee'] == '' and self.vals['narration'] == '':
            self.vals['narration'] = self.get('note', '')

        if not self['category'] in ['debit', 'credit']:
            raise UnimplementedError(
                "Can't handle %s in tx dated %s" %
                (self['category'], self['date']))

        return self.interpolate(self.vals)


class Statement(statement.Statement):
    "Barclay AAdvantage card parser"

    def __init__(self, fname, custom):
        """FNAME is the filename of the csv

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
        statement.Statement.__init__(self, fname, custom)
        key = "Barclays Bank Delaware"
        text = self.text
        if not isinstance(self.text, str):
            text = self.text.decode("latin-1")
        if not text.startswith(key):
            self.bank = ""
            return
        self.text = text
        self.bank = "Barclay AAdvantage Card"

        # Make custom available to transactions without passing it all
        # the way through.
        global CUSTOM
        CUSTOM = custom

        self.beanfile_preamble = (";; -*- mode: org; mode: beancount; -*-\n" +
                                  "1975-01-01 open Expenses:AAdvantage\n" +
                                  "1975-01-01 open Liabilities:AAdvantage\n")

    def parse(self):
        sh = io.StringIO(self.text)
        fieldnames = ['date', 'narration', 'category', 'amount']
        reader = csv.DictReader(sh, fieldnames)
        rows = list(reader)[5:]
        for row in rows:

            row['category'] = row['category'].lower()

            while '  ' in row['narration']:
                row['narration'] = row['narration'].replace('  ', ' ')

            # Make tx
            tx = Transaction()
            tx['category'] = row['category']
            tx['date'] = u.parse_date(row['date'])
            tx['amount'] = u.parse_money(row['amount'])
            tx['note'] = row['narration']
            self.append(tx)

    def sanity_check(self):
        """The CSV doesn't have redundant info we can sanity check.
        Fortunately, it's also very simple"""
        pass
