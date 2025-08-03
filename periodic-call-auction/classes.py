
from datetime import timedelta, time, datetime, date
import numpy as np
import pandas as pd

class PCAmarket:

    def __init__(self,
                 order_entry_start: time,
                 order_matching_start: time,
                 buffer_start: time,
                 current_time: time
                 ):
        """
        the state of the PCA (Periodic call auction) can be:
        -0 = order entry period
        happens between "order_entry_start" and "order_matching_start"
        -1 = order matching & trading period
        happens between "order_matching_start" and "buffer_start"
        -2 = buffer period
        """
        
        self.order_entry_start = order_entry_start
        self.order_matching_start = order_matching_start
        self.buffer_start = buffer_start

        self.order_book = pd.DataFrame( # bid/ask = 0 => bid, else ask
            columns=['Price', 'Volume', 'Bid/Ask', 'Time', 'OwnerID', 'OrderID']
        ) # stores all querying orders
        self.all_orders_made = [] # stores all orders made during session

        self.current_time = current_time
        self.open_price = None

        self.exec_table = None

        self.check_state()

        self.participants = pd.DataFrame(columns=['ID', 'Balance', 'AssetBalance'])

    def add_participant(self, balance):
        if self.participants.empty:
            self.participants = pd.DataFrame([[0, balance, 0]], columns=self.participants.columns)
        else:
            self.participants.loc[self.participants.index.max()+1] = [
                max(self.participants['ID'].values)+1, balance, 0
            ]

    def add_order(self, price: float, volume: float, bid: bool, dt: time, ownerid: int):
        assert self.state == 0, AssertionError()
        if self.order_book.empty:
            self.order_book = pd.DataFrame([
                [price, volume, 0 if bid else 1, dt, ownerid, 0]
            ], columns=self.order_book.columns)
        else:
            self.order_book.loc[self.order_book.index.max()+1] = [
                price, volume, 0 if bid else 1, dt, ownerid,
                max(self.order_book['OrderID'].values)+1
            ]

    def check_state(self):
        if self.order_entry_start <= self.current_time <= self.order_matching_start:
            self.state = 1
        elif self.order_matching_start <= self.current_time <= self.buffer_start:
            self.state = 2
        else:
            self.state = 0

    def advance_time(self, delta: timedelta):
        self.current_time = (datetime.combine(date.today(), self.current_time) + delta).time()
        self.check_state()

    def fill_order(self, bid_ownerid, ask_ownerid):
        """Updates orderbook and makes transaction"""
        bid_order = self.order_book[self.order_book['OrderID'] == bid_ownerid]
        ask_order = self.order_book[self.order_book['OrderID'] == ask_ownerid]

        price = bid_order['Price']

        print('bid order:'); print(bid_order)
        print('ask order:'); print(ask_order)
        print("bid_ownerid:", bid_ownerid)
        print("ask_ownerid:", ask_ownerid)

        bid_p = self.participants[self.participants['ID'] == bid_order['OwnerID']]
        ask_p = self.participants[self.participants['ID'] == ask_order['OwnerID']]

        m = min(bid_order['Volume'], ask_order['Volume'])
        
        ob_index_bid = self.order_book.index[self.order_book['OrderID'] == bid_ownerid]
        ob_index_ask = self.order_book.index[self.order_book['OrderID'] == ask_ownerid]

        self.order_book.loc[ob_index_bid, 'Volume'] -= m
        self.order_book.loc[ob_index_ask, 'Volume'] -= m

        print('updating balances of', bid_p.id, 'and', ask_p.id, 'to', m * bid_order.price)
        bid_idx = self.participants.index[self.participants['ID'] == bid_order['OwnerID']]
        ask_idx = self.participants.index[self.participants['ID'] == bid_order['OwnerID']]
        if bid_order.volume >= ask_order.volume:
            self.participants.loc[bid_idx, 'Balance'] -= m * price
            self.participants.loc[bid_idx, 'AssetBalance'] += m
            self.participants.loc[ask_idx, 'Balance'] += m * price
            self.participants.loc[ask_idx, 'AssetBalance'] -= m
        else:
            self.participants.loc[bid_idx, 'Balance'] += m * price
            self.participants.loc[bid_idx, 'AssetBalance'] -= m
            self.participants.loc[ask_idx, 'Balance'] -= m * price
            self.participants.loc[ask_idx, 'AssetBalance'] += m

        if self.order_book.loc[ob_index_bid, 'Volume'] == 0:
            print('deleting order')
            self.order_book = self.order_book[self.order_book['OrderID'] != bid_ownerid]
        if self.order_book.loc[ob_index_ask, 'Volume'] == 0:
            print('deleting ask order')
            self.order_book = self.order_book[self.order_book['OrderID'] != ask_ownerid]

    def determine_open_price(self):
        """
        -Collect all orders of the market session, ascending / descending dep. on buy/sell
        -Find matching volume
        """
        assert self.state == 0, AssertionError()

        bids = self.order_book[self.order_book['Bid/Ask'] == 0][['Price', 'Volume', 'OwnerID']]
        bids['BidVolumes'] = bids['Volume']
        bids = bids.groupby('Price').agg({
                'OwnerID': list,
                'BidVolumes': list,
                'Volume': 'sum'
            }).reset_index()
        bids = bids.sort_values(by=['Price'], ascending=True)
        bids['BidCumVol'] = bids['Volume'].cumsum()
        bids = bids.drop(['Volume'], axis=1)
        bids = bids.rename({'OwnerID': 'BidOwnerIDs'}, axis=1)
        
        asks = self.order_book[self.order_book['Bid/Ask'] == 1][['Price', 'Volume', 'OwnerID']]
        asks['AskVolumes'] = asks['Volume']
        asks = asks.groupby('Price').agg({
                'OwnerID': list,
                'AskVolumes': list,
                'Volume': 'sum'
            }).reset_index()
        asks = asks.sort_values(by=['Price'], ascending=False)
        asks['AskCumVol'] = asks['Volume'].cumsum()
        asks = asks.drop(['Volume'], axis=1)
        asks = asks.rename({'OwnerID': 'AskOwnerIDs'}, axis=1)
        
        x = set(asks['Price']).intersection(set(bids['Price']))
        bids_f = bids[bids['Price'].isin(x)]
        asks_f = asks[asks['Price'].isin(x)]

        y = bids_f.merge(asks_f, on='Price').reset_index()
        y['MatchedVol'] = y[['AskCumVol', 'BidCumVol']].values.min(axis=1)
        self.open_price = y['Price'][np.argmax(y['MatchedVol'].values)]
        self.exec_table = y

    def start_trade_period(self):
        assert self.state == 1, AssertionError("incorrect time to start trading")

        def fill(askvols, bidvols, askownerids, bidownerids):
            if (
                not askvols or not bidvols
                or sum(askvols) == 0 or sum(bidvols) == 0
            ):
                return
            
            for i in range(len(askvols)):
                if askvols[i] != 0:
                    askvols = askvols[i:]
                    askownerids = askownerids[i:]
                    break
            for j in range(len(bidvols)):
                if bidvols[j] != 0:
                    bidvols = bidvols[j:]
                    bidownerids = bidownerids[j:]
                    break
            
            m = min(askvols[0], bidvols[0])
            askvols[0] -= m
            bidvols[0] -= m

            self.fill_order(bidownerids[0], askownerids[0])
            return fill(askvols, bidvols, askownerids, bidownerids)
            
        prev_orderbook = pd.DataFrame()
        while not prev_orderbook.equals(self.order_book):
            prev_orderbook = self.order_book.copy()
            for idx, row in self.exec_table.iterrows():
                print(row)
                fill(
                    row['AskVolumes'][:],
                    row['BidVolumes'][:],
                    row['AskOwnerIDs'][:],
                    row['BidOwnerIDs'][:]
                    )

        print(self.order_book)
        print('balances:')
        for p in self.participants:
            print(p.balance)

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
        current_time=time(hour=7, minute=0, second=0)
    )

    # every market participant sends a random amount of orders
    for i in range(n_market_participants):

        market.add_participant(balance=10_000)

        nr_of_trades = np.random.randint(min_number_of_trades, max_number_of_trades+1)

        buy_pct = np.random.normal(0.5, 0.1)

        nr_of_buys = int(nr_of_trades * buy_pct)
        nr_of_sells = nr_of_trades - nr_of_buys

        buy_prices = np.round(np.random.uniform(min_price, max_price, size=nr_of_buys), decimals=price_decimals)
        sell_prices = np.round(np.random.uniform(min_price, max_price, size=nr_of_sells), decimals=price_decimals)
        buy_volumes = np.round(np.random.uniform(min_vol, max_vol, size=nr_of_buys))
        sell_volumes = np.round(np.random.uniform(min_vol, max_vol, size=nr_of_sells))

        for bv, bp in zip(buy_volumes, buy_prices):
            market.add_order(bp, bv, True, time(hour=7, minute=0, second=0), i)
        for sv, sp in zip(sell_volumes, sell_prices):
            market.add_order(bp, bv, False, time(hour=7, minute=0, second=0), i)

    # begin trading period
    market.determine_open_price() # determines open price of the entire trading session
    market.advance_time(timedelta(hours=2))
    market.start_trade_period()
        

if __name__ == '__main__':
    main()
