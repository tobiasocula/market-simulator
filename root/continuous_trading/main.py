import httpx
import asyncio
from datetime import time, datetime, date, timedelta
import uvicorn
from .market import app
import numpy as np
import websockets
import json
import sys
import time as truetime
from .market import baseurl
    
async def subscribe_marketdata():
    uri = "ws://localhost:8000/ws/marketdata"
    async with websockets.connect(uri) as websocket:
        print("Connected to marketdata WebSocket")
        try:
            while True:
                message: dict = json.loads(await websocket.recv())
                yield message # send to client

        except websockets.ConnectionClosed:
            print("WebSocket connection closed")

async def run_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def initialize_market():
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(baseurl + "/init_market", json=market_submit)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('ok'):
                print("Market initialized successfully")
                return
            else:
                raise RuntimeError(f"Market init endpoint responded with failure: {result.get('message')}")
        else:
            raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")

async def wait_for_ws_connection():
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(baseurl + "/wait_for_ws_connection")
            if resp.status_code == 200:
                return
            else:
                raise
    except:
        raise


async def wait_for_server(timeout=10):
    start = truetime.time()
    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(baseurl + "/ping")
                if resp.status_code == 200:
                    return
        except httpx.RequestError:
            pass
        if truetime.time() - start > timeout:
            raise TimeoutError("Server did not start in time")
        await asyncio.sleep(0.5)

async def random_participant_ids(amount=None):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(baseurl + "/random_participants", 
                                    json={"amount": amount})
        if resp.status_code == 200:
            result = resp.json()
            if result.get('ok'):
                print("gotten random participants")
                return result.get("content")
            else:
                raise RuntimeError(f"Error: {result.get('message')}")
        else:
            raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")

async def data_feed():
    global market_ws_data
    async for market_data in subscribe_marketdata():
        market_ws_data = market_data.copy()
        print('time:', market_ws_data['current_time'])
        print('order book:', market_ws_data['order_book'])

async def send_order(p_id: int,
                     volume: int,
                     buy: bool,
                     price: float | int | None):
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(baseurl + "/place_order", 
                                    json={
                                        "volume": volume,
                                        "buy": buy,
                                        "participant_id": p_id,
                                        "price": price
                                    })
        if resp.status_code == 200:
            result = resp.json()
            if result.get('ok'):
                print("sent order")
                return result.get("content")
            else:
                raise RuntimeError(f"Error: {result.get('message')}")
        else:
            raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")


async def main_clock():
    
    while time.isoformat(market_ws_data["current_time"]) <= time.isoformat(close_time):

        # send orders to order book before market starts
        while time.isoformat(market_ws_data["current_time"]) <= time.isoformat(open_time):
        
            part_ids = await random_participant_ids()
            for p_id in part_ids:
                # make a random trade
                await send_order(
                    p_id=p_id,
                    volume=int(np.random.normal(avg_vol_per_trade, std_vol_per_trade)),
                    buy=np.random.uniform(0, 1) <= pct_buy_orders,
                    price=None if np.random.uniform(0, 1) <= pct_market_orders
                        else init_open_price + np.random.normal(-norm_price_dev, norm_price_dev)
                )
                # wait some time before next participant
                await asyncio.sleep(np.random.uniform(0, 0.2))
            
            # wait some time again before next batch of orders
            await asyncio.sleep(np.random.uniform(1, 3))

        

async def start():

    server_task = asyncio.create_task(run_server())
    
    await wait_for_server()
    await initialize_market()
    subscribe_task = asyncio.create_task(data_feed())
    await wait_for_ws_connection()
    print('MARKET WS CONNECTION ESTABLISHED')

    main_task = asyncio.create_task(main_clock())
    print('SCEDULED MAIN TASK')
    
    await main_task
    
    server_task.cancel()
    subscribe_task.cancel()

    try:
        await server_task
    except asyncio.CancelledError:
        print("Server stopped")
   

if __name__ == '__main__':

    """Set params"""
    start_time = "07:30:00"
    open_time = "08:00:00"
    close_time = "17:00:00"
    
    init_open_price = 100.0

    n_participants = 100

    progress_step = 1.0 # amount of sec to progress in the simulated market
    sleep_step = 1.0 # amount of sec to wait in each progress tick
    ws_delay_step = 1.0 # amount of sec between each websocket response

    init_balance = 10_000 # for every participant
    avg_trades_per_min = 20
    std_trades_per_min = 5
    avg_vol_per_trade = 10
    std_vol_per_trade = 2
    pct_market_orders = 0.5
    pct_buy_orders = 0.5
    
    norm_price_dev = 10

    # data we get from market websocket
    market_ws_data = None

    market_submit = {
        "open_time": open_time,
        "close_time": close_time,
        "start_time": start_time,
        "progress_step": progress_step,
        "sleep_step": sleep_step,
        "ws_delay_step": ws_delay_step,
        "init_open_price": init_open_price,
        "participant_init_balances": [init_balance for _ in range(n_participants)]
    }


    asyncio.run(start())