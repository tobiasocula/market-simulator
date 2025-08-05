
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

from typing import Optional
from pydantic import BaseModel

class rpInput(BaseModel):
    amount: Optional[int] = None

class MarketInitializer(BaseModel):
    open_time: str
    close_time: str
    start_time: str

    progress_step: float
    sleep_step: float
    ws_delay_step: float

    init_open_price: float

    participant_init_balances: list[int]

class OrderRequest(BaseModel):
    volume: int
    buy: bool
    participant_id: int
    price: Optional[float] = None

baseurl = "http://localhost:8000"

async def start_market(app: FastAPI):
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

    app.state.open_time = None
    app.state.close_time = None
    app.state.start_time = None
    app.state.progress_step = None
    app.state.sleep_step = None
    app.state.ws_delay_step = None
    app.state.current_time = None
    app.state.participants = [] # dict with init_balance, balance, id
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
async def init_market(request: Request, market_init: MarketInitializer):
    try:
        async with app.state.order_book_lock, app.state.time_lock, app.state.ws_lock:

            request.app.state.open_time = market_init.open_time
            request.app.state.current_time = market_init.open_time
            request.app.state.current_price = market_init.init_open_price
            request.app.state.close_time = market_init.close_time
            request.app.state.start_time = market_init.start_time
            request.app.state.progress_step = market_init.progress_step
            request.app.state.sleep_step = market_init.sleep_step
            request.app.state.ws_delay_step = market_init.ws_delay_step

            last_id = 0
            for b in market_init.participant_init_balances:
                app.state.participants.append({
                    "init_balance": b,
                    "balance": b,
                    "id": last_id
                })
                last_id = last_id + 1
                app.state.num_participants += 1

            asyncio.create_task(start_market(app))
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
async def place_order(request: Request, order: OrderRequest):

    try:
        async with request.app.state.order_book_lock:
                
            ORDER_BOOK_COLUMNS = ['Time', 'Buy', 'Price', 'Volume', 'PartID']
            if app.state.order_book.empty:
                app.state.order_book = pd.DataFrame([
                    [
                    app.state.current_time,
                    0 if order.buy else 1,
                    order.price if order.price is not None else app.state.current_price,
                    order.volume,
                    order.participant_id
                    ]
                ], columns=ORDER_BOOK_COLUMNS)
            else:
                new_row = pd.DataFrame([[
                    app.state.current_time,
                    0 if order.buy else 1,
                    order.price if order.price is not None else app.state.current_price,
                    order.volume,
                    order.participant_id
                ]], columns=ORDER_BOOK_COLUMNS)
                app.state.order_book = pd.concat(
                    [app.state.order_book, new_row],
                    ignore_index=True
                )

            app.state.num_orders_in_ob += 1

            #print("New row added:", request.app.state.order_book.tail(1))


        return {"message": "placed order", "ok": True}

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

@app.post("/wait_for_ws_connection")
async def wait_for_ws_connection(request: Request):
    while not request.app.state.ws_connected.is_set():
        await asyncio.sleep(0.1)

@app.post("/random_participants")
async def random_participants(request: Request, inp: rpInput):
    assert request.app.state.num_participants >= 1, AssertionError()
    if inp.amount is None:
        amount = np.random.randint(1, request.app.state.num_participants+1)
    else:
        amount = min(inp.amount, request.app.state.num_participants)
    arr = np.random.randint(0, request.app.state.num_participants, amount)
    return {
        "ok": True,
        "content": [request.app.state.participants[a]["id"] for a in arr]
    }

@app.websocket("/ws/marketdata")
async def marketdata(websocket: WebSocket):
    await websocket.accept()
    try:
        async with websocket.app.state.ws_lock:
            websocket.app.state.ws_connected.set()
            print('set ws connected')
        while True:
            await websocket.send_json({
                "current_time": websocket.app.state.current_time,
                "order_book": websocket.app.state.order_book.to_json(),
                "current_price": websocket.app.state.current_price,
                "num_orders_in_ob": websocket.app.state.num_orders_in_ob,
            })
            await asyncio.sleep(websocket.app.state.ws_delay_step)
    except asyncio.CancelledError:
        print("Marketdata websocket handler cancelled")
        # Optionally close websocket connection explicitly
        await websocket.close()
        raise
    except Exception as e:
        print(f"Unexpected error in websocket handler: {e}")
        await websocket.close()