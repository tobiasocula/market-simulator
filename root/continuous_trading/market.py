
from fastapi import FastAPI, WebSocket, Request, HTTPException
import pandas as pd
from contextlib import asynccontextmanager
from multiprocessing import Pool
import os
import asyncio
import traceback
from .classes import ContinuousMarket, Order, baseurl
"""
price-time priority
"""





# define the lifespan of the app
@asynccontextmanager
async def lifespan(app: FastAPI):
    global worker_pool

    # Startup: create multiprocessing pool
    worker_pool = Pool(processes=os.cpu_count())

    app.state.market_lock = asyncio.Lock()
    app.state.market = None

    yield # Application starts serving requests here

    # Shutdown: remove multiprocessing pool
    worker_pool.close()
    worker_pool.join()
    print("Worker pool closed")

app = FastAPI(lifespan=lifespan) # lifespan is an async context manager



@app.post("/init_market")
async def init_market(request: Request, market: ContinuousMarket):
    try:
        if request.app.state.market is not None:
            return {"message": "cannot modify market again", "ok": False}
        async with request.app.state.market_lock:
            market._order_book = pd.DataFrame(columns=['Time', 'Buy', 'Price', 'Volume', 'PartID'])  # ← add this
            request.app.state.market = market
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
async def place_order(request: Request, order: Order):

    try:
        async with request.app.state.market_lock:
            assert hasattr(request.app.state.market, '_order_book'), AssertionError("no attr ob")
            print(request.app.state.market._order_book)
            #await asyncio.sleep(5)
            if request.app.state.market._order_book.empty:
                print('DATA:')
                print([
                    [
                    order.time,
                    0 if order.side == "buy" else 1,
                    order.price,
                    order.volume,
                    order.participant_id
                    ]
                ])
                ORDER_BOOK_COLUMNS = ['Time', 'Buy', 'Price', 'Volume', 'PartID']
                
                request.app.state.market._order_book = pd.DataFrame([
                    [
                    order.time,
                    0 if order.side == "buy" else 1,
                    order.price,
                    order.volume,
                    order.participant_id
                    ]
                ], columns=ORDER_BOOK_COLUMNS)
                print('MODIFIED DF')
            else:
                new_row = pd.DataFrame([[
                order.time,
                0 if order.side == "buy" else 1,
                order.price,
                order.volume,
                order.participant_id
            ]], columns=ORDER_BOOK_COLUMNS)
                request.app.state.market._order_book = pd.concat(
                    [request.app.state.market._order_book, new_row],
                    ignore_index=True
                )

            print("New row added:", request.app.state.market._order_book.tail(1))


        return {"message": "placed order"}

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

@app.get("/get_current_price")
async def get_current_price(request: Request):
    return {"result": request.app.market.current_price}

@app.websocket("/ws/marketdata")
async def marketdata(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Access shared state: use websocket.app.state
        cp = websocket.app.state.market.current_price
        ob = websocket.app.state.market.order_book_json()
        await websocket.send_json({"current_price": cp, "order_book": ob})
        await asyncio.sleep(1)  # to avoid tight loop