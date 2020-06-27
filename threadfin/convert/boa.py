"""
Parse bank of America bank statements
"""

from dateutil import parser as dateparse
import re
import sys

# Our code
import statement
from transaction import Transaction
import util as u
from util import parse_money

regex = {
    'summary': re.compile(r"^([,\w ]+)\b +\$?(-?[\d.,]+)")
    }

class Statement(statement.Statement):
    def __init__(self, pdfname, custom):
        """PDFNAME is the filename of the pdf"""
        if not "<</Creator(Bank of America)/Author(Bank of America)" in u.slurp(pdfname):
            self.bank = ""
            return
        self.bank = "Bank of America"
        statement.Statement.__init__(self, pdfname, custom)

    def fix_date(self, datetxt):
        """Take a boa-formatted date, assume year = year of statement, strip trailing chars, and return a date object"""
        date_parts = datetxt.split('/')
        date_parts[2] = str(self.year)
        return dateparse.parse("/".join(date_parts))

    def parse(self):
        txt = self.text
        mode = "start"
        lines = txt.split("\n")
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            if line.startswith("Account summary") or mode == "Account summary":
                mode="Account summary"
                m = regex['summary'].match(line)
                if m:
                    label = m.groups()[0]
                    amt = parse_money(m.groups()[1])
                    
                    if line.startswith("Beginning balance on"):
                        self.begin_bal = amt
                    if label == "Checks":
                        self.paid_checks_total = amt
                    if line.startswith("Ending balance on"):
                        self.end_bal = amt
                    if line.startswith("Deposits and other credits"):
                        self.deposits = amt
                    if label == "Withdrawals and other debits":
                        self.other_withdrawals = amt
                    if label == "Service fees":
                        self.fees = amt
                        
            if line == "Deposits and other credits" or mode == "DEPOSITS AND ADDITIONS":
                mode = "DEPOSITS AND ADDITIONS"
                if line[2] == "/": # Slash indicates a date, which indicates a transaction
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t['category'] = "DEPOSIT"
                    t['date'] = self.fix_date(parts[0])
                    t['amount'] = parse_money(parts[-1])
                    self.transactions.append(t)
                    
            if line == "Withdrawals and other debits" or mode == "Withdrawals and other debits":
                mode = "Withdrawals and other debits"
                if line[2] == "/": # Slash indicates a date, which indicates a transaction
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t['category'] = "OTHER-WITHDRAW"
                    t['date'] = self.fix_date(parts[0])
                    t['amount'] = parse_money(parts[-1])
                    t['note'] = " ".join(parts[1:-1])
                    if len(lines[i+1])>=4 and lines[i+1][2] != "/":
                        last_four = re.sub("[^0-9]", "", lines[i+1][-4:])
                        if last_four == "5713":
                            t['cardholder'] = 'Stray'
                        elif last_four == "1176":
                            t['cardholder'] = 'Powell'
                        elif len(last_four) != 4:
                            pass
                        else:
                            sys.stderr.write("In %s, can't id cardholder:\n%s\n%s\n" % (self.pdfname, line, lines[i+1]))
                            sys.exit(-1)
                    self.transactions.append(t)
            if line.startswith("Total withdrawals and other debits"):
                mode = None
            if line == "Checks" or mode == "Checks":
                mode = "Checks"
                if line[2] == '/':
                    parts = [l.strip() for l in line.split("  ") if l]
                    # line could have 0 or more dates
                    for p in range(0, len(parts), 3):
                        t = Transaction()
                        t['category']='CHECK'
                        t['date'] =  self.fix_date(parts[p])
                        t['number'] = int(re.sub("[^0-9]", "", parts[p+1]))
                        t['amount'] = parse_money(parts[p+2])
                        self.transactions.append(t)                                
            if line == "Service fees" or mode == "Service fees":
                mode = "Service fees"
                if line[2] == '/' and line[8] != ":":
                    parts = [l.strip() for l in line.split("  ") if l]
                    t = Transaction()
                    t['category'] = "FEES"
                    t['date'] = self.fix_date(parts[0])
                    t['amount'] = parse_money(parts[-1])
                    t['note'] = " ".join(parts[1:-1])
                    if lines[i+1].endswith("5713"):
                        t['cardholder'] = 'Stray'
                    elif  lines[i+1].endswith("1176"):
                        t['cardholder'] = 'Powell'
                    self.transactions.append(t)
            if line.startswith("Daily ledger balance") or mode == "DAILY ENDING BALANCE":
                mode = "DAILY ENDING BALANCE"
                # line could have 0 or more dates
                if len(line) >= 3 and line[2] == '/':
                    parts = line.split()
                    for p in range(0, len(parts), 2):
                        d = "%s/%s" % (self.year, parts[p])
                        self.daily_bal[dateparse.parse(d)] = parse_money( parts[p+1] )
