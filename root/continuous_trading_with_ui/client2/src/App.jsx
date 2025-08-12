
import './App.css'
import { useState, useRef, useEffect } from 'react';

const BASEURL = "http://localhost:8000";


// normal distribution simulator using Box-Muller transformation
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

  return (
    <div
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

  const handleStartClick = async () => {
    console.log('test');
  // init market
  const initMarketResp = await fetch(`${BASEURL}/init_market`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(marketSettings)
  });
  if (initMarketResp.status !== 200) {
    throw new Error('failed to init market:', initMarketResp.status);
  }

  // subscribe to market data and wait for validation
  await subscribeMarketData();
};

const [streamData, setStreamData] = useState({
    bidBook: null,
    askBook: null,
    bestBid: null,
    bestAsk: null,
    currentTime: null,
    participantData: null,
    numOrdersInOB: null,
    currentPrice: null
  });

const streamDataRef = useRef(streamData);

useEffect(() => {
  if (
    typeof streamDataRef.current.currentTime === 'string' &&
    typeof streamDataRef.current.currentPrice === 'number' &&
    !readyToRun.current
  ) {
    readyToRun.current = true;
    startSimulation();
  }
}, [streamDataRef.current.currentTime, streamDataRef.current.currentPrice]);

  const readyToRun = useRef(false);

  

  const orderCounter = useRef(0);
  const [orderLogs, setOrderLogs] = useState([]);
  const [tradeLogs, setTradeLogs] = useState([]);
  const [generalLog, setGeneralLog] = useState([]);

  const addOrderLog = (line) => setOrderLogs((logs) => [...logs, line]);
  const addTradeLog = (line) => setTradeLogs((logs) => [...logs, line]);
  const addGeneralLog = (line) => setGeneralLog((logs) => [...logs, line]);

  const [orderMethod, setOrderMethod] = useState(1); // standard: use second method (better IMO)


  const [marketSettings, setmarketSettings] = useState({
      open_time: "08:00:00",
      close_time: "12:00:00",
      start_time: "07:30:00",
      progress_step: 6.0,
      sleep_step: 0.1,
      ws_delay_step: 0.1,
      init_open_price: 100.0,
      participant_init_balance: 10_000.0,
      price_rounding_digits: 1,
      n_participants: 10
  });

  const [priceDrift, setPriceDrift] = useState(null);
  const priceDriftRef = useRef(null);

  

  // first method for determining order flow from participants
  // the goal is to determine the timeDelta interval in which a new order will be sent
  // this timedelta is sampled from an exponential distribution, using a lambda that is
  // sampled from a normal distribution
  const [tradeSettings1, setTradeSettings1] = useState({
    lambdaSampleMean: 1,
    lambdaSampleSTD: 0.2,
    pctBuyOrders: 0.5,
    // volume of each order is sampled from a log-normal distribution
    // using the mean and std:
    volumeMean: 2,
    volumeStd: 0.5,
    buyBias: 0.8
  });

  // second method for determining order flow from participants
  // the goal is to determine amount of orders in a fixed timedelta interval
  // this amount is sampled from a poisson distribution
  const [tradeSettings2, setTradeSettings2] = useState({
    tradeWaitStep: 0.5, // sec, timedelta length for order sampling
    avgGrowthRate: 0.01, // avg growth rate (increase in price) per timedelta
    priceDriftTimestep: 1, // sec, timedelta length for price drift cycle
    priceVolatility: 0.02, // units of price
    // volume of each order is sampled from a log-normal distribution
    // using the mean and std:
    volumeMean: 2,
    volumeStd: 0.5,
    // lambda parameter:
    // determines rate of order sending
    // is sampled for every participant out of normal distribution:
    lambdaSampleMean: 1,
    lambdaSampleSTD: 0.2,
    // function for determining number of orders in timedelta interval:
    // N = lambda + A*sin(B*t + C)
    A: 0.5,
    B: 1,
    C: 0,
    pctBuyOrders: 0.5,
    buyBias: 0.8
  });


  async function sendOrder(pid) {
    let vol;
    let buy;
    const buyBias = priceDriftRef.current / streamDataRef.current.currentPrice - 1;
    if (orderMethod === 0) {
      vol = Math.exp(randomNormal(tradeSettings1.volumeMean, tradeSettings1.volumeStd));
      
      buy = Math.random() <= Math.min(Math.max(
      tradeSettings2.pctBuyOrders + buyBias * tradeSettings2.buyBias
      , 0), 1);
    } else {
      console.log('VALUE:', tradeSettings2.pctBuyOrders + buyBias * tradeSettings2.buyBias);
      vol = Math.exp(randomNormal(tradeSettings2.volumeMean, tradeSettings2.volumeStd));
      buy = Math.random() <= Math.min(Math.max(
      tradeSettings2.pctBuyOrders + buyBias * tradeSettings2.buyBias
      , 0), 1);
    }
    
    const orderParams = {
      price: priceDrift,
      volume: vol,
      buy: buy,
      time: streamDataRef.current.currentTime,
      participant_id: pid,
      id: orderCounter.current
    };
    console.log('ORDERPARAMS:', orderParams);
    orderCounter.current++;
    const resp = await fetch(`${BASEURL}/place_order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderParams)
          });
    if (resp.status !== 200) {
      throw new Error('failed to send order after market open:', resp.status);
    }
  }

  async function participantCycle1(pid, lambda_i, endTime) {
    // trade cycle for one participant
    let [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
    let currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
    while (currentTimeDate < endTime) {
      // update current time
      [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
      currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);

      // determine waiting period (exponential distribution)
      // I used the explanation at
      // https://stats.stackexchange.com/questions/234544/from-uniform-distribution-to-exponential-distribution-and-vice-versa
      // to go form uniform -> exponential distribution

      await sendOrder(pid);
      const deltaT = -Math.log(Math.random()) / lambda_i;
      await new Promise(r => setTimeout(r, 1000 * deltaT));
    }
  }

  async function participantCycle2(pid, lambda_i, endTime) {
  let [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
  let currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);

  // Stop once end time is reached
  while (currentTimeDate < endTime) {
    [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
    currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
    const lambda_t = lambda_i + tradeSettings2.A * Math.sin(
    tradeSettings2.B + tradeSettings2.C
    );

    const u = Math.random();
    let cumRes = 0;
    let c = 0;
    let cumFact = 1;
    while (cumRes <= u) {
      cumRes += Math.log(-lambda_t) * lambda_t**c / cumFact;
      c++;
      cumFact *= c;
    }

    for (let i = 0; i < c; i++) {
      await sendOrder(pid);
    }
  }
}
  

async function priceDriftCycle() {
  const [hcl, mcl, scl] = marketSettings.close_time.split(":").map(Number);
  const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);
  let [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
  let currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
  while (currentTimeDate < closeTimeDate) {
    // use the discrete geometric brownian motion formula
    const VAL = streamDataRef.current.currentPrice * Math.exp(
      (tradeSettings2.avgGrowthRate - 0.5 * tradeSettings2.priceVolatility**2)
      * tradeSettings2.priceDriftTimestep
      + tradeSettings2.priceVolatility * Math.sqrt(tradeSettings2.priceDriftTimestep)
      * randomNormal(0, 1)
    );
    console.log('VAL:', VAL);
    priceDriftRef.current = VAL;
    setPriceDrift(priceDriftRef.current);
    await new Promise(r => setTimeout(r, 1000 * tradeSettings2.priceDriftTimestep));
    [hc, mc, sc] = streamDataRef.current.currentTime.split(":").map(Number);
    currentTimeDate = new Date(1970, 0, 1, hc, mc, sc);
  }

}

async function subscribeMarketData() {
  const uri = "ws://localhost:8000/ws/marketdata";
  const socket = new WebSocket(uri);

  socket.onopen = () => {
    console.log("Connected to marketdata WebSocket");
  };

  socket.onmessage = (event) => {
    
    try {
      const message = JSON.parse(event.data);

    console.log("WS parsed types:", typeof message.current_time, typeof message.current_price, message.current_price);
    console.log('Before setStreamData ->', message.current_price);

      // Update mutable ref immediately with new message data
      streamDataRef.current = {
        bidBook: message.bid_book,
        askBook: message.ask_book,
        currentPrice: message.current_price,
        currentTime: message.current_time,
        participantData: message.participants,
        numOrdersInOB: message.num_orders_in_ob,
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

  // return only if connection has been established

  // wait for websocket messages to be able to go through
  const waitWSResponse = await fetch(`${BASEURL}/wait_for_ws_connection`);
  if (waitWSResponse.status !== 200) {
    throw new Error('failed to wait for ws:', waitWSResponse.status);
  }

  // for being able to close socket later
  return socket;
}

  async function startSimulation() {

  addGeneralLog('started simulation');

  const pIDs = [...Array(marketSettings.n_participants).keys()];

  // activate price drift cycle (directional bias)
  // create price drift cycle
  priceDriftCycle();

  // activate trade cycle (depending on which method), for pre-market open
  const tasksBefMarketOpen = pIDs.map(p => {
    if (orderMethod === 0) {
      const lambda_i = randomNormal(tradeSettings1.lambdaSampleMean, tradeSettings1.lambdaSampleSTD);
      const [hcl, mcl, scl] = marketSettings.open_time.split(":").map(Number);
      const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);
      return participantCycle1(p, lambda_i, closeTimeDate);
    } else {
      const lambda_i = randomNormal(tradeSettings2.lambdaSampleMean, tradeSettings2.lambdaSampleSTD);
      const [hcl, mcl, scl] = marketSettings.open_time.split(":").map(Number);
      const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);
      return participantCycle2(p, lambda_i, closeTimeDate);
    }
  });

  // wait for market to open
  await Promise.all(tasksBefMarketOpen);

  console.log('AT MARKET OPEN');

  // at market open: clear OB and execute immediate trades
  const marketOpenResponse = await fetch(`${BASEURL}/at_market_open`);
  if (marketOpenResponse.status !== 200) {
    throw new Error('failed at market open:', marketOpenResponse.status);
  }
  console.log('CALLED AT MARKET OPEN');

  // activate trade cycle, for market open
  const tasksAfterMarketOpen = pIDs.map(p => {
    if (orderMethod === 0) {
      const lambda_i = randomNormal(tradeSettings1.lambdaSampleMean, tradeSettings1.lambdaSampleSTD);
      const [hcl, mcl, scl] = marketSettings.close_time.split(":").map(Number);
      const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);
      return participantCycle1(p, lambda_i, closeTimeDate);
    } else {
      const lambda_i = randomNormal(tradeSettings2.lambdaSampleMean, tradeSettings2.lambdaSampleSTD);
      const [hcl, mcl, scl] = marketSettings.close_time.split(":").map(Number);
      const closeTimeDate = new Date(1970, 0, 1, hcl, mcl, scl);
      return participantCycle2(p, lambda_i, closeTimeDate);
    }
  });


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
            onClick={handleStartClick}
            disabled={!readyToRun}
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
              window.location.reload();
            }}
            disabled={!readyToRun}
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
            <input type="text" value={value} onChange={(e) => setmarketSettings(
              (prev) => ({...prev, [key]: e.target.value})
            )}
            />
          </div>
        ))}
      </div>

      <div className='trade-settings' style={{
        display: 'flex', flexDirection: 'column', alignContent: 'center'
      }}>
        {orderMethod === 0 ?
        /// trade function 1
        Object.entries(tradeSettings1).map(([key, value]) => (
          <div key={key} style={{
            display: 'flex', gap: '10px', justifyContent: 'space-between'
          }}>
            <div>{key}</div>
            <input type="text" value={value} onChange={(e) => setTradeSettings1(
              (prev) => ({...prev, [key]: e.target.value})
            )}
            />
          </div>
        )) : 
        // trade function 2
        Object.entries(tradeSettings2).map(([key, value]) => (
          <div key={key} style={{
            display: 'flex', gap: '10px', justifyContent: 'space-between'
          }}>
            <div>{key}</div>
            <input type="text" value={value} onChange={(e) => setTradeSettings2(
              (prev) => ({...prev, [key]: e.target.value})
            )}
            />
          </div>
        ))
      }
      </div>

      <div className='trade-setting-chooser'>
        <button className='switch-settings' type='button'
        style={{
          backgroundColor: 'grey',
          border: 'none',
          borderRadius: '5px',
          color: 'white',
          width: '10rem',
          height: '3rem'
        }}
        onClick={() => orderMethod === 0 ? setOrderMethod(1) : setOrderMethod(0)}
        >Switch Order Policy Funcion</button>
        <div className='trade-settings-label'>Chosen: {orderMethod === 0 ? 'First' : 'Second'}</div>
      </div>

      </div>

      <div className='sub-layer'>
        <div className='current-time-sec'>{readyToRun ? (
          <div className='current-time' style={{
          fontSize: '1.1rem',
          fontWeight: 'bold',
          marginTop: '5px'
        }}>
          {`Current time: ${streamDataRef.current.currentTime}`}
        </div>
        ) : (<></>)
      }
      </div>
      <div className='current-price-sec'>
        {readyToRun ? (
          <div className='current-price' style={{
          fontSize: '1.1rem',
          fontWeight: 'bold',
          marginTop: '5px'
        }}>
          {`Current price: ${streamDataRef.current.currentPrice}`}
        </div>
        ) : (<></>)
      }
      </div>
      <div className='current-price-drift'>
        {readyToRun ? (
          <div className='current-price' style={{
          fontSize: '1.1rem',
          fontWeight: 'bold',
          marginTop: '5px'
        }}>
          {`Current price: ${priceDrift}`}
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
          <OrderBookTable orders={streamData.bidBook}
          />
        </div>
        <div style={{
            flex: '1 1 50%',
            minWidth: '400px',
            backgroundColor: 'rgba(200, 0, 0, 0.08)'
          }}>
          <OrderBookTable orders={streamData.askBook}
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
  )
}

export default App
