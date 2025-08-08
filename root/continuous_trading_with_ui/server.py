
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
    price: Optional[float] = None

baseurl = "http://localhost:8000"


# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):

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
    app.state.highest_bid = None
    app.state.lowest_ask = None
    app.state.ltp = None # last traded price
    app.state.num_participants = 0
    app.state.num_orders_in_ob = 0
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


@app.post("/init_market")
async def init_market(market_init: MarketInitializer):
    try:
        async with app.state.time_lock:
            app.state.ltp = market_init.start_time
        async with app.state.open_price_lock:
            app.state.ltp = market_init.init_open_price

        app.state.open_time = market_init.open_time
        app.state.close_time = market_init.close_time
        app.state.progress_step = market_init.progress_step
        app.state.sleep_step = market_init.sleep_step
        app.state.ws_delay_step = market_init.ws_delay_step
        app.state.price_rounding_digits = market_init.price_rounding_digits
        

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
    return [int(x) for x in app.state.participants.iloc[arr]['id'].values]


@app.post("/place_order_before_market_open")
async def place_order_before_market_open(order: OrderRequest):

    price = order.price if order.price is not None else app.state.ltp

    if order.buy:

        if app.state.bid_book.empty:
            # place first order
            async with app.state.bid_book_lock:
                app.state.bid_book = pd.DataFrame({
                    "price": price,
                    "volume": order.volume,
                    "time": order.time
                })
        else:
            if price < app.state.bid_book.loc[0, "Price"]:
                async with app.state.bid_book_lock:
                    app.state.bid_book = pd.DataFrame({
                        "price": [price] + app.state.bid_book["Price"].values.tolist(),
                        "volume": [order.volume] + app.state.bid_book["volume"].values.tolist(),
                        "time": [order.time] + app.state.bid_book["time"].values.tolist(),
                    })

