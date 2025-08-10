
import './App.css'
import { useState, useRef, useEffect } from 'react';

const BASEURL = "http://localhost:8000";

// Standard normal using Box-Muller
function randomNormal(mean, stdDev) {
  const u1 = Math.random();
  const u2 = Math.random();
  const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return z0 * stdDev + mean;
}

function OrderBookTable({ orders }) {

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
        {orders ? orders.map(({ price, volume, time }, idx) => (
          <tr key={idx} style={{ borderBottom: '1px solid #222' }}>
            <td style={{ textAlign: 'right', padding: '4px' }}>{price.toFixed(2)}</td>
            <td style={{ textAlign: 'right', padding: '4px' }}>{volume}</td>
            <td style={{ textAlign: 'center', padding: '4px' }}>{time}</td>
          </tr>
        ))
        : <></>}
      </tbody>
    </table>

    
    </div>
  );
}

function Terminal({ logs }) {
  // Automatically scrolls to bottom on new logs
  const terminalRef = useRef(null);

  // useEffect(() => {
  //   if (terminalRef.current) {
  //     terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  //   }
  // }, [logs]);

  return (
    <div
      ref={terminalRef}
      style={{
        background: '#111',
        color: '#0f0',
        padding: '16px',
        fontFamily: 'monospace',
        fontSize: '14px',
        height: '300px',
        overflowY: 'auto',
        borderRadius: '8px',
        marginBottom: '20px',
      }}
      className="terminal"
    >
      {logs.map((line, idx) => (
        <div key={idx}>{line}</div>
      ))}
    </div>
  );
}

function App() {

  const inSim = useRef(false);
  const orderCounter = useRef(0);
  const [orderLogs, setOrderLogs] = useState([]);
  const [tradeLogs, setTradeLogs] = useState([]);
  const [generalLog, setGeneralLog] = useState([]);

  const addOrderLog = (line) => setOrderLogs((logs) => [...logs, line]);
  const addTradeLog = (line) => setTradeLogs((logs) => [...logs, line]);
  const addGeneralLog = (line) => setGeneralLog((logs) => [...logs, line]);

  const [curTime, setCurTime] = useState(null);
  const [curPrice, setCurPrice] = useState(null);

  useEffect(() => {
    inSim.current = inSim;
  }, [inSim]);

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
      n_participants: 10
  });
  const [tradeSettings, setTradeSettings] = useState({
    pctAgressiveOrders: 0.30, // pct of orders trading below (selling) or above (buying)
    // current best bid and ask
    pctLimitOrders: 0.30, // pct of limit orders (not aggressive)
    avgTradesBeforeMarketOpen: 10.0, // per minute per participant
    avgTradesAfterMarketOpen: 2.0, // per minute per participant
    avgPriceDeviation: 0.01, // avg price deviation when trading aggresively
    stdPriceDeviation: 0.005, // std of price deviation when trading aggresively
    upperTradeVolume: 12,
    lowerTradeVolume: 6,
    pctBuyOrders: 0.5
  });
  const streamedData = useRef({
    bidBook: null,
    askBook: null,
    bestBid: null,
    bestAsk: null,
    currentTime: null,
    participantData: null,
    numOrdersInOB: null,
    currentPrice: null
  });

