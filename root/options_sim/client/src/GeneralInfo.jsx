import MyContext from "./context.jsx";
import { useContext } from "react";
import "./generalInfo.css";

function GeneralInfo() {
    const MARKET_URL = "http://localhost:8000";
    const {streamedData, params, setStreamedData, running, setRunning} = useContext(MyContext);

    async function subscribeData() {
            const uri = "ws://localhost:8000/ws/subscribe_data";
            const socket = new WebSocket(uri);
            socket.onopen = () => console.log("Connected to assetdata WebSocket");
            socket.onmessage = (event) => {
                try {
                const message = JSON.parse(event.data);
                setStreamedData({
                    overview: message.overview,
                    obs: message.obs,
                    time: message.time,
                    expiries: message.expiries,
                    strikes: message.strikes,
                    assetPriceDrift: message.assetPriceDrift,
                    assetVolaDrift: message.assetVolaDrift
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
            return socket;
            }

    return (
        <>

            <div style={{
                display: "flex",
            }}>
            <button

            className={!running ? "start-simulation" : "start-simulation-disabled"}

            onClick={async () => {
                // initiate market instance
                console.log('clicked start simulation button');
                console.log('initializing market')
              const initMarketResponse = await fetch(`${MARKET_URL}/init`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
              });

              if (initMarketResponse.status !== 200) {

                throw new Error('failed the init market', initMarketResponse.status);

              }

              console.log('initialized market');
              // start websocket connection
              await subscribeData();
              const assertConnectionResponse = await fetch(`${MARKET_URL}/assert_connection`);
              if (assertConnectionResponse.status !== 200) {
                throw new Error('failed the assert connection', assertConnectionResponse.status);
              }
              console.log('asserted connection');
              setRunning(true);
                }}

            disabled={running}

          >

            Start

          </button>

          <button className={running ? "stop-simulation" : "stop-simulation-disabled"} onClick={async () => {
            const r = await fetch(`${MARKET_URL}/stop_sim`);
            if (r.status !== 200) {
              throw new Error('failed to stop sim:', r.status);
            }
            console.log('stopped sim (market side)');
            console.log('reloading..');
            window.location.reload();

          }} disabled={!running}>

            Stop

          </button>

          <button

            className={running ? "pauze-simulation" : "pauze-simulation-disabled"}
            onClick={async () => {
              console.log('PAUZE');

              const r = await fetch(`${MARKET_URL}/pauze`);
              console.log('STATUS:', r.status);

              if (r.status !== 200) {

              throw new Error('failed to pauze:', r.status);

            }

            }} disabled={!running}

          >Pauze
          </button>

          </div>

            {streamedData ? (
                <div style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center"
                }}>
                    <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        minWidth: "500px"
                    }}>
                        <div>Time:</div>
                        <div>{streamedData.time}</div>

                    </div>

                    <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        minWidth: "500px"
                    }}>
                        <div>Underlying price drift:</div>
                        <div>{streamedData.assetPriceDrift}</div>

                    </div>

                    <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        minWidth: "500px"
                    }}>
                        <div>Underlying volatility drift:</div>
                        <div>{streamedData.assetVolaDrift}</div>

                    </div>

                    <div style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end"
                    }}>
                        
                        
                        
                    </div>
                </div>
            ) : <div></div>}
        </>
    )

}
export default GeneralInfo;