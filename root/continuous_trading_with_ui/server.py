
from fastapi import FastAPI, WebSocket, HTTPException
import pandas as pd
from contextlib import asynccontextmanager
from multiprocessing import Pool
import os
import asyncio
import traceback
from datetime import datetime, date, timedelta, time
from pydantic import BaseModel
from typing import Optional
import numpy as np
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

class rpInput(BaseModel):
    amount: Optional[int] = None
    amount_rnd_lower: Optional[int] = None
    amount_rnd_upper: Optional[int] = None


class MarketInitializer(BaseModel):
    open_time: str
    close_time: str
    start_time: str
    progress_step: float
    sleep_step: float
    ws_delay_step: float
    init_open_price: float
    participant_init_balance: float
    n_participants: int
    price_rounding_digits: int

class OrderRequest(BaseModel):
    volume: int
    buy: bool
    participant_id: int
    price: Optional[float | int | None] = None
    time: str
    id: int

baseurl = "http://localhost:8000"


# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.open_price_lock = asyncio.Lock()
    app.state.bid_book_lock = asyncio.Lock()
    app.state.ask_book_lock = asyncio.Lock()
    app.state.time_lock = asyncio.Lock()
    app.state.ws_lock = asyncio.Lock()
    app.state.participants_lock = asyncio.Lock()

    app.state.open_time = None
    app.state.close_time = None
    app.state.progress_step = None
    app.state.sleep_step = None
    app.state.ws_delay_step = None
    app.state.current_time = None
    app.state.participants = pd.DataFrame()
    app.state.bid_book = pd.DataFrame()
    app.state.ask_book = pd.DataFrame()
    app.state.ltp = None # last traded price

    app.state.ws_data_ready = asyncio.Event()
    app.state.ws_connected = asyncio.Event()

    yield # Application starts serving requests here

    # shutdown code

app = FastAPI(lifespan=lifespan) # lifespan is an async context manager

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def market_clock(app: FastAPI):
    while True:
        async with app.state.time_lock:
            app.state.current_time = (
                datetime.combine(date.today(), time.fromisoformat(app.state.current_time))
                                + timedelta(seconds=app.state.progress_step)
            ).time().isoformat()
        await asyncio.sleep(app.state.sleep_step)

@app.get("/wait_for_ws_connection")
async def wait_for_ws_connection():
    while not (app.state.ws_connected.is_set() and app.state.ws_data_ready.is_set()):
        await asyncio.sleep(0.1)


@app.post("/init_market")
async def init_market(market_init: MarketInitializer):
    try:
        async with app.state.time_lock:
            app.state.current_time = market_init.start_time
        async with app.state.open_price_lock:
            app.state.ltp = market_init.init_open_price

        app.state.open_time = market_init.open_time
        app.state.close_time = market_init.close_time
        app.state.current_time = market_init.start_time
        app.state.progress_step = market_init.progress_step
        app.state.sleep_step = market_init.sleep_step
        app.state.ws_delay_step = market_init.ws_delay_step
        app.state.price_rounding_digits = market_init.price_rounding_digits

        # clear previous session data
        app.state.participants = pd.DataFrame()
        app.state.bid_book = pd.DataFrame()
        app.state.ask_book = pd.DataFrame()
        

        data = {
            "init_balance": [market_init.participant_init_balance for _ in range(market_init.n_participants)],
            "balance": [market_init.participant_init_balance for _ in range(market_init.n_participants)],
            "id": [i for i in range(market_init.n_participants)],
            "asset_balance": 0
        }
        async with app.state.participants_lock:
            app.state.participants = pd.DataFrame(data)
            app.state.n_participants = market_init.n_participants
            
        asyncio.create_task(market_clock(app))
        return
    except Exception as e:
        print("Error in /init_market:", e)
        raise

@app.post("/random_participants")
async def random_participants(inp: rpInput):
    assert app.state.n_participants >= 1, AssertionError()
    if inp.amount is None:
        amount = np.random.randint(1, app.state.n_participants+1)
    elif inp.amount_rnd_lower is not None and inp.amount_rnd_upper is not None:
        amount = np.random.randint(inp.amount_rnd_lower, inp.amount_rnd_upper+1)
    else:
        amount = min(inp.amount, app.state.n_participants)
    arr = np.random.randint(0, app.state.n_participants, amount)
    return {"res": [int(x) for x in app.state.participants.iloc[arr]['id'].values]}