function orderGenerator(participant_id) {

  const time = new Date(Date.now()).toISOString().slice(11, 19);
  console.log('now:', time);
  const aggressiveOrder = Math.random() <= tradeSettings.pctAgressiveOrders;
  const volume = Math.round((Math.random() * 
  (tradeSettings.upperTradeVolume - tradeSettings.lowerTradeVolume)
) + tradeSettings.lowerTradeVolume);
  const buy = Math.random() <= tradeSettings.pctBuyOrders;
  if (aggressiveOrder) {
    let price;
    if (buy) {
      price = streamedData.current.currentPrice +
      randomNormal(streamedData.current.currentPrice * tradeSettings.avgPriceDeviation,
        streamedData.current.currentPrice * tradeSettings.stdPriceDeviation);
    } else {
      price = streamedData.current.currentPrice -
      randomNormal(streamedData.current.currentPrice * tradeSettings.avgPriceDeviation,
        streamedData.current.currentPrice * tradeSettings.stdPriceDeviation);
        console.log('value1:', streamedData.current.currentPrice * tradeSettings.avgPriceDeviation);
        console.log('value2:', streamedData.current.currentPrice * tradeSettings.stdPriceDeviation);
      console.log('randomnormal:', randomNormal(streamedData.current.currentPrice * tradeSettings.avgPriceDeviation,
        streamedData.current.currentPrice * tradeSettings.stdPriceDeviation));
    }
    console.log('price3:', price);
    return {volume, buy, participant_id, price, time, id: orderCounter.current};
  } else {
    const limitOrder = Math.random() <= tradeSettings.pctLimitOrders;
    if (limitOrder) {
      let price;
      if (buy) {
        price = streamedData.current.currentPrice -
        randomNormal(streamedData.current.currentPrice * tradeSettings.avgPriceDeviation,
        streamedData.current.currentPrice * tradeSettings.stdPriceDeviation);
    } else {
        price = streamedData.current.currentPrice +
        randomNormal(streamedData.current.currentPrice * tradeSettings.avgPriceDeviation,
        streamedData.current.currentPrice * tradeSettings.stdPriceDeviation);
    }
    console.log('price4:', price);
    return {volume, buy, participant_id, price, time, id: orderCounter.current};
    } else {
      if (buy) {
        const price = streamedData.current.bestBid;
        console.log('price1:', price);
        return {volume, buy, participant_id, price, time, id: orderCounter.current};
      } else {
        const price = streamedData.current.bestAsk;
        console.log('price2:', price);
        return {volume, buy, participant_id, price, time, id: orderCounter.current};
      }
    }
  }
}

async function sendOrderBeforeMarketOpen(pid) {
  const orderParams = orderGenerator(pid);
  console.log('orderparams:', orderParams);
  const resp = await fetch(`${BASEURL}/place_order_before_market_open`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderParams)
          });
  if (resp.status !== 200) {
    throw new Error('failed to send order before market open:', resp.status);
  }
  addOrderLog(`BEFORE MARKET OPEN: sent ${orderParams.buy ? 'buy' : 'sell'} order from ${pid} with volume ${orderParams.volume} @${orderParams.price}
    at timestamp ${orderParams.time}`);
}

useEffect(() => {
  console.log('STREAMED DATA UPDATED:', streamedData.current);
}, [streamedData.current]);


