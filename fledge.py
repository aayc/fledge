from plaid import Client
from ledger import Ledger
from pprint import pprint
from server import mini_server
import argparse
import csv
import json
import sys
import uuid
from datetime import datetime, timedelta
from colorama import Fore, Style
from util import yes_or_no

class Credentials:
    def __init__(self, fname):
        with open(fname, "r") as f:
            self.credentials = json.load(f)

        self.client_id  = self.credentials.get("client_id", False)
        self.secret     = self.credentials.get("secret", False)
        self.public_key = self.credentials.get("public_key", False)
        assert self.client_id and self.secret and self.public_key

    def __repr__(self):
        return json.dumps(self.credentials)

class Plaid:
    def __init__(self, credentials):
        self.client = Client(
            client_id=credentials.client_id,
            secret=credentials.secret,
            public_key=credentials.public_key,
            suppress_warnings=True,
            environment='development',
            api_version='2019-05-29'
        )

    def get_access_token(self, public_token):
        response = self.client.Item.public_token.exchange(public_token)
        return {
            "access_token": response["access_token"],
            "item_id" : response["item_id"]
        }

    def download_transactions(self, token, accounts, start, end):
        account_ids = set([a["id"] for a in accounts])
        res = self.client.Transactions.get(token, start_date=start, end_date=end)
        transactions = res["transactions"]
        return [t for t in transactions if t["account_id"] in account_ids]