@app.post("/place_order_before_market_open")
async def place_order_before_market_open(order: OrderRequest):
    print('CALLED!!!')

    price = order.price if order.price is not None else app.state.ltp

    if order.buy:

        if app.state.bid_book.empty:
            # place first order
            async with app.state.bid_book_lock:
                app.state.bid_book = pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "pid": [order.participant_id],
                    "id": [order.id]
                })
        else:
            async with app.state.bid_book_lock:
                app.state.bid_book = pd.concat([app.state.bid_book, pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "pid": [order.participant_id],
                    "id": [order.id]
                })]).sort_values(['price', 'time'], ascending=[False, False])

    else:

        if app.state.ask_book.empty:
            # place first order
            async with app.state.ask_book_lock:
                app.state.ask_book = pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "pid": [order.participant_id],
                    "id": [order.id]
                })
        else:
            async with app.state.ask_book_lock:
                app.state.ask_book = pd.concat([app.state.ask_book, pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "pid": [order.participant_id],
                    "id": [order.id]
                })]).sort_values(['price', 'time'], ascending=[True, True])


@app.websocket("/ws/marketdata")
async def marketdata(websocket: WebSocket):
    await websocket.accept()
    try:
        async with app.state.ws_lock:
            app.state.ws_connected.set()
            print('set ws connected')
        while True:
            await websocket.send_json({
                "current_time": app.state.current_time,
                "bid_book": app.state.bid_book.to_dict("records"),
                "ask_book": app.state.ask_book.to_dict("records"),
                "current_price": app.state.ltp,
                "participants": app.state.participants.to_dict("records"),
            })
            app.state.ws_data_ready.set()
            await asyncio.sleep(app.state.ws_delay_step)
    except asyncio.CancelledError:
        print("Marketdata websocket handler cancelled")
        await websocket.close()
        raise
    except Exception as e:
        print(f"Unexpected error in websocket handler: {e}")
        await websocket.close()

def allmaxima(arr):
    mi = np.argmax(arr)
    m = max(arr)
    res = [mi]
    for i,a in enumerate(arr):
        if i!=mi and a == m:
            res.append(i)
    return res

def allminima(arr):
    mi = np.argmin(arr)
    m = min(arr)
    res = [mi]
    for i,a in enumerate(arr):
        if i!=mi and a == m:
            res.append(i)
    return res
        


