from datetime import time, timedelta
from .classes import PCAmarket
import numpy as np

def main():

    n_market_participants = 100

    min_number_of_trades = 10
    max_number_of_trades = 30

    min_price = 7.0
    max_price = 13.0
    price_decimals = 2

    min_vol = 100
    max_vol = 300

    # initializes state to order-sending period
    market = PCAmarket(
        # just sample timestamps
        order_entry_start=time(hour=7, minute=30, second=0),
        order_matching_start=time(hour=9, minute=0, second=0),
        buffer_start=time(hour=10, minute=0, second=0),
        current_time=time(hour=7, minute=30, second=0)
    )

    # every market participant sends a random amount of orders
    for i in range(n_market_participants):

        part_id = market.add_participant(balance=10_000)

        nr_of_trades = np.random.randint(min_number_of_trades, max_number_of_trades+1)

        buy_pct = np.random.normal(0.5, 0.1)

        nr_of_buys = int(nr_of_trades * buy_pct)
        nr_of_sells = nr_of_trades - nr_of_buys

        buy_prices = np.round(np.random.uniform(min_price, max_price, size=nr_of_buys), decimals=price_decimals)
        sell_prices = np.round(np.random.uniform(min_price, max_price, size=nr_of_sells), decimals=price_decimals)
        buy_volumes = np.round(np.random.uniform(min_vol, max_vol, size=nr_of_buys))
        sell_volumes = np.round(np.random.uniform(min_vol, max_vol, size=nr_of_sells))

        for bv, bp in zip(buy_volumes, buy_prices):
            market.add_order(bp, bv, True, time(hour=7, minute=0, second=0), part_id)
        for sv, sp in zip(sell_volumes, sell_prices):
            market.add_order(sp, sv, False, time(hour=7, minute=0, second=0), part_id)

    # begin trading period
    market.advance_time(timedelta(hours=2))
    market.determine_open_price() # determines open price of the entire trading session
    market.execute_trades() # executes trades

    # advance to buffer period
    market.advance_time(timedelta(hours=3))

    print('Statistics after trading:')
    print(market.participants)

if __name__ == '__main__':
    main()