class Fledge:
    def __init__(self, credentials_file):
        self.credentials = Credentials(args.credentials)
        self.plaid = Plaid(self.credentials)
        self.transaction_headers = ["account_id", "transaction_id", "category_id", "category", "name", "date", "iso_currency_code", "amount"]

    def __get_date_ago(self, n=0):
        date = datetime.now() - timedelta(days=n)
        return date.strftime('%Y-%m-%d')

    def __get_transactions(self, args):
        with open(args.access_keys) as f:
            keys = json.load(f)
            access_token = keys["access"]["access_token"]
            accounts = keys["accounts"]
            if args.nickname is not None:
                accounts = [account for account in accounts if account["nickname"] == args.nickname]

        raw_transactions = self.plaid.download_transactions(access_token, accounts, args.start_date, args.end_date)
        transactions = [{ k:self.__format_tx(tx[k]) for k in self.transaction_headers } for tx in raw_transactions]
        return transactions

    def __convert_tx_date(self, date, fmt):
        return datetime.strptime(date, fmt).strftime("%Y/%m/%d")

    def __format_tx(self, obj):
        return obj if not isinstance(obj, list) else ";".join(obj)

    def __is_duplicate(self, t1, ledger_transactions):
        for t2 in ledger_transactions:
            match_amount = t2.has_amount(t1["amount"])
            if match_amount:
                print(f"{Fore.YELLOW}It looks like the following transaction:{Style.RESET_ALL}")
                print(f"Date: {t1['date']}")
                print(f"Name: {t1['name']}")
                print(f"Amount: {t1['amount']}")
                print(f"{Fore.YELLOW}matches the following ledger entry:{Style.RESET_ALL}")
                print(f"{t2}")
                if yes_or_no("Should this imported transaction be ignored?"):
                    print(f"{Fore.GREEN}Ignored!{Style.RESET_ALL}")
                    return True
        print(f"{Fore.GREEN}Keeping all imported transactions for processing...{Style.RESET_ALL}")
        return False

    def sync(self):
        parser = argparse.ArgumentParser(description='Sync your transaction data')
        parser.add_argument('access_keys', type=str, help='Your access keys json file (Don\'t have it?  See documentation and run fledge \'link\' <your Plaid credentials>)')
        parser.add_argument('ledger', type=str, help='Your ledger file')
        parser.add_argument('--nickname', type=str, help='Specific account to download from')
        parser.add_argument('--start_date', type=str, default=self.__get_date_ago(n=30), help='Format: YYYY-MM-DD, e.g., 2020-02-02')
        parser.add_argument('--end_date', type=str, default=self.__get_date_ago(), help='Format: YYYY-MM-DD, e.g., 2020-02-02')
        args = parser.parse_args(sys.argv[3:])

        tmp_file = "tmp" + uuid.uuid1() + ".csv"
        ledger = Ledger(args.ledger)
        transactions = self.__get_transactions(args)
        self.do_merge(ledger, transactions)

    def merge(self, verbose=True):
        parser = argparse.ArgumentParser(description='Merge transaction file with ledger')
        parser.add_argument('ledger', type=str, help='Your ledger file')
        parser.add_argument('transactions', type=str, help=f'Transactions csv file with headers {"".join(self.transaction_headers)}')
        parser.add_argument('--out', type=str, default="new_ledger.dat", help="Updated ledger file name to write to")
        args = parser.parse_args(sys.argv[3:])

        ledger = Ledger(args.ledger)
        with open(args.transactions) as f:
            transactions = [r for r in csv.DictReader(f)]

        self.do_merge(ledger, transactions)

    def do_merge(self, ledger, transactions):
        transactions = [t for t in transactions if not self.__is_duplicate(t, ledger.transactions)]
        print("=" * 20)
        date_format = input("Transaction file date format? (default: %Y-%m-%d): ").strip()
        date_format = "%Y-%m-%d" if date_format == "" else date_format
        flip_pos_neg = yes_or_no("Flip +/- on amounts?")
        print(f"{Fore.GREEN}Interactively walking you through the merge process... {Style.RESET_ALL}")
        print("\tType ?SKIP at any prompt to skip the current transaction")
        print("\tType ?RESTART at any prompt to restart the current transaction")
        print("\tType ?REDO at any prompt to redo all transactions")

        i = 0
        writable_transactions = []
        while i < len(transactions):
            t = transactions[i]
            prompts = [["Date", self.__convert_tx_date(t["date"], date_format)], ["Description", t["name"]]]
            answers = []
            special = False
            for (prompt, default) in prompts:
                answer = input(f"{prompt} (default: {default}): ").strip()
                if answer == "":
                    answer = default
                elif answer == "?SKIP":
                    special, i = True, i + 1
                    break
                elif answer == "?REDO":
                    special, i = True, 0
                    break
                elif answer == "?RESTART":
                    special = True
                    break
                answers.append(answer)
            if special:
                continue


            # handle accounts
            j = 1
            accounts = []
            amounts = []
            first = True
            acc = 0
            while True:
                account = input(f"Account {j}: ").strip()
                if account == "-":
                    if j > 2: break
                    else: continue
                elif account == "":
                    continue

                default_amount = -float(t['amount']) if first else -acc
                first = False
                amount = input(f"Amount (default: {default_amount}): ").strip()
                amount = float(amount) if amount != "" else default_amount
                accounts.append(account)
                amounts.append(amount)
                acc += amount
                j += 1

            writable_transactions.append({
                "date": answers[0],
                "description":answers[1],
                "accounts": accounts,
                "amounts": amounts
            })
            i += 1

        for writable_tx in writable_transactions:
            ledger.add_transaction(writable_tx)

        ledger.to_file(args.out)
        print(f"{Fore.GREEN}Success!{Style.RESET_ALL}")
        print(f"A new ledger file {args.out} that combines your previous and these transactions has been created!")

    def download(self):
        parser = argparse.ArgumentParser(description='Download your transaction data')
        parser.add_argument('access_keys', type=str, help='Your access keys json file (Don\'t have it?  See documentation and run fledge \'link\' <your Plaid credentials>)')
        parser.add_argument('--nickname', type=str, help='Specific account to download from')
        parser.add_argument('--out', type=str, default='my_download.csv', help='Output file name')
        parser.add_argument('--start_date', type=str, default=self.__get_date_ago(n=30), help='Format: YYYY-MM-DD, e.g., 2020-02-02')
        parser.add_argument('--end_date', type=str, default=self.__get_date_ago(), help='Format: YYYY-MM-DD, e.g., 2020-02-02')
        args = parser.parse_args(sys.argv[3:])
        transactions = self.__get_transactions(args)

        with open(args.out, 'w') as f:
            dict_writer = csv.DictWriter(f, self.transaction_headers)
            dict_writer.writeheader()
            dict_writer.writerows(transactions)

        print(f"{Fore.GREEN}Success!{Style.RESET_ALL}")
        print(f"A new file {args.out} has been created with transactions from {args.start_date} to {args.end_date}.")

    def link(self):
        parser = argparse.ArgumentParser(description='Link your financial accounts to Plaid APIs to enable automatic download and sync')
        parser.add_argument('--out', type=str, default="my_institution.json", help='Output file name')
        args = parser.parse_args(sys.argv[3:])

        def continue_link(keys):
            keys["access"] = self.plaid.get_access_token(keys["public_token"])
            with open(args.out, "w") as f:
                json.dump(keys, f, sort_keys=True, indent=4)

            print(f"{Fore.GREEN}Success!{Style.RESET_ALL}")
            print(f"A new file {args.out} has been created with credentials for the institution you linked.")
            print("")
            print(f"You're ready to sync your transactions! Run \"fledge sync <ledger file> {args.out}\" to sync all transactions from this institution.")
            print(f"+ Or, to sync per account: fledge sync <ledger file> {args.out} --nickname=<account nickname>")
            print(f"+ Or, to download without syncing: fledge download {args.out} [--nickname=<account nickname>]")

        mini_server(self.credentials.public_key, continue_link)

    def execute(self, command):
        getattr(self, command)()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automatically download and sync your transactions with Ledger CLI')
    parser.add_argument('command', type=str, choices=['link', 'download', 'merge', 'sync'])
    parser.add_argument('credentials', type=str, help='Your credentials json file')
    args = parser.parse_args(sys.argv[1:3])
    Fledge(args.credentials).execute(args.command)
