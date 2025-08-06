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

client = httpx.AsyncClient(timeout=30)
    
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
        resp = await client.get(baseurl + "/wait_for_ws_connection")
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
            resp = await client.get(baseurl + "/ping")
            if resp.status_code == 200:
                return
        except httpx.RequestError:
            pass
        if truetime.time() - start > timeout:
            raise TimeoutError("Server did not start in time")
        await asyncio.sleep(0.5)

async def random_participant_ids(amount=None, l=None, u=None):
    resp = await client.post(baseurl + "/random_participants", 
                                json={"amount": amount, "amount_rnd_lower": l, "amount_rnd_upper": u})
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

        # setting the event wakes up any coroutine waiting for an update
        market_ws_data_updated.set()

async def send_order(p_id: int,
                     volume: int,
                     buy: bool,
                     price: float | int | None,
                     market_open: bool = True):
    
    if market_open:
        try:
            resp = await client.post(baseurl + "/place_order", 
                                        json={
                                            "volume": volume,
                                            "buy": buy,
                                            "participant_id": p_id,
                                            "price": price
                                        })
        except:
            print('FAILED TO SEND MARKET AT OPEN')
    else:
        try:
            resp = await client.post(baseurl + "/place_order_bef_mo", 
                                        json={
                                            "volume": volume,
                                            "buy": buy,
                                            "participant_id": p_id,
                                            "price": price
                                        })
        except:
            print('FAILED TO SEND ORDER BEFORE OPEN')
        
    if resp.status_code == 200:
        result = resp.json()
        if result.get('ok'):
            print("sent order")
            return result.get("content")
        else:
            raise RuntimeError(f"Error: {result.get('message')}")
    else:
        raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")

async def at_open():
    resp = await client.get(baseurl + "/at_open")
    if resp.status_code == 200:
        result = resp.json()
        if result.get('ok'):
            print("matched orders")
            return
        else:
            raise RuntimeError(f"Error: {result.get('message')}")
    else:
        raise RuntimeError(f"Unexpected status code {resp.status_code}: {resp}")

async def trade_cycle(market_open=True):
    iteration = 0
    while True:
        print(f"Starting trade_cycle iteration {iteration}")
    
        part_ids = await random_participant_ids(l=5, u=10)
        print(f"PART IDS ({iteration}): {part_ids}")
        tasks = []
        for p_id in part_ids:
            tasks.append(asyncio.create_task(send_order(
                p_id=p_id,
                volume=int(np.random.normal(avg_vol_per_trade, std_vol_per_trade)),
                buy=np.random.uniform(0, 1) <= pct_buy_orders,
                price=None if np.random.uniform(0, 1) <= pct_market_orders
                    else init_open_price + np.random.normal(0, norm_price_dev),
                market_open=market_open
            )))
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"Completed sending orders for iteration {iteration}")
        iteration += 1

        await asyncio.sleep(np.random.uniform(1, 2))
        

    

async def main_clock():

    bef_market_open = asyncio.create_task(trade_cycle(market_open=False))
    while True:

        await market_ws_data_updated.wait()
        market_ws_data_updated.clear()
        current_time_obj = datetime.strptime(market_ws_data["current_time"], "%H:%M:%S").time()
        open_time_obj = datetime.strptime(open_time, "%H:%M:%S").time()

        print(f"Current Time: {current_time_obj}")
        #print('order book:'); print(market_ws_data['order_book'])

        if current_time_obj > open_time_obj:
            print("Breaking loop - market is open now!")
            bef_market_open.cancel()
            break

    # determine open price
    await at_open()
    await market_ws_data_updated.wait()
    print('order book at market open:'); print(market_ws_data['order_book'])

    aft_market_open = asyncio.create_task(trade_cycle())
    while True:

        await market_ws_data_updated.wait()
        market_ws_data_updated.clear()
        current_time_obj = datetime.strptime(market_ws_data["current_time"], "%H:%M:%S").time()
        close_time_obj = datetime.strptime(open_time, "%H:%M:%S").time()

        print(f"Current Time: {current_time_obj}")

        if current_time_obj > close_time_obj:
            print("Breaking loop - market is closed")
            aft_market_open.cancel()
            break

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
    start_time = "07:40:00"
    open_time = "08:00:00"
    close_time = "17:00:00"
    
    init_open_price = 100.0

    n_participants = 100

    max_price_dev = 0.01 # *100 pct, max open price deviation from last price

    progress_step = 6.0 # amount of sec to progress in the simulated market
    sleep_step = 0.1 # amount of sec to wait in each progress tick
    ws_delay_step = 0.1 # amount of sec between each websocket response

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
    market_ws_data_updated = asyncio.Event()

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