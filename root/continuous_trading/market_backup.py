
from fastapi import FastAPI, WebSocket, Request, HTTPException
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
from concurrent.futures import ProcessPoolExecutor
from math import ceil

from typing import Optional
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

    participant_init_balances: list[int]

    price_rounding_digits: int

class OrderRequest(BaseModel):
    volume: int
    buy: bool
    participant_id: int
    price: Optional[float] = None

baseurl = "http://localhost:8000"

async def market_clock(app: FastAPI):
    while True:
        async with app.state.time_lock:
            app.state.current_time = (
                datetime.combine(date.today(), time.fromisoformat(app.state.current_time))
                                + timedelta(seconds=app.state.progress_step)
            ).time().isoformat()
        await asyncio.sleep(app.state.sleep_step)


# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_pool

    # Startup: create multiprocessing pool
    worker_pool = Pool(processes=os.cpu_count())

    app.state.order_book_lock = asyncio.Lock()
    app.state.time_lock = asyncio.Lock()
    app.state.ws_lock = asyncio.Lock()
    app.state.open_price_lock = asyncio.Lock()
    app.state.participants_lock = asyncio.Lock()

    app.state.open_time = None
    app.state.close_time = None
    app.state.progress_step = None
    app.state.sleep_step = None
    app.state.ws_delay_step = None
    app.state.current_time = None
    app.state.participants = None
    app.state.order_book = pd.DataFrame()
    app.state.current_price = None
    app.state.num_participants = 0
    app.state.num_orders_in_ob = 0
    app.state.ws_connected = asyncio.Event()

    yield # Application starts serving requests here

    # Shutdown: remove multiprocessing pool
    worker_pool.close()
    worker_pool.join()
    print("Worker pool closed")

app = FastAPI(lifespan=lifespan) # lifespan is an async context manager

@app.post("/init_market")
async def init_market(market_init: MarketInitializer):
    try:
        async with app.state.time_lock:
            app.state.current_time = market_init.start_time
        async with app.state.open_price_lock:
            app.state.current_price = market_init.init_open_price

        app.state.open_time = market_init.open_time
        app.state.close_time = market_init.close_time
        app.state.progress_step = market_init.progress_step
        app.state.sleep_step = market_init.sleep_step
        app.state.ws_delay_step = market_init.ws_delay_step
        app.state.price_rounding_digits = market_init.price_rounding_digits

        npart = len(market_init.participant_init_balances)
        data = {
            "init_balance": market_init.participant_init_balances,
            "balance": market_init.participant_init_balances,
            "id": [i for i in range(npart)],
            "asset_balance": 0
        }
        async with app.state.participants_lock:
            app.state.participants = pd.DataFrame(data)
            app.state.num_participants = npart
            
        asyncio.create_task(market_clock(app))
        return {"message": "Market initialized", "ok": True}
    except Exception as e:
        print("Error in /init_market:")
        traceback.print_exc()
        # Optionally send back error details for debugging (not for production)
        raise HTTPException(status_code=500, detail=f"Server error: {e}")


@app.get("/ping")
def ping():
    return {"message": "ok"}


@app.post("/place_order")
async def place_order(order: OrderRequest):
    try:
        async with app.state.order_book_lock:

            price = round(
                order.price, ndigits=app.state.price_rounding_digits
                ) if order.price is not None else round(
                    app.state.current_price, ndigits=app.state.price_rounding_digits
                )
            if app.state.order_book.empty:
                pass
            else:
                if order.buy:
                    for idx, row in app.state.order_book.iterrows():
                        if row["Price"] == price:
                            
                            if row["AskVol"] > 0:
                                # execute trade
                                # compare first occurence in askvols to order volume
                                if row["AskVols"][0] > order.volume:
                                    row["AskVols"][0] -= order.volume
                                    # update participant states
                                else:
                                    row["AskVols"][0] = 0
                                    # update participant states
                            else:
                                # append buy order to buys
                                row["BidVols"].append(order.volume)
                                row["BidOrderIDs"].append(app.state.num_orders_in_ob)
                                row["BidVol"] += order.volume
                                row["BidOwnerIDs"].append(order.participant_id)

                                app.state.num_orders_in_ob += 1

                            return

                    # no price found -> append new order
                    app.state.order_book = pd.concat([app.state.order_book, pd.DataFrame({
                        "Price": [price],
                        "AskVol": [0.0],
                        "BidVol": [order.volume],
                        "AskOrderIDs": [[app.state.num_orders_in_ob]],
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]],
                        "MatchedVol": [0.0]
                    })])

                    app.state.num_orders_in_ob += 1

                else: # sell order

                    for idx, row in app.state.order_book.iterrows():
                        if row["Price"] == price:
                            
                            if row["BidVol"] > 0:
                                # execute trade
                                # compare first occurence in askvols to order volume
                                if row["BidVols"][0] > order.volume:
                                    row["BidVols"][0] -= order.volume
                                    # update participant states
                                else:
                                    row["BidVols"][0] = 0
                                    # update participant states
                            else:
                                # append sell order to buys
                                row["AskVols"].append(order.volume)
                                row["AskOrderIDs"].append(app.state.num_orders_in_ob)
                                row["AskVol"] += order.volume
                                row["AskOwnerIDs"].append(order.participant_id)
                                
                                app.state.num_orders_in_ob += 1

                            return

                    # no price found -> append new order
                    app.state.order_book = pd.concat([app.state.order_book, pd.DataFrame({
                        "Price": [price],
                        "AskVol": [order.volume],
                        "BidVol": [0.0],
                        "AskOrderIDs": [[app.state.num_orders_in_ob]],
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]],
                        "MatchedVol": [0.0]
                    })])

                    app.state.num_orders_in_ob += 1

    except:
        raise

