
from fastapi import FastAPI, WebSocket, HTTPException
import pandas as pd
import logging
from contextlib import asynccontextmanager
import os
import asyncio
import traceback
from datetime import datetime, date, timedelta, time
from pydantic import BaseModel
from typing import Optional
import numpy as np
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create file handler
file_handler = logging.FileHandler("option_market_sim.log", mode='a')
file_handler.setLevel(logging.INFO)

# Create a common formatter and set it for both handlers
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Disable propagation to avoid duplicate logs
logger.propagate = False

baseurl = "http://localhost:8000"

class MarketInitializer(BaseModel):
    open_time: str
    close_time: str
    start_time: str
    progress_step: float
    sleep_step: float
    ws_delay_step: float

class AssetOrder(BaseModel):
    volume: int
    buy: bool
    participant_id: int
    price: Optional[float | int | None] = None
    time: str
    id: int


# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):

    # initialize app state

    # market state
    app.state.open_time = None
    app.state.close_time = None
    app.state.progress_step = None
    app.state.sleep_step = None
    app.state.ws_delay_step = None
    app.state.current_time = None

    app.state.ws_connected = asyncio.Event()

    # asset states
    app.state.bid_book = pd.DataFrame()
    app.state.ask_book = pd.DataFrame()
    app.state.ltp = None # last traded price
    app.state.last_asset_id = 0

    # option states
    app.state.books = [] # list of dataframes, each df representing

    # locks
    app.state.bid_book_lock = asyncio.Lock()
    app.state.ask_book_lock = asyncio.Lock()

    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/subscribe_data")
async def subscribe_data(websocket: WebSocket):
    await websocket.accept()

    while True:
        try:
            await websocket.send_json({
                "current_time": app.state.current_time,
                "option_books": [df.to_dict("records") for df in app.state.books],
                "bid_book": app.state.bid_book.to_dict("records"),
                "ask_book": app.state.ask_book.to_dict("records"),
                "ltp": app.state.ltp,
            })
            app.state.ws_connected.set()
            await asyncio.sleep(app.state.ws_delay_step)
        except asyncio.CancelledError:
            print("Marketdata websocket handler cancelled")
            await websocket.close()
            raise
        except Exception as e:
            print(f"Unexpected error in websocket handler: {e}")
            await websocket.close()
            raise

@app.get("/assert_connection")
async def assert_connection():
    while not app.state.ws_connected.is_set():
        await asyncio.sleep(0.1)

@app.post("/init_market")
async def init_market(market_init: MarketInitializer):

    app.state.open_time = market_init.open_time
    app.state.close_time = market_init.close_time
    app.state.current_time = market_init.start_time
    app.state.progress_step = market_init.progress_step
    app.state.sleep_step = market_init.sleep_step
    app.state.ws_delay_step = market_init.ws_delay_step

    # clear previous session data
    app.state.bid_book = pd.DataFrame()
    app.state.ask_book = pd.DataFrame()

    asyncio.create_task(market_clock(app))

async def market_clock(app: FastAPI):
    while True:
        # async with app.state.time_lock:
        app.state.current_time = (
            datetime.combine(date.today(), time.fromisoformat(app.state.current_time))
                            + timedelta(seconds=app.state.progress_step)
        ).time().isoformat()
        await asyncio.sleep(app.state.sleep_step)

@app.post("/asset_order")
async def asset_order(order: AssetOrder):
    
    price = order.price if order.price is not None else app.state.ltp

    if order.buy:

        if app.state.bid_book.empty:
            # place first order
            async with app.state.bid_book_lock:
                app.state.bid_book = pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "id": [order.id]
                })
        else:
            async with app.state.bid_book_lock:
                app.state.bid_book = pd.concat([app.state.bid_book, pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "id": [order.id]
                })]).sort_values(
                    ['price', 'time'], ascending=[False, False]
                    ).reset_index(drop=True)

    else:

        if app.state.ask_book.empty:
            # place first order
            async with app.state.ask_book_lock:
                app.state.ask_book = pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "id": [order.id]
                })
        else:
            async with app.state.ask_book_lock:
                app.state.ask_book = pd.concat([app.state.ask_book, pd.DataFrame({
                    "price": [price],
                    "volume": [order.volume],
                    "time": [order.time],
                    "id": [order.id]
                })]).sort_values(
                    ['price', 'time'], ascending=[True, True]
                    ).reset_index(drop=True)