function subscribeMarketData() {
  const uri = "ws://localhost:8000/ws/marketdata";
  const socket = new WebSocket(uri);

  socket.onopen = () => {
    console.log("Connected to marketdata WebSocket");
  };

  socket.onmessage = (event) => {
    
    try {
      const message = JSON.parse(event.data);

      setCurTime(message.current_time);
      setCurPrice(message.current_price);
      //console.log('current time:', message.current_time);

      // Pass the parsed message to caller’s callback handler
      streamedData.current = {
        bidBook: message.bid_book,
        askBook: message.ask_book,
        bestBid: message.best_bid,
        bestAsk: message.best_ask,
        currentPrice: message.current_price,
        currentTime: message.current_time,
        participantData: message.participants,
        numOrdersInOB: message.num_orders_in_ob,
        ltp: message.ltp
      };
      console.log('STREAMED DATA RESULT:', streamedData.current);
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

async function sendOrderAfterMarketOpen(pid) {
  const orderParams = orderGenerator(pid);
  console.log('orderparams:', orderParams);
  const resp = await fetch(`${BASEURL}/place_order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderParams)
          });
  if (resp.status !== 200) {
    throw new Error('failed to send order before market open:', resp.status);
  }
  addOrderLog(`sent ${orderParams.buy ? 'buy' : 'sell'} order from ${pid} with volume ${orderParams.volume} @${orderParams.price}
    at timestamp ${orderParams.time}`);
  const msg = await resp.json();
  if (msg["msg"] !== "") addTradeLog(msg["msg"]);
}

async function oneParticipantTradeCycleAfterMarketOpen(id) {
  const n = Math.round(1 / marketSettings.sleep_step);
  let c = 0;

  // close time date
  const [hcl, mcl, scl] = marketSettings.close_time.split(":").map(Number);
  const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);

  while (true) {
    const [hc, mc, sc] = streamedData.current.currentTime.split(":").map(Number);
    const currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
    //console.log('seen currenttime:', currentTimeDate);
    if (currentTimeDate >= closeTimeDate) return;
    if (!inSim.current) return;
    if (c % n === 0) {
      const chanceToTrade = tradeSettings.avgTradesAfterMarketOpen / 60;
      if (Math.random() <= chanceToTrade) sendOrderAfterMarketOpen(id);
    }
    c++;
    await new Promise(resolve => setTimeout(resolve, 1000 * marketSettings.sleep_step));
  }

}

async function oneParticipantTradeCycleBeforeMarketOpen(id) {
  //console.log('streameddata:', streamedData);
  
  const n = Math.round(1 / marketSettings.sleep_step);
  let c = 0;

  while (typeof streamedData.current?.currentTime !== "string") {
    await new Promise(res => setTimeout(res, 100));
  }
  //console.log("curTimeString BEFORE split:", streamedData.current.currentTime);

  // open time date
  const [ho, mo, so] = marketSettings.open_time.split(":").map(Number);
  const openTimeDate = new Date(1970, 0, 1, ho, mo, so);

  while (true) {
    
    const [hc, mc, sc] = streamedData.current.currentTime.split(":").map(Number);
    const currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
    //console.log('seen currenttime:', currentTimeDate);
    if (currentTimeDate >= openTimeDate) return;
    if (!inSim.current) return;

    if (c % n === 0) {
      const chanceToTrade = tradeSettings.avgTradesBeforeMarketOpen / 60;
      if (Math.random() <= chanceToTrade) sendOrderBeforeMarketOpen(id);
    }
    c++;
  await new Promise(resolve => setTimeout(resolve, 1000 * marketSettings.sleep_step));
}

}

  
async function startSimulation() {

  addGeneralLog('started simulation');
  inSim.current = true;

  const pIDs = [...Array(marketSettings.n_participants).keys()]
  console.log('pids:', pIDs);


  // initialize market
  // sets market parameters and sets main time clock
  const initMarketResp = await fetch(`${BASEURL}/init_market`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(marketSettings)
          });
  if (initMarketResp.status !== 200) {
    throw new Error('failed to init market:', initMarketResp.status);
  }
  

  // activate live streaming of market data
  const ws = subscribeMarketData();

  // wait for websocket messages to be able to go through
  const waitWSResponse = await fetch(`${BASEURL}/wait_for_ws_connection`);
  if (waitWSResponse.status !== 200) {
    throw new Error('failed to wait for ws:', waitWSResponse.status);
  }

  // start trading cycle for participants
  //await new Promise(resolve => setTimeout(resolve, 5000));
  const tasks = pIDs.map(pid => oneParticipantTradeCycleBeforeMarketOpen(pid));

  // wait for market to open
  await Promise.all(tasks);
  
  // market open
  const marketOpenResponse = await fetch(`${BASEURL}/at_market_open`);
  if (marketOpenResponse.status !== 200) {
    throw new Error('failed at market open:', marketOpenResponse.status);
  }
  const msg = await marketOpenResponse.json();
  if (msg["msg"] !== "") addTradeLog(msg["msg"]);
  addGeneralLog("Market has opened");


  console.log('FINISHED AT MARKET OPEN')
  
  // start trading cycle now that market has opened
  const marketOpenTasks = pIDs.map(pid => oneParticipantTradeCycleAfterMarketOpen(pid));

}

  return (
    <>
    <div className='horizontal-layers' style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '10px',
      gap: '10px'
    }}>
      <div className='control-layer' style={{
          display: 'flex',
          gap: '10px',
          marginTop: '10px'
        }}>
          <div className='buttons' style={{
            display: 'flex', flexDirection: 'column', justifyContent: 'space-around'
          }}>
          <button
            className="start-simulation"
            onClick={startSimulation}
            disabled={inSim.current}
            style={{
              backgroundColor: 'green',
              border: 'none',
              borderRadius: '5px',
              color: 'white',
              width: '5rem',
              height: '3rem'
            }}
          >
            Start
          </button>
          <button
            className="end-simulation"
            onClick={() => {
              inSim.current = false;
              window.location.reload();
            }}
            disabled={!inSim.current}
            style={{
              backgroundColor: 'red',
              border: 'none',
              borderRadius: '5px',
              color: 'white',
              width: '5rem',
              height: '3rem'
            }}
          >
            End
          </button>
      </div>

      <div className='market-settings' style={{
        display: 'flex', flexDirection: 'column', alignContent: 'center'
      }}>
        {Object.entries(marketSettings).map(([key, value]) => (
          <div key={key} style={{
            display: 'flex', gap: '10px', justifyContent: 'space-between'
          }}>
            <div>{key}</div>
            <input type="text" value={value} onChange={(e) => setMarketSettings(
              (prev) => ({...prev, [key]: e.target.value})
            )}
            />
          </div>
        ))}
      </div>

      <div className='trade-settings' style={{
        display: 'flex', flexDirection: 'column', alignContent: 'center'
      }}>
        {Object.entries(tradeSettings).map(([key, value]) => (
          <div key={key} style={{
            display: 'flex', gap: '10px', justifyContent: 'space-between'
          }}>
            <div>{key}</div>
            <input type="text" value={value} onChange={(e) => setTradeSettings(
              (prev) => ({...prev, [key]: e.target.value})
            )}
            />
          </div>
        ))}
      </div>

      </div>

      <div className='sub-layer'>
        <div className='current-time-sec'>{inSim.current ? (
          <div className='current-time' style={{
          fontSize: '1.1rem',
          fontWeight: 'bold',
          marginTop: '5px'
        }}>
          {`Current time: ${curTime}`}
        </div>
        ) : (<></>)
      }
      </div>
      <div className='current-price-sec'>
        {inSim.current ? (
          <div className='current-price' style={{
          fontSize: '1.1rem',
          fontWeight: 'bold',
          marginTop: '5px'
        }}>
          {`Current price: ${curPrice}`}
        </div>
        ) : (<></>)
      }
      </div>
      </div>

      <div className='view-layer' style={{
        display: 'flex',
        justifyContent: 'center',
        gap: '20px',
        alignItems: 'flex-start',  // prevent stretching tall empty logs
        width: '100%',
        maxWidth: '1200px'
      }}>
        <div style={{
          flex: '1 1 50%',
          minWidth: '400px',
          backgroundColor: 'rgba(0, 200, 0, 0.08)'
          }}>
          <OrderBookTable orders={streamedData.current.bidBook}
          />
        </div>
        <div style={{
            flex: '1 1 50%',
            minWidth: '400px',
            backgroundColor: 'rgba(200, 0, 0, 0.08)'
          }}>
          <OrderBookTable orders={streamedData.current.askBook}
          />
        </div>
        <div className='logs' style={{
          flex: '1 1 50%',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px'
        }}>
          <Terminal logs={generalLog} style={{ minHeight: '150px', maxHeight: '200px' }} />
          <Terminal logs={orderLogs} style={{ minHeight: '150px', maxHeight: '200px' }} />
          <Terminal logs={tradeLogs} style={{ minHeight: '150px', maxHeight: '200px' }} />
        </div>

      </div>

    </div>
    </>
  );
}

export default App;