import httpx
import asyncio
from datetime import time, datetime, date, timedelta
import uvicorn
from .market import app, baseurl
from .classes import MarketParticipant, ContinuousMarket
import numpy as np
import websockets

async def subscribe_marketdata():
    uri = "ws://localhost:8000/ws/marketdata"
    async with websockets.connect(uri) as websocket:
        print("Connected to marketdata WebSocket")
        try:
            while True:
                message: dict = await websocket.recv()
                # message is json string
                print('received:'); print(message)

        except websockets.ConnectionClosed:
            print("WebSocket connection closed")

async def run_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def wait_for_server(timeout=10):
    import time
    start = time.time()
    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(baseurl + "/ping")
                if resp.status_code == 200:
                    return
        except httpx.RequestError:
            pass
        if time.time() - start > timeout:
            raise TimeoutError("Server did not start in time")
        await asyncio.sleep(0.5)

async def main():

    global start_time
    cur_time = start_time

    while cur_time < open_time:
        await asyncio.sleep(0.1)
        cur_time = (datetime.combine(date.today(), cur_time) + timedelta(minutes=1)).time()
        print('curtime:', cur_time)

    while cur_time < close_time:
        await asyncio.sleep(sleep_time)
        cur_time = (datetime.combine(date.today(), cur_time) + timedelta(seconds=progress_step)).time()
        print('curtime:', cur_time)

        # actual trading logic begins
        
        for p in market.random_participants():
            if np.random.uniform(0, 1) <= pct_market_orders:
                # make market order
                price = 10
            else:
                # make limit / stop order
                price = 10 + np.random.uniform(norm_price_dev, std_price_dev)
            # print('placing order...')
            asyncio.create_task(p.make_order(
                volume=int(np.random.normal(avg_vol_per_trade, std_vol_per_trade)),
                buy=np.random.uniform(0, 1) <= pct_buy_orders,
                curtime=cur_time,
                price=price
        ))


async def start():

    server_task = asyncio.create_task(run_server())
    await wait_for_server()  # wait for server ready first
    await market.initialize()
    asyncio.create_task(subscribe_marketdata())
    main_task = asyncio.create_task(main())
    await main_task

    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        print("Server stopped")
   

if __name__ == '__main__':

    """Set params"""
    open_hour = 9
    close_hour = 17
    n_participants = 100

    progress_step = 1 # sec
    sleep_time = 0.1 # sec

    init_balance = 10_000 # for every participant
    avg_trades_per_min = 20
    std_trades_per_min = 5
    avg_vol_per_trade = 10
    std_vol_per_trade = 2
    pct_market_orders = 0.5
    pct_buy_orders = 0.5
    
    norm_price_dev = 10
    std_price_dev = 2
    
    start_time = time(hour=8, minute=30)
    close_time = time(hour=close_hour)
    open_time = time(hour=open_hour)

    current_price = None
    current_time = None

    market = ContinuousMarket(open_time=open_time, close_time=close_time)
    for _ in range(n_participants):
        market.add_participant(MarketParticipant(init_balance=init_balance))

    asyncio.run(start())