async def participants(pid_bid: int,
                       pid_ask: int,
                       vol: int,
                       price: float):

    print(f"participants() start: bid={pid_bid}, ask={pid_ask}, vol={vol}, price={price}")

    async with app.state.participants_lock:
        print(f"participants() acquired lock: bid={pid_bid}, ask={pid_ask}")
        app.state.participants.loc[
            app.state.participants["id"] == pid_bid, ["balance", "asset_balance"]
        ] += [-vol * price, vol]
        app.state.participants.loc[
            app.state.participants["id"] == pid_ask, ["balance", "asset_balance"]
        ] += [vol * price, -vol]
        print(f"participants() updated balances: bid={pid_bid}, ask={pid_ask}")
    print(f"participants() end: bid={pid_bid}, ask={pid_ask}")

@app.post("/place_order_bef_mo")
async def place_order_bef_mo(order: OrderRequest):

    try:
        async with app.state.order_book_lock:

            price = round(
                order.price, ndigits=app.state.price_rounding_digits
                ) if order.price is not None else round(
                    app.state.current_price, ndigits=app.state.price_rounding_digits
                )
            if app.state.order_book.empty:
                if order.buy:
                    app.state.order_book = pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[]],
                        "BidVols": [[order.volume]],
                        "AskOrderIDs": [[]],
                        "BidOrderIDs": [[0]],
                        "AskOwnerIDs": [[]],
                        "BidOwnerIDs": [[order.participant_id]],
                        "MatchedVol": [0.0]
                    })
                else:
                    app.state.order_book = pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[order.volume]],
                        "BidVols": [[]],
                        "AskOrderIDs": [[0]], # first order 
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]],
                        "MatchedVol": [0.0]
                    })

            else:
                
                for idx, row in app.state.order_book.iterrows():
                    if row["Price"] == price:
                        # insert order into stack
                        if order.buy:
                            row["BidOwnerIDs"].append(order.participant_id)
                            row["BidOrderIDs"].append(app.state.num_orders_in_ob)
                            row["BidVols"].append(order.volume)
                        else:
                            row["AskOwnerIDs"].append(order.participant_id)
                            row["AskOrderIDs"].append(app.state.num_orders_in_ob)
                            row["AskVols"].append(order.volume)
                    
                # outside for-loop: no price found
                # append order manually
                if order.buy:
                    app.state.order_book = pd.concat([app.state.order_book, pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[]],
                        "BidVols": [[order.volume]],
                        "AskOrderIDs": [[]],
                        "BidOrderIDs": [[app.state.num_orders_in_ob]],
                        "AskOwnerIDs": [[]],
                        "BidOwnerIDs": [[order.participant_id]],
                        "MatchedVol": [0.0]
                    })])
                else:
                    app.state.order_book = pd.concat([app.state.order_book, pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[order.volume]],
                        "BidVols": [[0.0]],
                        "AskOrderIDs": [[app.state.num_orders_in_ob]], 
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]],
                        "MatchedVol": [0.0]
                    })])

                app.state.order_book = app.state.order_book.reset_index(drop=True)
                #app.state.order_book = app.state.order_book.sort_values(by='Price', ascending=True)

            # new order added
            app.state.num_orders_in_ob += 1

            return

    except Exception as e:
        print(f"Exception in place_order: {e}")
        traceback.print_exc()
        raise


