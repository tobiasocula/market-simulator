
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

    participant_init_balances: list[float]

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

            # assumes order_book is already sorted on price

            price = round(
                order.price, ndigits=app.state.price_rounding_digits
                ) if order.price is not None else round(
                    app.state.current_price, ndigits=app.state.price_rounding_digits
                )
            if app.state.order_book.empty:
                return
            
            if price < app.state.order_book.loc[0, "Price"]:
                if order.buy:
                    app.state.order_book = pd.DataFrame({
                        "Price": [price] + app.state.order_book["Price"].values.tolist(),
                        "BidVols": [[order.volume]] + app.state.order_book["BidVols"].values.tolist(),
                        "AskVols": [[]] + app.state.order_book["AskVols"].values.tolist(),
                        "BidOrderIDs": [[app.state.num_orders_in_ob]] + app.state.order_book["BidOrderIDs"].values.tolist(),
                        "AskOrderIDs": [[]] + app.state.order_book["AskOrderIDs"].values.tolist(),
                        "BidOwnerIDs": [[order.participant_id]] + app.state.order_book["BidOwnerIDs"].values.tolist(),
                        "AskOwnerIDs": [[]] + app.state.order_book["AskOwnerIDs"].values.tolist()
                    })
                else:
                    app.state.order_book = pd.DataFrame({
                        "Price": [price] + app.state.order_book["Price"].values.tolist(),
                        "AskVols": [[order.volume]] + app.state.order_book["AskVols"].values.tolist(),
                        "BidVols": [[]] + app.state.order_book["BidVols"].values.tolist(),
                        "AskOrderIDs": [[app.state.num_orders_in_ob]] + app.state.order_book["AskOrderIDs"].values.tolist(),
                        "BidOrderIDs": [[]] + app.state.order_book["BidOrderIDs"].values.tolist(),
                        "AskOwnerIDs": [[order.participant_id]] + app.state.order_book["AskOwnerIDs"].values.tolist(),
                        "BidOwnerIDs": [[]] + app.state.order_book["BidOwnerIDs"].values.tolist()
                    })

            elif price > app.state.order_book.loc[len(app.state.order_book)-1, "Price"]:
                if order.buy:
                    app.state.order_book = pd.DataFrame({
                        "Price": app.state.order_book["Price"].values.tolist() + [price],
                        "BidVols": app.state.order_book["BidVols"].values.tolist() + [[order.volume]],
                        "AskVols": app.state.order_book["AskVols"].values.tolist() + [[]],
                        "BidOrderIDs": app.state.order_book["BidOrderIDs"].values.tolist() + [[app.state.num_orders_in_ob]],
                        "AskOrderIDs": app.state.order_book["AskOrderIDs"].values.tolist() + [[]],
                        "BidOwnerIDs": app.state.order_book["BidOwnerIDs"].values.tolist() + [[order.participant_id]],
                        "AskOwnerIDs": app.state.order_book["AskOwnerIDs"].values.tolist() + [[]]
                    })
                else:
                    app.state.order_book = pd.DataFrame({
                        "Price": app.state.order_book["Price"].values.tolist() + [price],
                        "AskVols": app.state.order_book["AskVols"].values.tolist() + [[order.volume]],
                        "BidVols": app.state.order_book["BidVols"].values.tolist() + [[]],
                        "AskOrderIDs": app.state.order_book["AskOrderIDs"].values.tolist() + [[app.state.num_orders_in_ob]],
                        "BidOrderIDs": app.state.order_book["BidOrderIDs"].values.tolist() + [[]],
                        "AskOwnerIDs": app.state.order_book["AskOwnerIDs"].values.tolist() + [[order.participant_id]],
                        "BidOwnerIDs": app.state.order_book["BidOwnerIDs"].values.tolist() + [[]]
                    })

            else:

                # price belongs somewhere in the orderbook
                for idx, row in app.state.order_book.iterrows():

                    if price == row["Price"]:

                        if order.buy and len(app.state.order_book.loc[idx, "AskVols"]) > 0:

                            if order.volume >= app.state.order_book.loc[idx, "AskVols"][0]:

                                # modify balances of involved participants
                                async with app.state.participants_lock:
                                    ask_idx = app.state.participants.index[
                                        app.state.participants["id"] == app.state.order_book.loc[idx, "AskOwnerIDs"][0]
                                    ][0]

                                    app.state.participants.at[order.participant_id, "balance"] -= app.state.order_book.loc[idx, "AskVols"][0] * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[order.participant_id, "asset_balance"] += app.state.order_book.loc[idx, "AskVols"][0]

                                    app.state.participants.at[ask_idx, "balance"] += app.state.order_book.loc[idx, "AskVols"][0] * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[ask_idx, "asset_balance"] -= app.state.order_book.loc[idx, "AskVols"][0]

                                # delete values in ask-entries

                                idx_tbr_ask = [k for k,r in enumerate(
                                    app.state.order_book.loc[idx, "AskVols"])
                                    if r > 0
                                ]
                                new_askvols, new_ask_ownerids, new_ask_orderids = [], [], []
                                for j in idx_tbr_ask:
                                    new_askvols.append(app.state.order_book.loc[idx, "AskVols"][j])
                                    new_ask_ownerids.append(app.state.order_book.loc[idx, "AskOwnerIDs"][j])
                                    new_ask_orderids.append(app.state.order_book.loc[idx, "AskOrderIDs"][j])

                                app.state.order_book.at[idx, "AskVols"] = new_askvols
                                app.state.order_book.at[idx, "AskOrderIDs"] = new_ask_orderids
                                app.state.order_book.at[idx, "AskOwnerIDs"] = new_ask_ownerids


                        
                            else:
                                # modify balances of involved participants
                                async with app.state.participants_lock:
                                    ask_idx = app.state.participants.index[
                                        app.state.participants["id"] == app.state.order_book.loc[idx, "AskOwnerIDs"][0]
                                    ][0]

                                    app.state.participants.at[order.participant_id, "balance"] -= order.volume * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[order.participant_id, "asset_balance"] += order.volume

                                    app.state.participants.at[ask_idx, "balance"] += order.volume * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[ask_idx, "asset_balance"] -= order.volume

                                app.state.num_orders_in_ob += 1

                                return

                        elif not order.buy and len(app.state.order_book.loc[idx, "BidVols"]) > 0:

                            if order.volume >= app.state.order_book.loc[idx, "BidVols"][0]:

                                # modify balances of involved participants
                                async with app.state.participants_lock:
                                    
                                    bid_idx = app.state.participants.index[
                                        app.state.participants["id"] == app.state.order_book.loc[idx, "BidOwnerIDs"][0]
                                    ][0]

                                    app.state.participants.at[bid_idx, "balance"] -= app.state.order_book.loc[idx, "BidVols"][0] * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[bid_idx, "asset_balance"] += app.state.order_book.loc[idx, "BidVols"][0]

                                    app.state.participants.at[order.participant_id, "balance"] += app.state.order_book.loc[idx, "BidVols"][0] * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[order.participant_id, "asset_balance"] -= app.state.order_book.loc[idx, "BidVols"][0]

                                # delete values in ask-entries
                                idx_tbr_bid = [k for k,r in enumerate(
                                    app.state.order_book.loc[idx, "BidVols"])
                                    if r > 0
                                ]
                                assert (
                                    len(app.state.order_book.loc[idx, "BidVols"]) ==
                                    len(app.state.order_book.loc[idx, "BidOwnerIDs"]) ==
                                    len(app.state.order_book.loc[idx, "BidOrderIDs"])
                                ), AssertionError("Lengths failed:",
                                                len(app.state.order_book.loc[idx, "BidVols"]),
                                                len(app.state.order_book.loc[idx, "BidOwnerIDs"]),
                                                len(app.state.order_book.loc[idx, "BidOrderIDs"]))
                                new_bidvols, new_bid_ownerids, new_bid_orderids = [], [], []
                                for j in idx_tbr_bid:
                                    new_bidvols.append(app.state.order_book.loc[idx, "BidVols"][j])
                                    new_bid_ownerids.append(app.state.order_book.loc[idx, "BidOwnerIDs"][j])
                                    new_bid_orderids.append(app.state.order_book.loc[idx, "BidOrderIDs"][j])

                                app.state.order_book.at[idx, "BidVols"] = new_bidvols
                                app.state.order_book.at[idx, "BidOrderIDs"] = new_bid_orderids
                                app.state.order_book.at[idx, "BidOwnerIDs"] = new_bid_ownerids
                        
                            else:

                                # modify balances of involved participants
                                async with app.state.participants_lock:

                                    bid_idx = app.state.participants.index[
                                        app.state.participants["id"] == app.state.order_book.loc[idx, "BidOwnerIDs"][0]
                                    ][0]

                                    app.state.participants.at[bid_idx, "balance"] -= order.volume * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[bid_idx, "asset_balance"] += order.volume

                                    app.state.participants.at[order.participant_id, "balance"] += order.volume * app.state.order_book.loc[idx, 'Price']
                                    app.state.participants.at[order.participant_id, "asset_balance"] -= order.volume
                        
                        # no matching buy/sell order found
                        # insert order into stack

                        elif order.buy:
                            app.state.order_book.iloc[idx]["BidVols"].append(order.volume)
                            app.state.order_book.iloc[idx]["BidOwnerIDs"].append(order.participant_id)
                            app.state.order_book.iloc[idx]["BidOrderIDs"].append(app.state.num_orders_in_ob)
                        else:
                            app.state.order_book.iloc[idx]["AskVols"].append(order.volume)
                            app.state.order_book.iloc[idx]["AskOwnerIDs"].append(order.participant_id)
                            app.state.order_book.iloc[idx]["AskOrderIDs"].append(app.state.num_orders_in_ob)

                        app.state.num_orders_in_ob += 1

                        # recompute current price

                        return
                    
                    elif price < row["Price"]:

                        # insert
                        if order.buy:
                            app.state.order_book = pd.DataFrame({
                                "Price": (
                                    app.state.order_book.loc[:idx-1, "Price"].values.tolist()
                                    + [price] +
                                    app.state.order_book.loc[idx:, "Price"].values.tolist()
                                ),
                                "BidVols": (
                                    app.state.order_book.loc[:idx-1, "BidVols"].values.tolist()
                                    + [[order.volume]] +
                                    app.state.order_book.loc[idx:, "BidVols"].values.tolist()
                                ),
                                "AskVols": (
                                    app.state.order_book.loc[:idx-1, "AskVols"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "AskVols"].values.tolist()
                                ),
                                "BidOrderIDs": (
                                    app.state.order_book.loc[:idx-1, "BidOrderIDs"].values.tolist()
                                    + [[app.state.num_orders_in_ob]] +
                                    app.state.order_book.loc[idx:, "BidOrderIDs"].values.tolist()
                                ),
                                "AskOrderIDs": (
                                    app.state.order_book.loc[:idx-1, "AskOrderIDs"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "AskOrderIDs"].values.tolist()
                                ),
                                "BidOwnerIDs": (
                                    app.state.order_book.loc[:idx-1, "BidOwnerIDs"].values.tolist()
                                    + [[order.participant_id]] +
                                    app.state.order_book.loc[idx:, "BidOwnerIDs"].values.tolist()
                                ),
                                "AskOwnerIDs": (
                                    app.state.order_book.loc[:idx-1, "AskOwnerIDs"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "AskOwnerIDs"].values.tolist()
                                ),
                            })
                        else:
                            app.state.order_book = pd.DataFrame({
                                "Price": (
                                    app.state.order_book.loc[:idx-1, "Price"].values.tolist()
                                    + [price] +
                                    app.state.order_book.loc[idx:, "Price"].values.tolist()
                                ),
                                "BidVols": (
                                    app.state.order_book.loc[:idx-1, "BidVols"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "BidVols"].values.tolist()
                                ),
                                "AskVols": (
                                    app.state.order_book.loc[:idx-1, "AskVols"].values.tolist()
                                    + [[order.volume]] +
                                    app.state.order_book.loc[idx:, "AskVols"].values.tolist()
                                ),
                                "BidOwnerIDs": (
                                    app.state.order_book.loc[:idx-1, "BidOwnerIDs"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "BidOwnerIDs"].values.tolist()
                                ),
                                "AskOrderIDs": (
                                    app.state.order_book.loc[:idx-1, "AskOrderIDs"].values.tolist()
                                    + [[app.state.num_orders_in_ob]] +
                                    app.state.order_book.loc[idx:, "AskOrderIDs"].values.tolist()
                                ),
                                "BidOrderIDs": (
                                    app.state.order_book.loc[:idx-1, "BidOrderIDs"].values.tolist()
                                    + [[]] +
                                    app.state.order_book.loc[idx:, "BidOrderIDs"].values.tolist()
                                ),
                                "AskOwnerIDs": (
                                    app.state.order_book.loc[:idx-1, "AskOwnerIDs"].values.tolist()
                                    + [[order.participant_id]] +
                                    app.state.order_book.loc[idx:, "AskOwnerIDs"].values.tolist()
                                )
                            })

                        app.state.num_orders_in_ob += 1
                        # recompute cumvol and matched vol (to calculate open_price)
                        askcumvol = (
                            app.state.order_book['AskVols']
                                .apply(lambda x: sum(x))
                                .iloc[::-1]
                                .cumsum()
                                .iloc[::-1]
                            )
                        bidcumvol = (
                            app.state.order_book['BidVols']
                                .apply(lambda x: sum(x))
                                .cumsum()
                            )
                        matchedvol = np.array([askcumvol, bidcumvol]).min(axis=0)
                        
                        open_price = app.state.order_book['Price'][np.argmax(matchedvol)]
                        async with app.state.open_price_lock:
                            app.state.current_price = open_price
                        return
    except:
        raise

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
                        "BidOrderIDs": [[0]], # first order 
                        "AskOwnerIDs": [[]],
                        "BidOwnerIDs": [[order.participant_id]]
                    })
                else:
                    app.state.order_book = pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[order.volume]],
                        "BidVols": [[]],
                        "AskOrderIDs": [[0]], # first order 
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]]
                    })

                # new order added
                app.state.num_orders_in_ob += 1

                app.state.order_book = app.state.order_book.reset_index(drop=True)

                return

            else:
                
                for idx, row in app.state.order_book.iterrows():
                    if row["Price"] == price:
                        # insert order into stack
                        if order.buy:
                            app.state.order_book.iloc[idx]["BidOwnerIDs"].append(order.participant_id)
                            app.state.order_book.iloc[idx]["BidOrderIDs"].append(app.state.num_orders_in_ob)
                            app.state.order_book.iloc[idx]["BidVols"].append(order.volume)
                        else:
                            app.state.order_book.iloc[idx]["AskOwnerIDs"].append(order.participant_id)
                            app.state.order_book.iloc[idx]["AskOrderIDs"].append(app.state.num_orders_in_ob)
                            app.state.order_book.iloc[idx]["AskVols"].append(order.volume)

                        # new order added
                        app.state.num_orders_in_ob += 1

                        app.state.order_book = app.state.order_book.reset_index(drop=True)

                        return
                    
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
                    })])
                else:
                    app.state.order_book = pd.concat([app.state.order_book, pd.DataFrame({
                        "Price": [price],
                        "AskVols": [[order.volume]],
                        "BidVols": [[]],
                        "AskOrderIDs": [[app.state.num_orders_in_ob]], 
                        "BidOrderIDs": [[]],
                        "AskOwnerIDs": [[order.participant_id]],
                        "BidOwnerIDs": [[]],
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
    # not implemented yet
    pass

@app.post("/cancel_order")
async def modify_order(orderid: int):
    # not implemented yet
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
        async with app.state.order_book_lock, app.state.participants_lock:
            for idx, _ in app.state.order_book.iterrows():
            
                while (
                    len(app.state.order_book.loc[idx, "AskVols"]) > 0 and
                    len(app.state.order_book.loc[idx, "BidVols"]) > 0
                ):
                    
                    idx_tbr_bid = [k for k,r in enumerate(
                        app.state.order_book.loc[idx, "BidVols"])
                        if r > 0
                    ]
                    idx_tbr_ask = [k for k,r in enumerate(
                        app.state.order_book.loc[idx, "AskVols"])
                        if r > 0
                    ]
                    new_bidvols, new_bid_ownerids, new_bid_orderids = [], [], []
                    new_askvols, new_ask_ownerids, new_ask_orderids = [], [], []
                    for i in idx_tbr_bid:
                        new_bidvols.append(app.state.order_book.loc[idx, "BidVols"][i])
                        new_bid_ownerids.append(app.state.order_book.loc[idx, "BidOwnerIDs"][i])
                        new_bid_orderids.append(app.state.order_book.loc[idx, "BidOrderIDs"][i])
                    for j in idx_tbr_ask:
                        new_askvols.append(app.state.order_book.loc[idx, "AskVols"][j])
                        new_ask_ownerids.append(app.state.order_book.loc[idx, "AskOwnerIDs"][j])
                        new_ask_orderids.append(app.state.order_book.loc[idx, "AskOrderIDs"][j])

                    app.state.order_book.at[idx, "BidVols"] = new_bidvols
                    app.state.order_book.at[idx, "BidOrderIDs"] = new_bid_orderids
                    app.state.order_book.at[idx, "BidOwnerIDs"] = new_bid_ownerids

                    app.state.order_book.at[idx, "AskVols"] = new_askvols
                    app.state.order_book.at[idx, "AskOrderIDs"] = new_ask_orderids
                    app.state.order_book.at[idx, "AskOwnerIDs"] = new_ask_ownerids

                    if (
                        len(app.state.order_book.loc[idx, "BidVols"]) == 0 or
                        len(app.state.order_book.loc[idx, "AskVols"]) == 0
                    ):
                        break

                    if (
                        app.state.order_book.loc[idx, "BidVols"][0]
                        >=
                        app.state.order_book.loc[idx, "AskVols"][0]
                    ):
                        app.state.order_book.at[idx, "BidVols"][0] -= app.state.order_book.loc[idx, "AskVols"][0]

                        # modify participants book
                        ask_idx = app.state.participants.index[
                            app.state.participants["id"] == app.state.order_book.loc[idx, "AskOwnerIDs"][0]
                        ][0]
                        bid_idx = app.state.participants.index[
                            app.state.participants["id"] == app.state.order_book.loc[idx, "BidOwnerIDs"][0]
                        ][0]

                        app.state.participants.at[bid_idx, "balance"] -= app.state.order_book.loc[idx, "AskVols"][0] * app.state.order_book.loc[idx, 'Price']
                        app.state.participants.at[bid_idx, "asset_balance"] += app.state.order_book.loc[idx, "AskVols"][0]

                        app.state.participants.at[ask_idx, "balance"] += app.state.order_book.loc[idx, "AskVols"][0] * app.state.order_book.loc[idx, 'Price']
                        app.state.participants.at[ask_idx, "asset_balance"] -= app.state.order_book.loc[idx, "AskVols"][0]

                        app.state.order_book.at[idx, "AskVols"][0] = 0

                    else:
                        app.state.order_book.at[idx, "AskVols"][0] -= app.state.order_book.loc[idx, "BidVols"][0]

                        # modify participants book
                        ask_idx = app.state.participants.index[
                            app.state.participants["id"] == app.state.order_book.loc[idx, "AskOwnerIDs"][0]
                        ][0]
                        bid_idx = app.state.participants.index[
                            app.state.participants["id"] == app.state.order_book.loc[idx, "BidOwnerIDs"][0]
                        ][0]

                        app.state.participants.at[bid_idx, "balance"] -= app.state.order_book.loc[idx, "BidVols"][0] * app.state.order_book.loc[idx, 'Price']
                        app.state.participants.at[bid_idx, "asset_balance"] += app.state.order_book.loc[idx, "BidVols"][0]

                        app.state.participants.at[ask_idx, "balance"] += app.state.order_book.loc[idx, "BidVols"][0] * app.state.order_book.loc[idx, 'Price']
                        app.state.participants.at[ask_idx, "asset_balance"] -= app.state.order_book.loc[idx, "BidVols"][0]

                        app.state.order_book.at[idx, "BidVols"][0] = 0


            # recompute cumvol and matched vol (to calculate open price)
            askcumvol = (
                app.state.order_book['AskVols']
                    .apply(lambda x: sum(x))
                    .iloc[::-1]
                    .cumsum()
                    .iloc[::-1]
                )
            bidcumvol = (
                app.state.order_book['BidVols']
                    .apply(lambda x: sum(x))
                    .cumsum()
                )
            matchedvol = np.array([askcumvol, bidcumvol]).min(axis=0)
            
            open_price = app.state.order_book['Price'][np.argmax(matchedvol)]

        async with app.state.open_price_lock:
            app.state.current_price = open_price

        await asyncio.gather(*participants_updating)

        app.state.order_book = app.state.order_book.sort_values(by="Price")

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