@app.get("/at_market_open")
async def at_market_open():

    if app.state.bid_book.empty or app.state.ask_book.empty:
        # remain old price
        return

    # first determine open price

    if app.state.bid_book.iloc[0]['price'] < app.state.ask_book.iloc[0]['price']:
        """
        Non-overlapping market -> tie breaker
        Choose best bid or ask (closest to previous open)
        """
        async with app.state.open_price_lock:
            app.state.ltp = (
                app.state.bid_book.iloc[0]['price']
                if
                abs(app.state.bid_book.iloc[0]['price'] - app.state.ltp)
                <=
                abs(app.state.ask_book.iloc[0]['price'] - app.state.ltp)
                else
                app.state.ask_book.iloc[0]['price']
            )
        return {"msg": ""}
    """
    else: overlapping market
    use cumulative volume and if necessary imbalance between bids and asks
    """

    alls = (
        pd.concat([
            app.state.ask_book.rename(columns={'volume': 'askvol'}).drop('time', axis=1),
            app.state.bid_book.rename(columns={'volume': 'bidvol'}).drop('time', axis=1)
            ])
        .sort_values('price', ascending=True)
        .reset_index(drop=True)
    ).fillna(0)

    alls['cumask'] = alls['askvol'].cumsum()
    alls['cumbid'] = alls['bidvol'].iloc[::-1].cumsum().iloc[::-1]
    alls['matchvol'] = alls[['cumask', 'cumbid']].values.min(axis=1)
    
    maxints = allmaxima(alls['matchvol'].values)
    if len(maxints) > 1:
        alls['imbalance'] = abs(alls['cumbid'] - alls['cumask'])
        idx = np.argmin(alls.iloc[maxints]['imbalance'].values)
        m = idx + maxints[0]
        price = alls.iloc[m]['price']
    else:
        price = alls.iloc[m]['price']
    
    async with app.state.open_price_lock:
        app.state.ltp = price

    # execute potential trades
    async with app.state.bid_book_lock, app.state.ask_book_lock:

        while True:
            if app.state.bid_book.empty or app.state.ask_book.empty:
                return {"msg": ""}
            if app.state.bid_book.iloc[0]['price'] < app.state.ask_book.iloc[0]['price']:
                return {"msg": ""}
            if app.state.bid_book.iloc[0]['volume'] < app.state.ask_book.iloc[0]['volume']:
                app.state.ask_book.at[0, 'volume'] -= app.state.bid_book.iloc[0]['volume']

                # update participants book
                async with app.state.participants_lock:
                    pid_bid = app.state.participants.index[
                        app.state.participants['id'] == app.state.bid_book.iloc[0]['pid']
                        ]
                    pid_ask = app.state.participants.index[
                        app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                        ]
                    volume = app.state.bid_book.iloc[0]['volume']
                    app.state.participants.loc[pid_bid, "balance"] -= volume * app.state.ltp
                    app.state.participants.loc[pid_bid, "asset_balance"] += volume
                    app.state.participants.loc[pid_ask, "balance"] += volume * app.state.ltp
                    app.state.participants.loc[pid_ask, "asset_balance"] -= volume

                ask_id = app.state.ask_book.iloc[0]['id']
                bid_id = app.state.bid_book.iloc[0]['id']

                app.state.bid_book = app.state.bid_book.iloc[1:].reset_index(drop=True)

                return {"msg": f"""
                        Executed orders {bid_id} and
                        {ask_id} @ {app.state.ltp} and volume {volume} at time {app.state.current_time}
                """}

            elif app.state.bid_book.iloc[0]['volume'] > app.state.ask_book.iloc[0]['volume']:
                app.state.bid_book.at[0, 'volume'] -= app.state.ask_book.iloc[0]['volume']

                # update participants book
                async with app.state.participants_lock:
                    pid_bid = app.state.participants.index[
                        app.state.participants['id'] == app.state.bid_book.iloc[0]['pid']
                        ]
                    pid_ask = app.state.participants.index[
                        app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                        ]
                    volume = app.state.ask_book.iloc[0]['volume']
                    app.state.participants.loc[pid_bid, "balance"] -= volume * app.state.ltp
                    app.state.participants.loc[pid_bid, "asset_balance"] += volume
                    app.state.participants.loc[pid_ask, "balance"] += volume * app.state.ltp
                    app.state.participants.loc[pid_ask, "asset_balance"] -= volume

                ask_id = app.state.ask_book.iloc[0]['id']
                bid_id = app.state.bid_book.iloc[0]['id']

                app.state.ask_book = app.state.ask_book.iloc[1:].reset_index(drop=True)

                return {"msg": f"""
                        Executed orders {bid_id} and
                        {ask_id} @ {app.state.ltp} and volume {volume} at time {app.state.current_time}
                """}

            else:
                # equal volumes
                volume = app.state.ask_book.iloc[0]['volume']
                ask_id = app.state.ask_book.iloc[0]['id']
                bid_id = app.state.bid_book.iloc[0]['id']
                app.state.bid_book = app.state.bid_book.iloc[1:].reset_index(drop=True)
                app.state.ask_book = app.state.ask_book.iloc[1:].reset_index(drop=True)

                return {"msg": f"""
                        Executed orders {bid_id} and
                        {ask_id} @ {app.state.ltp} and volume {volume} at time {app.state.current_time}
                """}

