
import './App.css'
import { useState } from 'react';

const BASEURL = "http://localhost:8000";


// python asyncio.Event() equivalent in javascript
class AsyncEvent {
  constructor() {
    this._promise = null;
    this._resolve = null;
    this._isSet = false;
  }

  wait() {
    if (this._isSet) {
      this._isSet = false;  // reset
      return Promise.resolve();
    }
    if (!this._promise) {
      this._promise = new Promise(resolve => {
        this._resolve = resolve;
      });
    }
    return this._promise;
  }

  set() {
    if (this._resolve) {
      this._resolve();
      this._promise = null;
      this._resolve = null;
    } else {
      this._isSet = true;
    }
  }

  clear() {
    this._isSet = false;
  }
}


function App() {

  const [inSim, setInSim] = useState(false);
  const [marketSettings, setMarketSettings] = useState({
      open_time: "08:00:00",
      close_time: "12:00:00",
      start_time: "07:50:00",
      progress_step: 6.0,
      sleep_step: 0.1,
      ws_delay_step: 0.1,
      init_open_price: 100.0,
      participant_init_balance: 10_000.0,
      price_rounding_digits: 1,
      num_participants: 100
  });
  const [tradeSettings, setTradeSettings] = useState({
    pctOfAgressiveOrders: 0.30,
    
    
  })
  const [streamedData, setStreamedData] = useState({
    orderBook: null,
    currentTime: null,
    participantData: null,
    numOrdersInOB: null,
    currentPrice: null
  })


function subscribeMarketData() {
  const uri = "ws://localhost:8000/ws/marketdata";
  const socket = new WebSocket(uri);

  socket.onopen = () => {
    console.log("Connected to marketdata WebSocket");
  };

  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      // Pass the parsed message to caller’s callback handler
      setStreamedData({
        orderBook: message.order_book,
        currentTime: message.current_time,
        participantData: message.participants,
        numOrdersInOB: message.num_orders_in_ob,
        currentPrice: message.current_price
      });
    } catch (err) {
      console.error("Error parsing WebSocket message:", err);
    }
  };

  socket.onclose = (event) => {
    if (event.wasClean) {
      console.log(`WebSocket closed cleanly, code=${event.code}, reason=${event.reason}`);
    } else {
      console.warn('WebSocket connection closed unexpectedly');
    }
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  // for being able to close socket later
  return socket;
}

async function beforeMarketTradeCycle() {
  while (true) {
    // get some random participants
    const participantResponse = await fetch(`${BASEURL}/random_participants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        "amount": null,
        "amount_rnd_lower": 3,
        "amount_rnd_upper": 10
      })
    });
    if (participantResponse.status !== 200) {
      throw new Error();
    }
    const parts = await participantResponse.json();
  }
}

async function mainCycle() {

  const marketWsDataUpdated = new AsyncEvent();

  if (Object.values(streamedData).some((e) => e === null)) {
    throw new Error("in trade cycle: some values are null");
  }

  const currentTime = new Date(`1970-01-01T${streamedData.currentTime}Z`);
  const openTime = new Date(`1970-01-01T${openTime}Z`);

  // before market open cycle
  while (currentTime < openTime) {

    marketWsDataUpdated.clear();
    await marketWsDataUpdated.wait();

    const befMarketOpen = beforeMarketTradeCycle();

  }

}
  
async function startSimulation() {

  // initialize market
  // sets market parameters and sets main time clock
  const initMarketResp = await fetch(`${BASEURL}/init_market`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(marketSettings)
          });
  if (initMarketResp.status !== 200) {
    return
  }
  setInSim(true);

  // activate live streaming of market data
  const ws = subscribeMarketData();

  // wait for websocket messages to be able to go through
  const waitWSResponse = await fetch(`${BASEURL}/wait_for_ws_connection`);
  if (waitWSResponse.status !== 200) {
    return
  }

}

  return (
    <>
      <button className='start-simulation' onClick={startSimulation}>Start</button>
      <button className='end-simulation' onClick={endSimulation}>Start</button>
    </>
  )
}

export default App
