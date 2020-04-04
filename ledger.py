from dateutil.parser import parse
from datetime import datetime
import re

def has_date(s):
    patterns = [
        "\d{4}\/\d{2}\/\d{2}",
        "\d{2}\/\d{2}\/\d{4}",
        "\d{4}-\d{2}-\d{2}",
        "\d{2}-\d{2}"
    ]
    return any((re.search(p, s) for p in patterns))

def get_indent(s):
    return len(s) - len(s.lstrip())

class Ledger:
    def __init__(self, fname):
        try:
            with open(fname, "r") as f:
                self.raw_lines  = f.readlines()
                lines = [l for l in self.raw_lines if not l.lstrip().startswith(";")]
                #macros = [l.strip().split(" ") for l in lines if l.startswith("@")]
        except:
            raise Exception("Ledger not found")

        # find first transaction
        first = next((i for i in range(len(lines)) if has_date(lines[i])), -1)
        if first == -1 or first + 1 == len(lines):
            raise("Ledger has no transactions")

        self.indent = get_indent(lines[first])
        self.indent2 = get_indent(lines[first + 1])
        self.line_len = len(lines[first + 1])
        self.transactions = []

        for i in range(len(lines)):
            if has_date(lines[i]):
                start = i
                j = i + 1
                while j < len(lines) and get_indent(lines[j]) == self.indent2:
                    j += 1
                self.transactions.append(Transaction(i, lines[start:j]))

    def add_transaction(self, tx):
        lines = []
        lines.append(f"{self.indent * ' '}{tx['date']} {tx['description']}\n")
        for i in range(len(tx['accounts'])):
            left_part = (self.indent2 * ' ' + tx['accounts'][i]).ljust(self.line_len)
            amount_str = str(tx['amounts'][i])
            line = left_part[0:self.line_len - len(amount_str) - 1] + amount_str
            lines.append(f"{line}\n")

        j = 0
        parse_date = lambda x: datetime.strptime(x, "%Y/%m/%d")
        while j < len(self.transactions) and parse_date(tx['date']) > parse_date(self.transactions[j].date):
            j += 1
        skip_lines = self.transactions[j].start_line if j < len(self.transactions) else len(self.raw_lines)
        self.raw_lines = self.raw_lines[0:skip_lines] + lines + self.raw_lines[skip_lines:]

        self.transactions.insert(j, Transaction(skip_lines, lines))
        for i in range(j, len(self.transactions)):
            self.transactions[i].start_line += len(lines)

    def to_file(self, fname):
        with open(fname, "w") as f:
            for line in self.raw_lines:
                f.write(line)

class Transaction:
    def __init__(self, start_line, lines):
        self.start_line = start_line
        self.lines = lines
        self.date = lines[0].split(" ")[0]
        self.amounts = []
        self.accounts = []
        for i in range(1, len(lines)):
            parts = re.split("\s+", lines[i].strip().replace("\t", "  "))
            self.accounts.append(parts[0])
            if len(parts) > 1:
                self.amounts.append(parts[1])

    def has_amount(self, s):
        search = "".join([c for c in s if c.isdigit() or c == '.'])
        return any((search in amount for amount in self.amounts))

    def __repr__(self):
        return "".join(self.lines)
