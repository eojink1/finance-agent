# transactions.csv

One person's bank and credit card transactions, 2026-01-01 to 2026-06-30. Synthetic data.

| Column | Meaning |
|---|---|
| `date` | Posting date, `YYYY-MM-DD` |
| `description` | Merchant text as the bank shows it, e.g. `NETFLIX.COM` |
| `amount` | US dollars. Negative = money out, positive = money in (pay, refunds) |
| `category` | One of: Income, Housing, Utilities, Groceries, Dining, Transportation, Shopping, Subscriptions, Transfer, Credit Card Payment |
| `account` | `checking` or `credit card` |

Definitions:
- **Spending** is money out in every category except Transfer and Credit Card Payment, minus
  refunds (positive amounts in those same categories, other than Income). Report spending as a
  positive number.
- **Transfer** moves money between the person's own accounts; it is not spending or income.
- **Credit Card Payment** pays the card bill from checking. The purchases are already listed on
  the card, so it is not spending or income.
- **Income** is the Income category only.
- A **subscription** is a charge in the Subscriptions category. It is **active** in a month when
  it charged in that month.
