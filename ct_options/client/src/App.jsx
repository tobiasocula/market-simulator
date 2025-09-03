
import './App.css'
import { useEffect, useState, useRef } from 'react'


function OrderBookTable({ orders, orderMaxLength }) {

  const f = () => {
    if (orders) {
      if (orders.length > orderMaxLength) {
        return orders.slice(0, orderMaxLength);
      } else {
        const r = [];
        [...Array(orderMaxLength - orders.length)].forEach(i => r.push({
          price: "", volume: "", time: ""
        }));
        return orders.concat(r);
      }
  } else {
    const r = [];
    [...Array(orderMaxLength)].forEach(i => r.push({
      price: "", volume: "", time: ""
    }));
    return r;
  }
}
return (
    <div className='table-div' style={{
      display: 'flex', justifyContent: 'center'
    }}>
    <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace' }}>
      <thead>
        <tr style={{ borderBottom: '1px solid #444' }}>
          <th style={{ textAlign: 'right', padding: '4px' }}>Price</th>
          <th style={{ textAlign: 'right', padding: '4px' }}>Volume</th>
          <th style={{ textAlign: 'center', padding: '4px' }}>Time</th>
        </tr>
      </thead>
      <tbody>
        {f(orders).map(({ price, volume, time }, idx) => (
          <tr key={idx} style={{ borderBottom: '1px solid #222' }}>
            <td style={{ textAlign: 'right', padding: '4px' }}>{price !== "" ? price : "\u00A0"}</td>
            <td style={{ textAlign: 'right', padding: '4px' }}>{volume !== "" ? volume : "\u00A0"}</td>
            <td style={{ textAlign: 'center', padding: '4px' }}>{time !== "" ? time : "\u00A0"}</td>
          </tr>
        ))
        }
      </tbody>
    </table>
    </div>
  );
}

function App() {

  const [readyToRun, setReadyToRun] = useState(false);

  async function startTradingCycle() {
    console.log('starting trade cycle');
    console.log({assetdata: assetSimData,
        sleep_step: initMarketParams.sleep_step,
        optiondata: optionSimData});
    const initMarketResponse = await fetch(`${TRADINGENGINE_URL}/init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assetdata: assetSimData,
        sleep_step: initMarketParams.sleep_step,
      optiondata: optionSimData
    })
    });
    if (initMarketResponse.status !== 200) {
      throw new Error('failed the init market', initMarketResponse.status);
    }
  }

  useEffect(() => {
  if (readyToRun) {
    // data has come in, market initialized, etc
    // start trading cycle
    startTradingCycle();

  }
}, [readyToRun]);

  const [initMarketParams, setInitMarketParams] = useState({
        open_time: "08:00:00",
        close_time: "12:00:00",
        start_time: "07:30:00",
        progress_step: 6.0,
        sleep_step: 0.1,
        ws_delay_step: 0.1
  });

  const [optionSim, setOptionSim] = useState(true);

  const [assetSimData, setAssetSimData] = useState({
    init_open_price: 100.0,
    init_vola: 0.3,
    kappa: 0.5,
    theta: 0.07,
    xi: 0.03,
    mu: 0.8,
    rho: 0.5,
    dt: 1/365
  });

  const streamDataRef = useRef(null);
  const [limitRowsOB, setLimitRowsOB] = useState(5);
  

  const [streamData, setStreamData] = useState({
    bidBook: null,
    askBook: null,
    ltp: null
  });

  const [optionSimData, setOptionSimData] = useState({
    beta: 2.0,
    gamma: 1.0,
    mu: 1.0,
    contract_volume_mean: 2.0,
    contract_volume_std: 1.0,
    // expiry times (standard):
    // 5 hours, 10 hours, 1 day, 3 days, 5 days, 1 week
    expiry_times: [3600*5, 36000, 3600*24, 3600*24*3, 3600*24*5, 3600*24*7],
    strikes_per_expiry: 5
  })

  const MARKET_URL = "http://localhost:8000";
  const TRADINGENGINE_URL = "http://localhost:8001";


  
async function subscribeData() {
  const uri = "ws://localhost:8000/ws/subscribe_data";
  const socket = new WebSocket(uri);
  
  socket.onopen = () => {
    console.log("Connected to assetdata WebSocket");
  };

  socket.onmessage = (event) => {
    console.log('received ws message');
    
    try {
      const message = JSON.parse(event.data);
      console.log(message);

      // Update mutable ref immediately with new message data
      streamDataRef.current = {
        bidBook: message.bid_book,
        askBook: message.ask_book,
        ltp: message.ltp
      };

      // Then update React state to trigger re-render if needed
      setStreamData(streamDataRef.current);
      //console.log('STREAMED DATA RESULT:', streamData);
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

  return (
    <>
      <div style={{
          flex: '1 1 50%',
          minWidth: '400px',
          backgroundColor: 'rgba(0, 200, 0, 0.08)',
          // height: '10rem'
          }}>
          <OrderBookTable orders={streamData.bidBook} orderMaxLength={limitRowsOB}
          />
      </div>
      <button
            className="start-simulation"
            onClick={async () => {
                  // initiate market instance
                console.log('clicked start simulation button');
                console.log('initializing market')
              const initMarketResponse = await fetch(`${MARKET_URL}/init_market`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(initMarketParams)
              });
              if (initMarketResponse.status !== 200) {
                throw new Error('failed the init market', initMarketResponse.status);
              }
              console.log('initialized market');

              // start websocket connection
              console.log('subscribing to market data')
              await subscribeData();
              console.log('subbed to market data');

              // wait for valid connection
              const assertConnectionResponse = await fetch(`${MARKET_URL}/assert_connection`);
              if (assertConnectionResponse.status !== 200) {
                throw new Error('failed the assert connection', assertConnectionResponse.status);
              }
              console.log('asserted connection');

              setReadyToRun(true);

            }}
            disabled={readyToRun}
          >
            Start Simulation
          </button>
    </>
  )
}

export default App
