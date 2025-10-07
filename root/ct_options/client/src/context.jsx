import { createContext, useState } from "react";

// Create the context with default value null
const MyContext = createContext(null);

// Provider component to wrap your app or components
export const MyContextProvider = ({ children }) => {
  // State or values you want to provide
  const [streamedData, setStreamedData] = useState(null);
  const [readyToRun, setReadyToRun] = useState(false);
  const [running, setRunning] = useState(false);

  const [initMarketParams, setInitMarketParams] = useState({

            start_time: "2025-01-01 07:30:00",

            update_rate: 0.1 // seconds

      });

   

      const [assetSimData, setAssetSimData] = useState({

        init_open_price: 100.0,

        init_vola: 0.3,

        kappa: 0.5,

        theta: 0.07,

        xi: 0.03,

        mu: 0.8,

        rho: 0.5,

      });

 

      const [optionSimData, setOptionSimData] = useState({

          // time decay parameter for intensity calculation
          // higher -> higher intensity impact on orders that just came in
          // I used 1000 as the standard value. This means the half life (of the intensity) will be:
          // -ln(2) / beta = 0.00069 years or 0.177 trading days or about 4.2 hours.
          beta: 1000.0,

          // strike-difference strength parameter for intensity calculation
          // higher -> higher intensity impact on the difference in strike price between contracts
          // if gamma_m = 5.0, like here, then the multiplication factor in the exponent of the intensity will be,
          // if eg. K1 = 100 and k2 = 110: 5.0 * |ln(100 / 110)| = 0.48 (meaning the intensity will be quite severely lower)
          gamma_m: 2.0,

          // expiry-difference strength parameter for intensity calculation
          // higher -> more isolation between expiry-specific orders
          // if gamma_t = 0.8, then the decay factor in the exponent of the intensity will be,
          // if eg. expiry_1 = 1 day from now and expiry_2 = 7 days from now, and gamma_t = eg. 0.8::
          // 0.8 * (0.016 years difference) = 0.013 ≃ 0 such that this will be almost 1 in the exponent.
          gamma_t: 0.3,

          // base intensity
          mu_intensity: 100.0,

          // order size impact parameter for intensity calculation
          // higher -> higher volume orders will have bigger impact
          // 
          w: 0.5,

          contract_volume_mean: 1.0,

          contract_volume_std: 0.5,

          // expiry times (standard):

          // 5 hours, 10 hours, 1 day, 3 days, 5 days, 1 week

          //expiry_dts: [3600*5, 36000, 3600*24, 3600*24*3, 3600*24*5, 3600*24*7],

          expiry_dts: [3600*5, 36000],

          tau: [[1.0, 1.0], [1.0, 1.0]],

          volume_base: 1.0,

          volume_time_decay: 0.2,

          volume_moneyness: 0.6,

          strike_dist_pcts: [0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5],

          risk_free: 0.01,

          dividend_rate: 0.0,

          // parameters: base, bid-ask imbalance, spread, recent volume
          lm_params: [0.0, 0.8, 1.5, 0.9],

          // parameters: base, bid-ask imbalance
          bs_params: [0.0, -1.5],

          limit_dist: 1.0,
          init_iv: 0.14,
          init_spread: 1.0

        });

  return (
    <MyContext.Provider value={{ streamedData, setStreamedData, readyToRun, setReadyToRun, optionSimData, setOptionSimData,
      assetSimData, setAssetSimData, initMarketParams, setInitMarketParams, running, setRunning
     }}>
      {children}
    </MyContext.Provider>
  );
};

export default MyContext;
