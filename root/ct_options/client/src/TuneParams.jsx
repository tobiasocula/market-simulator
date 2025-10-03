import { useState, useContext } from "react";

import MyContext from "./context.jsx";

import GeneralInfo from "./GeneralInfo.jsx";




function TuneParams() {

 

    const {setStreamedData, initMarketParams, setInitMarketParams, assetSimData, setAssetSimData,
      running, setRunning, optionSimData, setOptionSimData
    } = useContext(MyContext);

    const descs = {
      start_time: "The fictitious start time (and date) of the simulation",
      update_rate: "Amount of time (seconds) per tick update (higher means higher frequency of time and market event updates)",
      init_open_price: "Initial open price of the underlying (from previous trading session(s))",
      init_vola: "Initial volatility of underlying (from previous trading session(s))",
      kappa: "Underlying's volatility mean reversion rate (used in Heston model). Higher means more stable volatility.",
      theta: "Underlying's volatility long-term mean used in Heston model. Higher means higher volatility on average.",
      xi: "Volatility of underlying's volatility. Higher means more volatile volatility. Used in Heston model",
      mu: "Long-term underlying's price drift, measured in pct-points per year. Eg. 0.1 means 10%/year on average. Used in Heston model",
      rho: "Correlation between underlying's price and volatility. Used in Heston model Must be 0 <= rho <= 1.",
      beta: "Time decay parameter for intensity calculation. Higher means higher intensity impact on orders that just came in. Eg. if beta = 1000, then the\
      half life will be ln(2) / 1000 years = approx. 4.2 hours.",
      gamma_m: "Strike-difference strength parameter for intensity calculation.\
      Higher means higher intensity impact on the difference in strike price between contracts.\
      Eg. if gamma_m = 5.0, then the multiplication factor in the exponent of the intensity will be,\
      if eg. K1 = 100 and k2 = 110: 5.0 * |ln(100 / 110)| = 0.48 (meaning the intensity will be quite severely lower)",
      gamma_t: "Expiry-difference strength parameter for intensity calculation.\
      Higher means more isolation between expiry-specific orders.\
      Eg. if gamma_t = 0.8, then the decay factor in the exponent of the intensity will be,\
      if for example expiry_1 = 1 day from now and expiry_2 = 7 days from now:\
      0.8 * (0.016 years difference) = 0.013 ≃ 0 such that the contributing multiplication factor will be exp(0) = 1.",
      mu_intensity: "The baseline intensity level per contract (universal for all contracts in this simulation).\
      If mu = 0, then the self-exciting property of the point-process used won't apply here, since the intensity can only come from the incoming of other orders.\
      If mu > 0, then spontaneous orders can come in without needing self-excitation to take place. Higher naturally means higher baseline intensity, so more\
      orders coming in on average per contract.",
      w: "Order size impact parameter for intensity calculation. Higher means more weight to order size when impacting the intensity calculation of\
      other contract orders, meaning large orders will lead to more self-excitation of other contracts.\
      If for example, w = 0.5, a certain contract order impacting the formula has a size of 5, then the term in the exponent\
      will be 0.5 * ln(5) = 0.80 such that the factor contributing in the formula will be exp(0.80) = 2.23.",
      contract_volume_mean: "Mean volume of contract orders, which are lognormally distributed. Higher means exponentially higher contract order sizes.",
      contract_volume_std: "Standard deviation of volume of contract orders (lognormally distributed).",
      expiry_dts: "Determines expiry dates for option contracts. In seconds from start time of simuation (eg. 36000 means 10 hours from starting time of simulation).",
      tau: "2x2 matrix determining the impact of one type of contract order exciting the contract order of another. The rows are indexed by the type of the contract\
      that is impacting the second contract, in the formula of the intensity calculation. Eg. tau[0, 1] is the impact of a call contract on a put order, and tau[1, 0]\
      is the impact of a put order onto a call order. Typically, the impact of put -> put order (which is tau[1, 1]) is greater than the others, because "
    };

    const [descActive, setDescActive] = useState({
      start_time: false,
      update_rate: false,
      init_open_price: false,
      init_vola: false,
      kappa: false,
      theta: false,
      xi: false,
      mu: false,
      rho: false,
      beta: false,
      gamma_m: false,
      gamma_t: false,
      mu_intensity: false,
      w: false,
      contract_volume_mean: false,
      contract_volume_std: false,
      expiry_dts: false,
      tau: false
    });

    const [infoAppearing, setInfoAppearing] = useState(false);

    console.log(descActive);



        return (

          <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: "10px"}}>

            <GeneralInfo/>

            <div style={{fontWeight: "bold"}}>General settings</div>
            <div style={{
              display: 'flex', flexDirection: 'column', alignContent: 'center', margin: '10px',
              width: '25rem'
            }}>
              
              {Object.entries(initMarketParams).map(([key, value]) => (
                <div key={key} style={{
                  display: 'flex', gap: '10px', justifyContent: 'space-between', position: "relative"
                }}>
                    <div>{key}</div>
                    <input type="text" value={value} onChange={(e) => setInitMarketParams((prev) => ({...prev, [key]: e.target.value}))} />
                    <button onClick={() => {
                      if (infoAppearing) return;
                      setDescActive((prev) => ({...prev, [key]: true}));
                      setInfoAppearing(true);
                    }
                    }>Info</button>

                    {descActive[key] && (
                      <div style={{
                        position: "absolute",
                        top: "50%",
                        left: "50%",
                        minWidth: "12rem",
                        transform: "translate(-50%, -50%)",
                        backgroundColor: "white",
                        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
                        padding: "8px",
                        zIndex: 1000,
                        backgroundColor: "rgba(15, 15, 15, 1)"
                        }}>
                        <div>{descs[key]}</div>
                        <button onClick={() => {
                          setDescActive((prev) => ({...prev, [key]: false}));
                          setInfoAppearing(false);
                        }}>Close</button>
                      </div>
                    )}
                    
            </div>
            
            ))}

          </div>

          <div style={{fontWeight: "bold"}}>Asset (underlying) simulation settings</div>
          <div style={{
              display: 'flex', flexDirection: 'column', alignContent: 'center', margin: '10px',
              width: '25rem'
            }}>
              
              {Object.entries(assetSimData).map(([key, value]) => (
                <div key={key} style={{
                  display: 'flex', gap: '10px', justifyContent: 'space-between'
                }}>
                    <div>{key}</div>
                    <input type="text" value={value} onChange={(e) => setAssetSimData((prev) => ({...prev, [key]: e.target.value}))} />
                    <button onClick={() => {
                      if (infoAppearing) return;
                      setDescActive((prev) => ({...prev, [key]: true}));
                      setInfoAppearing(true);
                    }
                    }>Info</button>
            </div>
            ))}

          </div>

          <div style={{fontWeight: "bold"}}>Option generation settings</div>
          <div style={{
              display: 'flex', flexDirection: 'column', alignContent: 'center', margin: '10px',
              width: '25rem'
            }}>
              
              {Object.entries(optionSimData).map(([key, value]) => (
                <div key={key} style={{
                  display: 'flex', gap: '10px', justifyContent: 'space-around'
                }}>
                    <div>{key}</div>
                    <input type="text" value={value} onChange={(e) => setOptionSimData((prev) => ({...prev, [key]: e.target.value}))} />
                    <button onClick={() => {
                      if (infoAppearing) return;
                      setDescActive((prev) => ({...prev, [key]: true}));
                      setInfoAppearing(true);
                    }
                    }>Info</button>
            </div>
            ))}

          </div>

        </div>

    );

}

 

export default TuneParams;