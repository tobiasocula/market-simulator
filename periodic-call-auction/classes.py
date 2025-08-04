
from datetime import timedelta, time, datetime, date
import numpy as np
import sys
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
        assert self.state == 1, AssertionError()
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
            self.state = 1 # order entry
        elif self.order_matching_start <= self.current_time <= self.buffer_start:
            self.state = 2 # order matching & trading
        else:
            self.state = 0 # buffer

    def advance_time(self, delta: timedelta):
        self.current_time = (datetime.combine(date.today(), self.current_time) + delta).time()
        self.check_state()

    def get_stats_of_participant(self, part_id: int):
        return self.participants[self.participants['ID'] == part_id]
    
    def all_part_ids(self):
        for idx, row in self.participants.iterrows():
            yield row['ID']
    
    def cancel_order(self, order_id: int, part_id: int):
        assert self.state == 1, AssertionError()
        order = self.order_book.loc[self.order_book['OrderID'] == order_id]
        assert not order.empty, AssertionError()
        assert order['OwnerID'] == part_id, AssertionError()
        self.order_book.loc[self.order_book['OrderID'] != order_id]

    def modify_order(self, order_id: int, part_id: int, add_volume: float):
        assert self.state == 1, AssertionError()
        order = self.order_book.loc[self.order_book['OrderID'] == order_id]
        assert not order.empty, AssertionError()
        assert order['OwnerID'] == part_id, AssertionError()
        self.order_book.loc[self.order_book['OrderID'] == order_id, 'Volume'] += add_volume

    def determine_open_price(self):
        """
        -Collect all orders of the market session, ascending / descending dep. on buy/sell
        -Find matching volume
        -Determine open price
        """
        assert self.state == 2, AssertionError()

        bids = self.order_book[self.order_book['Bid/Ask'] == 0][
            ['Price', 'Volume', 'OwnerID', 'OrderID']
            ]
        bids['BidVolumes'] = bids['Volume'].copy()
        bids = bids.groupby('Price').agg({
                'OwnerID': list,
                'BidVolumes': list,
                'OrderID': list,
                'Volume': 'sum'
            }).reset_index()
        bids = bids.sort_values(by='Price', ascending=True)
        bids['BidCumVol'] = bids['Volume'].cumsum()
        bids = bids.drop(['Volume'], axis=1)
        bids = bids.rename({'OwnerID': 'BidOwnerIDs', 'OrderID': 'BidOrderIDs'}, axis=1)
        
        asks = self.order_book[self.order_book['Bid/Ask'] == 1][
            ['Price', 'Volume', 'OwnerID', 'OrderID']
            ]
        asks['AskVolumes'] = asks['Volume'].copy()
        asks = asks.groupby('Price').agg({
                'OwnerID': list,
                'AskVolumes': list,
                'OrderID': list,
                'Volume': 'sum'
            }).reset_index()
        asks = asks.sort_values(by='Price', ascending=False)
        asks['AskCumVol'] = asks['Volume'].cumsum()
        asks = asks.drop(['Volume'], axis=1)
        asks = asks.rename({'OwnerID': 'AskOwnerIDs', 'OrderID': 'AskOrderIDs'}, axis=1)

        x = set(asks['Price']).intersection(set(bids['Price']))
        bids_f = bids[bids['Price'].isin(x)]
        asks_f = asks[asks['Price'].isin(x)]
        y = bids_f.merge(asks_f, on='Price').reset_index()

        y['MatchedVol'] = y[['AskCumVol', 'BidCumVol']].values.min(axis=1)
        self.open_price = y['Price'][np.argmax(y['MatchedVol'].values)]
        self.exec_table = y

    def execute_trades(self):
        """Executing trades and clearing order book"""
        assert self.state == 2, AssertionError("incorrect time to start trading")
        print(self.order_book)
        for idx, row in self.exec_table.iterrows():
            while (
                sum(self.exec_table.loc[idx, 'AskVolumes']) > 0 and
                sum(self.exec_table.loc[idx, 'BidVolumes']) > 0
            ):

                for i, askvol in enumerate(self.exec_table.at[idx, 'AskVolumes']):
                    if askvol != 0:
                        self.exec_table.at[idx, 'AskVolumes'] = self.exec_table.at[idx, 'AskVolumes'][i:]
                        self.exec_table.at[idx, 'AskOwnerIDs'] = self.exec_table.at[idx, 'AskOwnerIDs'][i:]
                        self.exec_table.at[idx, 'AskOrderIDs'] = self.exec_table.at[idx, 'AskOrderIDs'][i:]
                        break
                for j, bidvol in enumerate(self.exec_table.at[idx, 'BidVolumes']):
                    if bidvol != 0:
                        self.exec_table.at[idx, 'BidVolumes'] = self.exec_table.at[idx, 'BidVolumes'][j:]
                        self.exec_table.at[idx, 'BidOwnerIDs'] = self.exec_table.at[idx, 'BidOwnerIDs'][j:]
                        self.exec_table.at[idx, 'BidOrderIDs'] = self.exec_table.at[idx, 'BidOrderIDs'][j:]
                        break
                
                vol = min(
                    self.exec_table.at[idx, 'AskVolumes'][0],
                    self.exec_table.at[idx, 'BidVolumes'][0]
                )
                
                price = self.exec_table.at[idx, 'Price']
                bid_ownerid = self.exec_table.at[idx, 'BidOwnerIDs'][0]
                ask_ownerids = self.exec_table.at[idx, 'AskOwnerIDs'][0]
                bid_orderid = self.exec_table.at[idx, 'BidOrderIDs'][0]
                ask_orderid = self.exec_table.at[idx, 'AskOrderIDs'][0]

                self.exec_table.loc[idx, 'AskVolumes'][0] -= vol
                self.exec_table.loc[idx, 'BidVolumes'][0] -= vol

                # modify order book
                if self.exec_table.loc[idx, 'AskVolumes'][0] == 0:
                    self.order_book = self.order_book[
                        self.order_book['OrderID'] != ask_orderid
                    ]
                else:
                    self.order_book.loc[
                        self.order_book['OrderID'] == ask_orderid,
                        'Volume'
                    ] -= vol

                if self.exec_table.loc[idx, 'BidVolumes'][0] == 0:
                    self.order_book = self.order_book[
                        self.order_book['OrderID'] != bid_orderid
                    ]
                else:
                    self.order_book.loc[
                        self.order_book['OrderID'] == bid_orderid,
                        'Volume'
                    ] -= vol

                # handle funds
                self.participants.loc[
                    self.participants['ID'] == bid_ownerid, 'Balance'
                ] -= vol * price
                self.participants.loc[
                    self.participants['ID'] == bid_ownerid, 'AssetBalance'
                ] += vol

                self.participants.loc[
                    self.participants['ID'] == ask_ownerids, 'Balance'
                ] += vol * price
                self.participants.loc[
                    self.participants['ID'] == ask_ownerids, 'AssetBalance'
                ] -= vol
        