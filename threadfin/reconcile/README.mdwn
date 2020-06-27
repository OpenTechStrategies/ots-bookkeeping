# Reconcile

Reconcile goes through the bank statement and the ledger and tries to
match daily balances in each on the theory that if the daily balances
match, the records match.  So far that's right in all my checking.
When they don't match, you know something is wrong.  At our current
level of activity where we don't have 100s of transactions per day,
this works pretty well and is granular enough info to find missing or
incorrent transactions.

 * Download statements to ~/OTS/finance/statements/YYYY_MM.pdf
 * `threadfin reconcile --config=/path/to/config.yaml`

## Using its output

Run `threadfin reconcile account1 account2`.  You'll see the last
reconcilable date and a reverse-sorted list by date of transactions to
reconcile.  Start working through them by matching the screen data and
the data in the register to the bank statements and the check faces.

Also, you can grep in the statements dir for numbers, which can
provide clues.

You'll see a message telling you the last date on which statement and
beancount ledger lined up.  Pay no attention to transactions on or
before this date.

You can load out.html in a browser and you'll see a two-column view
for the earliest date that reconcile can't figure out.  It will
attempt to match transactions by amount.  This view should give you a
lot of clues as to what's wrong.

We're not making consistent use of our cleared flag, and we should fix
that.  It might help during reconciliation.  Maybe it would be useful
to stop just commenting stuff out and instead only deal with cleared
transactions.

Keep running reconcile and watching the unreconciled transaction list
get shorter.  It's oddly satisfying.