@app.post("/modify_order")
async def modify_order(orderid: int):
    pass

@app.post("/cancel_order")
async def modify_order(orderid: int):
    pass

@app.get("/wait_for_ws_connection")
async def wait_for_ws_connection():
    while not app.state.ws_connected.is_set():
        await asyncio.sleep(0.1)

@app.post("/random_participants")
async def random_participants(inp: rpInput):
    assert app.state.num_participants >= 1, AssertionError()
    if inp.amount is None:
        amount = np.random.randint(1, app.state.num_participants+1)
    elif inp.amount_rnd_lower is not None and inp.amount_rnd_upper is not None:
        amount = np.random.randint(inp.amount_rnd_lower, inp.amount_rnd_upper+1)
    else:
        amount = min(inp.amount, app.state.num_participants)
    arr = np.random.randint(0, app.state.num_participants, amount)
    return {
        "ok": True,
        "content": [int(x) for x in app.state.participants.iloc[arr]['id'].values]
    }



@app.get("/at_open")
async def at_open():

    # fill orders
    participants_updating = []
    try:
        async with app.state.order_book_lock:
            for idx, row in app.state.order_book.iterrows():
            
                while sum(row["BidVols"]) > 0 and sum(row["AskVols"]) > 0:

                    row["BidVols"] = [el for el in row["BidVols"] if el > 0]
                    row["BidOrderIDs"] = [row["BidOrderIDs"][k] for k,r in enumerate(row["BidVols"]) if r > 0]
                    row["BidOwnerIDs"] = [row["BidOwnerIDs"][k] for k,r in enumerate(row["BidVols"]) if r > 0]

                    row["AskVols"] = [el for el in row["AskVols"] if el > 0]
                    row["AskOrderIDs"] = [row["AskOrderIDs"][k] for k,r in enumerate(row["AskVols"]) if r > 0]
                    row["AskOwnerIDs"] = [row["AskOwnerIDs"][k] for k,r in enumerate(row["AskVols"]) if r > 0]

                    if not row["BidVols"] or not row["AskVols"]:
                        break

                    if row["BidVols"][0] >= row["AskVols"][0]:
                        row["BidVols"][0] -= row["AskVols"][0]

                        participants_updating.append(asyncio.create_task(participants(
                                pid_bid=row["BidOwnerIDs"][0],
                                pid_ask=row["AskOwnerIDs"][0],
                                vol=row["AskVols"][0],
                                price=row["Price"]
                        )))
                        row["AskVols"][0] = 0

                    else:
                        row["AskVols"][0] -= row["BidVols"][0]

                        participants_updating.append(asyncio.create_task(participants(
                                pid_bid=row["BidOwnerIDs"][0],
                                pid_ask=row["AskOwnerIDs"][0],
                                vol=row["BidVols"][0],
                                price=row["Price"]
                        )))
                        row["BidVols"][0] = 0

            # recompute cumvol and matched vol
            app.state.order_book['AskCumVol'] = (
                                app.state.order_book['AskVols']
                                    .apply(lambda x: sum(x))
                                    .iloc[::-1]
                                    .cumsum()
                                    .iloc[::-1]
                                )
            app.state.order_book['BidCumVol'] = (
                                app.state.order_book['BidVols']
                                    .apply(lambda x: sum(x))
                                    .cumsum()
                                )
            app.state.order_book["MatchedVol"] = (
                app.state.order_book[["AskCumVol", "BidCumVol"]]
                .values.min(axis=1)
            )
            
            open_price = app.state.order_book['Price'][
                np.argmax(app.state.order_book['MatchedVol'].values)
                ]

        async with app.state.open_price_lock:
            app.state.current_price = open_price

        print('CHECKPOINT1')

        await asyncio.gather(*participants_updating)
        print('CHECKPOINT2')
        return

    except Exception as e:
        print('exception:', e)
        raise

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
                "order_book": app.state.order_book.to_json(),
                "current_price": app.state.current_price,
                "num_orders_in_ob": app.state.num_orders_in_ob,
                "participants": app.state.participants.to_json()
            })
            await asyncio.sleep(app.state.ws_delay_step)
    except asyncio.CancelledError:
        print("Marketdata websocket handler cancelled")
        # Optionally close websocket connection explicitly
        await websocket.close()
        raise
    except Exception as e:
        print(f"Unexpected error in websocket handler: {e}")
        await websocket.close()