@app.post("/place_order")
async def place_order(order: OrderRequest):

    if order.buy:
        async with app.state.ask_book_lock:
            while True:
                if order.volume == 0:
                    return {"msg": ""}
                if app.state.ask_book.empty:
                    # append buy order to bid book
                    async with app.state.bid_book_lock:
                        app.state.bid_book = pd.concat([app.state.bid_book, pd.DataFrame({
                            "price": [order.price],
                            "volume": [order.volume],
                            "time": [order.time],
                            "pid": [order.participant_id],
                            "id": [order.id]
                        })]).sort_values(['price', 'time'], ascending=[False, False])
                    return {"msg": ""}
                if order.price < app.state.ask_book.iloc[0]['price']:
                    # no matching trade possible
                    # append buy order to bid book
                    async with app.state.bid_book_lock:
                        app.state.bid_book = pd.concat([app.state.bid_book, pd.DataFrame({
                            "price": [order.price],
                            "volume": [order.volume],
                            "time": [order.time],
                            "pid": [order.participant_id],
                            "id": [order.id]
                        })]).sort_values(['price', 'time'], ascending=[False, False])
                    return {"msg": ""}
                if order.volume > app.state.ask_book.iloc[0]['volume']:

                    order.volume -= app.state.ask_book.iloc[0]['volume']

                    # update participants book
                    async with app.state.participants_lock:
                        pid_ask = app.state.participants.index[
                            app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                            ]
                        pid_bid = app.state.participants.index[
                            app.state.participants['id'] == order.participant_id
                            ]
                        
                        price = app.state.ask_book.iloc[0]['price']
                        volume = app.state.ask_book.iloc[0]['volume']

                        app.state.participants.loc[pid_bid, "balance"] -= volume * price
                        app.state.participants.loc[pid_bid, "asset_balance"] += volume
                        app.state.participants.loc[pid_ask, "balance"] += volume * price
                        app.state.participants.loc[pid_ask, "asset_balance"] -= volume

                    app.state.ask_book = app.state.ask_book.iloc[1:].reset_index(drop=True)

                    return {"msg": f"""
                            Executed orders {app.state.ask_book.iloc[0]['id']} and
                            {order.id} @ {price} and volume {volume} at time {app.state.current_time}
                    """}

                else:
                    app.state.ask_book.at[0, 'volume'] -= order.volume

                    # update participants book
                    async with app.state.participants_lock:
                        pid_ask = app.state.participants.index[
                            app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                            ]
                        pid_bid = app.state.participants.index[
                                app.state.participants['id'] == order.participant_id
                                ]
                        
                        price = app.state.ask_book.iloc[0]['price']
                        app.state.participants.loc[pid_bid, "balance"] -= order.volume * price
                        app.state.participants.loc[pid_bid, "asset_balance"] += order.volume
                        app.state.participants.loc[pid_ask, "balance"] += order.volume * price
                        app.state.participants.loc[pid_ask, "asset_balance"] -= order.volume

                    return {"msg": f"""
                            Executed orders {app.state.ask_book.iloc[0]['id']} and
                            {order.id} @ {price} and volume {order.volume} at time {app.state.current_time}
                    """}


    else: # sell order

        async with app.state.bid_book_lock:
            while True:
                if order.volume == 0:
                    return {"msg": ""}
                if app.state.bid_book.empty:
                    # append buy order to bid book
                    async with app.state.ask_book_lock:
                        app.state.ask_book = pd.concat([app.state.ask_book, pd.DataFrame({
                            "price": [order.price],
                            "volume": [order.volume],
                            "time": [order.time],
                            "pid": [order.participant_id],
                            "id": [order.id]
                        })]).sort_values(['price', 'time'], ascending=[True, True])
                    return {"msg": ""}
                if order.price < app.state.bid_book.iloc[0]['price']:
                    # no matching trade possible
                    # append buy order to bid book
                    async with app.state.ask_book_lock:
                        app.state.ask_book = pd.concat([app.state.ask_book, pd.DataFrame({
                            "price": [order.price],
                            "volume": [order.volume],
                            "time": [order.time],
                            "pid": [order.participant_id],
                            "id": [order.id]
                        })]).sort_values(['price', 'time'], ascending=[True, True])
                    return {"msg": ""}
                
                if order.volume > app.state.bid_book.iloc[0]['volume']:

                    order.volume -= app.state.bid_book.iloc[0]['volume']

                    # update participants book
                    async with app.state.participants_lock:
                        pid_ask = app.state.participants.index[
                            app.state.participants['id'] == order.participant_id
                            ]
                        pid_bid = app.state.participants.index[
                            app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                            ]
                        
                        volume = app.state.bid_book.iloc[0]['volume']
                        price = app.state.bid_book.iloc[0]['price']

                        app.state.participants.loc[pid_bid, "balance"] -= volume * price
                        app.state.participants.loc[pid_bid, "asset_balance"] += volume
                        app.state.participants.loc[pid_ask, "balance"] += volume * price
                        app.state.participants.loc[pid_ask, "asset_balance"] -= volume

                    app.state.bid_book = app.state.bid_book.iloc[1:].reset_index(drop=True)

                    return {"msg": f"""
                            Executed orders {app.state.ask_book.iloc[0]['id']} and
                            {order.id} @ {price} and volume {volume} at time {app.state.current_time}
                    """}

                else:
                    app.state.bid_book.at[0, 'volume'] -= order.volume

                    # update participants book
                    async with app.state.participants_lock:
                        pid_ask = app.state.participants.index[
                            app.state.participants['id'] == order.participant_id
                            ]
                        pid_bid = app.state.participants.index[
                                app.state.participants['id'] == app.state.ask_book.iloc[0]['pid']
                                ]
                        price = app.state.bid_book.iloc[0]['price']
                        app.state.participants.loc[pid_bid, "balance"] -= order.volume * price
                        app.state.participants.loc[pid_bid, "asset_balance"] += order.volume
                        app.state.participants.loc[pid_ask, "balance"] += order.volume * price
                        app.state.participants.loc[pid_ask, "asset_balance"] -= order.volume

                    return {"msg": f"""
                            Executed orders {app.state.ask_book.iloc[0]['id']} and
                            {order.id} @ {price} and volume {order.volume} at time {app.state.current_time}
                    """}


