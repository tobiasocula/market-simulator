from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pydantic import BaseModel
import asyncio
import bisect
import numpy as np
from datetime import timedelta, datetime
import logging
import threading




class MarketInitializer(BaseModel):

    start_time: str

    update_rate: float



class OptionData(BaseModel):

    beta: float # decay parameter, for this model, this is constant for all contracts k,j

    gamma_m: float # determines strength between contract's moneynesses

    gamma_t: float # determines strength between contract's expiry dates

    mu_intensity: float # the static intensity per contract (also constant for all contracts here)

    w: float # determines strength of order volume

    contract_volume_mean: float | int # mean for lognormal sampling of option contract size

    contract_volume_std: float | int # std for lognormal sampling of option contract size

    expiry_dts: list[int]

    tau: list[list[float]] # relation matrix for call and put options

    # coefficients for determining volume of contract order

    volume_base: float

    volume_time_decay: float

    volume_moneyness: float

    strike_dist_pcts: list[float]

 

    risk_free: float

    dividend_rate: float

 

    # limit order vs market order params

    # spread, log of order size, order book imbalance

    lm_params: list[float]

    # buy vs sell order params

    # order book imbalance,

    bs_params: list[float]

 

    # parameter for exponentially distributed distance from ltp (if limit order)

    limit_dist: float


class AssetData(BaseModel):

    init_open_price: float

    init_vola: float

 

    # data for price stochastic modeling

    kappa: float # volatility mean reverting rate

    theta: float # volatility mean

    xi: float # volatility of volatility

    mu: float # asset yearly expected return

    rho: float # correlation volatility and asset price

class Params(BaseModel):

    market_data: MarketInitializer

    option_data: OptionData

    asset_data: AssetData


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = ProcessPoolExecutor()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_methods=["*"],

    allow_headers=["*"],
)


@app.get("/assert_connection")

async def assert_connection():

    while not app.state.ws_connected.is_set():

        await asyncio.sleep(app.state.market_data.update_rate)



@app.websocket("/ws/subscribe_data")

async def subscribe_data(websocket: WebSocket):

    await websocket.accept()

 

    while True:

        try:

            data_to_send = {

                "overview": format_overview(app.state.expiry_overviews),

                "obs": format_obs(app.state.contract_obs),

                "time": app.state.current_time.isoformat(),

                "expiries": [a.isoformat() for a in app.state.expiry_times],

                "strikes": app.state.strikes.tolist(),

                "assetPriceDrift": app.state.asset_price_drift,

                "assetVolaDrift": app.state.asset_vola_drift

            }

            #print('sending overview:')

            #print(data_to_send["overview"])

            await websocket.send_json(data_to_send)

            app.state.ws_connected.set()

            await asyncio.sleep(app.state.market_data.update_rate)

        except asyncio.CancelledError:

            print("Marketdata websocket handler cancelled")

            await websocket.close()

            raise

        except Exception as e:

            print(f"Unexpected error in websocket handler: {e}")

            await websocket.close()

            raise

def intensity(args):
    time, exp_idx, strike_idx, cte_type_idx, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes = args

    #print(">>> INTENSITY CALLED", time, exp_idx, strike_idx, cte_type_idx)

    # logging.getLogger().info('intensity called')

    lmbda = option_data.mu_intensity

    

    for i in range(num_expiries):

        for j in range(num_strikes):

            for c in range(2):

                if hist[i, j, c] is None:

                    

                    rho_self = 1.3 if i == exp_idx and j == strike_idx else 1.0

                    tau = option_data.tau[c][cte_type_idx]

                    strike_k = strikes[j]

                    strike_curr = strikes[strike_idx]
                    

                    lmbda += np.exp(

                        - option_data.gamma_t * np.abs(

                            (expiry_times[i] - expiry_times[exp_idx]).total_seconds() / (3600 * 24 * 365)

                        )

                        - option_data.gamma_m * np.abs(

                            np.log(strike_k / asset_ltp) - np.log(strike_curr / asset_ltp)

                            )

                    ) * rho_self * tau

                else:

                    

                    for p in hist[i, j, c]:

                        #print('CUR TIME')

                        cur_vol = p["vol"]

                        cur_time = p["time"]

                        #print('cur time:', cur_time)

                        rho_self = 1.3 if i == exp_idx and j == strike_idx else 1.0

                        tau = option_data.tau[c][cte_type_idx]

                        strike_k = strikes[j]

                        strike_curr = strikes[strike_idx]


                        lmbda += np.exp(

                            option_data.w * np.log(cur_vol)

                            - option_data.gamma_t * np.abs(

                                (expiry_times[i] - expiry_times[exp_idx]).total_seconds() / (3600 * 24 * 365)

                                )

                            - option_data.gamma_m * np.abs(

                                np.log(strike_k / asset_ltp) - np.log(strike_curr / asset_ltp)

                            ) - option_data.beta * (time - cur_time).total_seconds() / (3600 * 24 * 365)

                            ) * rho_self * tau

    return lmbda


# helper function
def binsort_matrix(arr, new, col=0, rev=False):
    if arr is None or arr == []:
        return [new]
    if arr[0][col] >= new[col]:
        return [new] + arr
    if arr[-1][col] <= new[col]:
        return arr + [new]
    L = 0
    N = len(arr) - 1
    U = N
    m = 0
    if rev:
        arr = arr[::-1]
    while U - L > 1:
        m = L + (U - L) // 2
        if arr[m][col] < new[col]:
            L = m
        elif arr[m][col] > new[col]:
            U = m
        else:
            break

    if arr[m][col] < new[col]:
        m += 1

    return arr[:m] + [new] + arr[m:] if not rev else (arr[:m] + [new] + arr[m:])[::-1]




# helper function



def format_obs(struct):

    # struct is np array with shape (n_expiries, n_strikes, 2, 2)

    # goal is to return a struct with structure

    # list with each item being

    # {expiry: expiry, data: {

    # strike: strike, ob: {

    # calls_bids: data1, calls_asks: data2, ..., data4}}}

    def clean_arr(arr):
        if arr is None:
            return None
        return [
            round(arr[0], ndigits=2),
            arr[1],
            arr[2].isoformat()
        ]

   

    res = []

    for i in range(len(struct)):

        data = []

        for j in range(len(struct[0])):

            calls_bids = struct[i,j,0,0] if struct[i,j,0,0] is not None else None

            calls_asks = struct[i,j,0,1] if struct[i,j,0,1] is not None else None

            puts_bids = struct[i,j,1,0]if struct[i,j,1,0] is not None else None

            puts_asks = struct[i,j,1,1] if struct[i,j,1,1] is not None else None

            data.append({"strike": float(app.state.strikes[j]),

                            "ob": {

                                "calls_bids": [clean_arr(a) for a in calls_bids] if calls_bids is not None else None,

                                "calls_asks": [clean_arr(a) for a in calls_asks] if calls_asks is not None else None,

                                "puts_bids": [clean_arr(a) for a in puts_bids] if puts_bids is not None else None,

                                "puts_asks": [clean_arr(a) for a in puts_asks] if puts_asks is not None else None

                            }

                         })

        res.append({"expiry": app.state.expiry_times[i].isoformat(), "data": data})

 

    #print('RES:'); print(res)

    return res


def format_overview(struct):

    # struct is np array with shape (6, 7, 2), every item is a list of lists

    # goal is to return a struct with structure

    # list with each item being a matrix (like a real OB)

    # strikes_calls/puts is a matrix (n_strikes x 8)
    res = []

    for i in range(struct.shape[0]):
        data = [
            [round(float(k), ndigits=2) for k in struct[i,j,0]] + [round(float(app.state.strikes[j]), ndigits=2)] + [round(float(k), ndigits=2) for k in struct[i,j,1][::-1]] # is list
            for j in range(struct.shape[1])
        ]

        res.append({"expiry": app.state.expiry_times[i].isoformat(),
                    "data": data})
        
    return res


async def market_clock():

    print('CALLED MARKET CLOCK')

    while True:

        app.state.current_time += timedelta(seconds=app.state.market_data.update_rate)

        await asyncio.sleep(app.state.market_data.update_rate)


def imbalance_spread(exp_idx, strike_idx, type_idx):
    ob_bids = app.state.contract_obs[exp_idx, strike_idx, type_idx, 0]
    ob_asks = app.state.contract_obs[exp_idx, strike_idx, type_idx, 1]
    if ob_bids is None or ob_asks is None or ob_bids == [] or ob_asks == []:
        return 0, 0
    agg_bids = sum([row[1] for row in ob_bids])
    agg_asks = sum([row[1] for row in ob_asks])
    return (agg_bids - agg_asks) / (agg_bids + agg_asks + 1e-06), ob_bids[0][0] - ob_asks[0][0]


async def price_drift():

    logging.info('price_drift')

    # get update rate in years
    dt = app.state.market_data.update_rate / (365 * 24 * 3600)

   

    app.state.asset_price_drift = app.state.asset_data.init_open_price

    app.state.asset_vola_drift = app.state.asset_data.init_vola

    while True:

        # update price and vola using Heston model

 

        z1 = np.random.normal()

        z2 = np.random.normal()

        dw_s = np.sqrt(dt) * z1

        dw_v = np.sqrt(dt) * (app.state.asset_data.rho * z1 + np.sqrt(1 - app.state.asset_data.rho**2) * z2)

 

        # update volatility

        app.state.asset_vola_drift = app.state.asset_vola_drift + app.state.asset_data.kappa * (app.state.asset_data.theta - app.state.asset_vola_drift) * dt + app.state.asset_data.xi * np.sqrt(app.state.asset_vola_drift) * dw_v

       

        # update price

        app.state.asset_price_drift = app.state.asset_price_drift * np.exp((app.state.asset_data.mu - 0.5 * app.state.asset_vola_drift**2) * dt + np.sqrt(app.state.asset_vola_drift) * dw_s)

        app.state.asset_price_drift_set.set()

        # print('price and vola:', app.state.asset_price_drift, app.state.asset_vola_drift)

        await asyncio.sleep(app.state.market_data.update_rate)


def trade_checking(contract_obs, current_time, expiry_overviews, recent_volume):
    """
    should be running constantly
    returns orderbook and overview structures
    """

    logging.info('TRADE CHECKING')

    # loop through contract_obs

    S = contract_obs.shape
    #print('S:', S)
    #print('check1')

    for i in range(S[0]):
        #print('check1.1')

        for j in range(S[1]):
            #print('check1.2')

            for k in range(S[3]):
                #print('check1.3')
                
                #print('a:', app.state.contract_obs[i, j, k, 0])
                #print('b:', app.state.contract_obs[i, j, k, 1])

                logging.info(f"COMPARING {contract_obs[i, j, k, 0] if contract_obs[i, j, k, 0] is not None else 'None'} TO {contract_obs[i, j, k, 1] if contract_obs[i, j, k, 1] is not None else 'None'}")

                if contract_obs[i, j, k, 0] is None or contract_obs[i, j, k, 1] is None:
                    logging.info("NONE VALUES - SKIPPING")
                    continue

                if contract_obs[i, j, k, 0] == [] or contract_obs[i, j, k, 1] == []:
                    logging.info("EMPTY LISTS - SKIPPING")
                    continue

            
                if contract_obs[i, j, k, 0][0][0] < contract_obs[i, j, k, 1][0][0]:
                    logging.info("NO OVERLAPPING PRICES - SKIPPING")

                    # no overlapping prices -> no trades possible

                    continue

                

                # determine trade price

                if (

                    current_time -

                    #parse_datetime(contract_obs[i, j, k, 0][0][2])
                    contract_obs[i, j, k, 0][0][2]

                    >

                    current_time -

                    #parse_datetime(contract_obs[i, j, k, 1][0][2])
                    contract_obs[i, j, k, 1][0][2]

                ):

                    # execute at buy price

                    price = contract_obs[i, j, k, 0][0][0]

                    #print('check3')

                    

                else:

                    # execute at sell price

                    price = contract_obs[i, j, k, 1][0][0]

                    #print('check4')

    


                
                #logging.info("GOTTEN THROUGH")
                if contract_obs[i, j, k, 0][0][1] > contract_obs[i, j, k, 1][0][1]:

                    # greater buy volume than sell volume
                    #print('greater buy volume')

                    #print('TRADE CHECKING 1')
                    #logging.info('PASSED FIRST CHECK')
                    
                        # update volume, ltp, and bid/ask

                    best_ask = contract_obs[i, j, k, 1][0][0]
                    expiry_overviews[i, j, k][6] = best_ask
                    expiry_overviews[i, j, k][7] = best_ask - expiry_overviews[i, j, k][5]
                    expiry_overviews[i, j, k][2] += contract_obs[i, j, k, 1][0][1]
                    expiry_overviews[i, j, k][4] = price
                        #print('EO UPDATED')

                    #logging.info("MODIFYING RECENT VOL")

                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 1][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 1][0][1]})



                    # subtract trade vol

                    contract_obs[i, j, k, 0][0][1] -= contract_obs[i, j, k, 1][0][1]

                    # remove best ask

                    contract_obs[i, j, k, 1] = contract_obs[i, j, k, 1][1:]

                    

                    

                    


                elif contract_obs[i, j, k, 0][0][1] < contract_obs[i, j, k, 1][0][1]:
                    #logging.info('PASSED SECOND CHECK')

                    # greater sell volume than buy volume
                    #print('greater sell volume')
                    #print('TRADE CHECKING 2')

                    # update volume, ltp, and bid/ask

                    best_bid = contract_obs[i, j, k, 0][0][0]

                    expiry_overviews[i, j, k][5] = best_bid

                    expiry_overviews[i, j, k][7] = expiry_overviews[i, j, k][6] - best_bid

                    expiry_overviews[i, j, k][2] += contract_obs[i, j, k, 0][0][1]

                    expiry_overviews[i, j, k][4] = price

                        #print('EO UPDATED')

                
                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 0][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 0][0][1]})

            
                        # subtract trade vol

                        contract_obs[i, j, k, 1][0][1] -= contract_obs[i, j, k, 0][0][1]

                        # remove best bid

                        contract_obs[i, j, k, 0] = contract_obs[i, j, k, 0][1:]

                else: # equal volume
                    #logging.info('PASSED f CHECK')


                        # update volume, ltp, and bid/ask

                    best_bid = contract_obs[i, j, k, 0][0][0]
                    best_ask = contract_obs[i, j, k, 1][0][0]
                    expiry_overviews[i, j, k][5] = best_bid
                    expiry_overviews[i, j, k][6] = best_ask
                    expiry_overviews[i, j, k][7] = best_bid - best_ask
                    expiry_overviews[i, j, k][2] += contract_obs[i, j, k, 1][0][1]
                    expiry_overviews[i, j, k][4] = price

        
                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 0][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 0][0][1]})

            
                    # remove best bid
                    contract_obs[i, j, k, 0] = contract_obs[i, j, k, 0][1:]
                    # remove best ask
                    contract_obs[i, j, k, 1] = contract_obs[i, j, k, 1][1:]

    return contract_obs, expiry_overviews, recent_volume



def option_trade_cycle(option_data, num_expiries, num_strikes, current_time, asset_data, strikes, asset_ltp, expiry_times, recent_volume_sums, expiry_overviews):

    def unpack(params):

        def update(ps, valid):
            last = ps[-1]
            if last == valid[-1] - 1:
                if len(ps) == 1:
                    return [None]
                return update(ps[:-1], valid[:-1]) + [0]
            else:
                return [k for k in ps[:-1]] + [last + 1]
            
        N = np.prod(params)
        K = np.zeros(len(params))
        for i in range(N):
            yield K, i
            K = update(K, params)
    """
    should be running constantly
    returns True/False, args
    True if order should go through
    False otherwise (wait .. seconds)
    """

    logging.info('option_trade_cycle')

    max_order_size_sigma = 3
    M = option_data.w * (max_order_size_sigma * option_data.contract_volume_std + option_data.contract_volume_mean)

    N = num_strikes * num_expiries * 2

    hist = np.empty((num_expiries, num_strikes, 2), dtype=object)
    args = []

    #logging.info('ARGS1:', args)

    for i in range(num_expiries):

        for j in range(num_strikes):

            args.append((current_time, i, j, 0, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

            args.append((current_time, i, j, 1, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

    #logging.info('ARGS:', args)

    with ThreadPoolExecutor(max_workers=4) as thread_pool:
        lambdas = list(thread_pool.map(intensity, args))

    #logging.info('LAMBDAS:', lambdas)

    Lambda = sum(lambdas)

    ex = -np.log(np.random.uniform()) / M

    if np.random.uniform() <= Lambda / M:
        # order accepted

        candidate_lambdas = np.empty(N)

        candidate_args = []

        candidate_Lambda = 0

        for i in range(num_expiries):

            for j in range(num_strikes):

                candidate_args.append((current_time, i, j, 0, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

                candidate_args.append((current_time, i, j, 1, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

        with ThreadPoolExecutor(max_workers=4) as thread_pool:
            results = list(thread_pool.map(intensity, candidate_args))

        for i, result in enumerate(results):

            candidate_lambdas[i] = result

            candidate_Lambda += result

        rel_probs = candidate_lambdas / candidate_Lambda


        p = np.cumsum(np.sort(rel_probs))


        #logging.info(f"P VALUES: {p}")

        chosen_prob = np.random.uniform()
        for param_arr, p_idx in unpack([
            num_expiries, num_strikes, 2
        ]):

            i, j, c = param_arr
            i, j, c = int(i), int(j), int(c)


            if p[p_idx] >= chosen_prob:
                # choose this contract for an order
                #print("new order for contract", p_idx)
                logging.info(f"CHOOSING CONTRACT {p_idx}")

                vol = int(np.random.lognormal(

                        option_data.contract_volume_mean,

                        option_data.contract_volume_std

                    ) * option_data.volume_base * np.exp(

                        -option_data.volume_moneyness * np.abs(np.log(

                            asset_ltp / strikes[j]

                        )) - option_data.volume_time_decay * (

                            (current_time - expiry_times[i]).total_seconds() / (3600 * 24 * 365)

                    )))
                
                if vol == 0: # round to nearest non-zero integer
                    vol = 1

                eta_lm = (

                    option_data.lm_params[0]

                    + option_data.lm_params[1] * expiry_overviews[i, j, c][7]

                    + option_data.lm_params[2] * vol

                )

                #p_market = 1 / (1 + np.exp(-eta_lm)) # prob for market order
                p_market = 0.5

                logging.info(f"PROB FOR MARKET ORDER: {p_market}")


                # determine probability for buy or sell
                # features of this GLM (feature vector):
                # -imbalance between buys and sells
                # -spread
                # -recent trading volume
                # -log of trade size
                # -moneyness

                imb, spread = imbalance_spread(i, j, c)

                eta_bs = (

                    option_data.bs_params[0]

                    + option_data.lm_params[1] * imb

                    + option_data.lm_params[2] * spread

                    + option_data.lm_params[3] * recent_volume_sums[i, j, c]

                    + option_data.lm_params[4] * np.log(vol)

                )

                #p_buy = 1 / (1 + np.exp(-eta_bs)) # prob for buy
                p_buy = 0.5
                logging.info(f"PROB FOR buy ORDER: {p_buy}")



                # update history

                buy = np.random.uniform() <= p_buy

                entry = {

                    "vol": vol,

                    "side": 0 if buy else 1,

                    "time": current_time

                }

                if hist[i, j, c] is None:

                    hist[i, j, c] = [entry]

                else:

                    hist[i, j, c].append(entry)



                # determine price

                if np.random.uniform() <= p_market:

                    # market order

                    price = asset_ltp

                else:

                    # limit order

                    # distance from ltp is exponentially distributed

                    dist = -np.log(np.random.uniform()) / option_data.limit_dist
                    logging.info(f"LIMIT ORDER DIST: {dist}")

                    price = asset_ltp + dist if not buy else asset_ltp - dist

                logging.info("RETURNING!!")

                return True, i, j, c, current_time, vol, buy, price

    else:
        return False, ex

        
def place_order(expiry_idx, strike_idx, time, volume, buy, call, price, contract_obs, expiries, strikes):

    logging.info('place_order')

    if call:

        if buy:

            if contract_obs[expiry_idx, strike_idx, 0, 0] is None:

                # descending
                #print('NEW AT EXPIRY', expiries[expiry_idx], 'AND STRIKE', strikes[strike_idx], 'CALL BUY')
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} CALL BUY')

                contract_obs[expiry_idx, strike_idx, 0, 0] = [[price, volume, time]]

                

            else:
                # descending
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} CALL BUY')
         
          
                contract_obs[expiry_idx, strike_idx, 0, 0] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 0, 0], [price, volume, time], rev=True)

        else:

            if contract_obs[expiry_idx, strike_idx, 0, 1] is None:
                #print('NEW AT EXPIRY', expiries[expiry_idx], 'AND STRIKE', strikes[strike_idx], 'CALL SELL')
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} CALL SELL')

                # descending
            
                contract_obs[expiry_idx, strike_idx, 0, 1] = [[price, volume, time]]

            else:
                #print('APPENDING AT EXPIRY', expiries[expiry_idx], 'AND STRIKE', strikes[strike_idx], 'CALL SELL')
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} CALL SELL')
        
                contract_obs[expiry_idx, strike_idx, 0, 1] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 0, 1], [price, volume, time])

    else:

        if buy:

            if contract_obs[expiry_idx, strike_idx, 1, 0] is None:
                #print('NEW AT EXPIRY', expiries[expiry_idx], 'AND STRIKE', strikes[strike_idx], 'PUT BUY')
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} PUT BUY')

                # descending
                contract_obs[expiry_idx, strike_idx, 1, 0] = [[price, volume, time]]

            else:
                #print('APPENDING AT EXPIRY', expiries[expiry_idx], 'AND STRIKE', strikes[strike_idx], 'PUT BUY')
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} PUT BUY')
            
                contract_obs[expiry_idx, strike_idx, 1, 0] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 1, 0], [price, volume, time], rev=True)


        else:

            if contract_obs[expiry_idx, strike_idx, 1, 1] is None:
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} PUT SELL')

                # descending

                contract_obs[expiry_idx, strike_idx, 1, 1] = [[price, volume, time]]

            else:
                #logging.info(f'NEW AT EXPIRY {expiries[expiry_idx]} AND STRIKE {strikes[strike_idx]} PUT SELL')
                contract_obs[expiry_idx, strike_idx, 1, 1] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 0, 0], [price, volume, time])

    return contract_obs


def recent_volume_checking(num_expiries, num_strikes, recent_volume, current_time, recent_vol_delta):

    logging.info('recent_volume_checking')

    new_vol_arr = np.full((num_expiries, num_strikes, 2), None)
    new_vol_arr_sum = np.zeros((num_expiries, num_strikes, 2))
    for i in range(num_expiries):
        for j in range(num_strikes):
            for k in range(2):
                # if recent_volume[i, j, k] is not None:
                #     logging.info(f"cur: {recent_volume[i, j, k]} from i,j,k {i} {j} {k}")
                if recent_volume[i, j, k] is None:
                    continue
                for entry in recent_volume[i, j, k]:

                    if entry["time"] - current_time <= recent_vol_delta:
                        if new_vol_arr[i, j, k] is None:
                            new_vol_arr[i, j, k] = [entry]
                        else:
                            new_vol_arr[i, j, k].append(entry)
                    else:
                        new_vol_arr_sum[i, j, k] += entry["value"]

        return new_vol_arr, new_vol_arr_sum
    

@app.post("/init")
async def init(data: Params):

    logging.basicConfig(
        filename='log.log',    # Log file name
        level=logging.INFO,        # Log level
        format='%(asctime)s - %(levelname)s - %(message)s'  # Log message format
    )

    app.state.pauzed = False

    app.state.asset_price_drift = None

    app.state.asset_vola_drift = None

    app.state.ws_connected = asyncio.Event()
    app.state.asset_price_drift_set = asyncio.Event()

    app.state.asset_ltp = data.asset_data.init_open_price

    app.state.contract_obs_lock = asyncio.Lock()

    app.state.option_data = data.option_data

    app.state.market_data = data.market_data

    app.state.asset_data = data.asset_data

    # one per order book (expiry, strike, type)
    app.state.recent_vol_delta = timedelta(seconds=5) # "recent volume" time window
    app.state.recent_vol_lock = asyncio.Lock()

    app.state.expiry_overviews_lock = asyncio.Lock()

    app.state.current_time = datetime.strptime(data.market_data.start_time, "%Y-%m-%d %H:%M:%S")

    app.state.expiry_times = [

        app.state.current_time + timedelta(seconds=t)

        for t in data.option_data.expiry_dts

    ]

 

    N = len(data.option_data.strike_dist_pcts)

    M = len(data.option_data.expiry_dts)

    app.state.num_strikes = N

    app.state.num_expiries = M
    
    app.state.recent_volume = np.full((M, N, 2), None) # datatype is a list of dicts: [{"time": time, "value": value}, ...]
    app.state.recent_volume_sums = np.zeros((M, N, 2))

    app.state.expiry_overviews = np.empty((M, N, 2), dtype=object)
    for i in range(app.state.expiry_overviews.shape[0]):
        for j in range(app.state.expiry_overviews.shape[1]):
            # entries are: bid, ask spread, volume, ltp, moneyness, oi, iv<
            app.state.expiry_overviews[i, j, 0] = [0 for _ in range(8)]
            app.state.expiry_overviews[i, j, 1] = [0 for _ in range(8)]

    app.state.contract_obs = np.empty((M, N, 2, 2), dtype=object)

    app.state.expiries = np.array([

        app.state.current_time + timedelta(seconds=k)

        for k in data.option_data.expiry_dts

    ])

 

    app.state.strikes = np.array(

        sorted(list(set([

        data.asset_data.init_open_price * (1 + a)

        for a in data.option_data.strike_dist_pcts

        ]

        +

        [

        data.asset_data.init_open_price * (1 - a)

        for a in data.option_data.strike_dist_pcts

        ])))

    )

    asyncio.create_task(price_drift())
    asyncio.create_task(market_clock())

    asyncio.create_task(trade_checking_coro())
    asyncio.create_task(option_trade_cycle_coro())

async def recent_volume_checking_coro():
    loop = asyncio.get_event_loop()

    while True:

        new_vol_arr, new_vol_sums = await loop.run_in_executor(app.state.pool, recent_volume_checking,
            app.state.num_expiries, app.state.num_strikes, app.state.recent_volume, app.state.current_time, app.state.recent_vol_delta)
        
        async with app.state.recent_vol_lock:
            app.state.recent_volume = new_vol_arr
            app.state.recent_volume_sums = new_vol_sums

        await asyncio.sleep(app.state.market_data.update_rate)


async def trade_checking_coro():
    loop = asyncio.get_event_loop()

    while True:

        contract_obs, expiry_overviews, recent_volume = await loop.run_in_executor(app.state.pool, trade_checking, 
                app.state.contract_obs, app.state.current_time, app.state.expiry_overviews, app.state.recent_volume
            )
        
        async with app.state.contract_obs_lock:
            app.state.contract_obs = contract_obs

        async with app.state.expiry_overviews_lock:
            app.state.expiry_overviews = expiry_overviews

        async with app.state.recent_vol_lock:
            app.state.recent_volume = recent_volume

        await asyncio.sleep(app.state.market_data.update_rate)
        
        



async def option_trade_cycle_coro():

    loop = asyncio.get_event_loop()

    while True:

        args = await loop.run_in_executor(app.state.pool, option_trade_cycle, 
                    app.state.option_data, app.state.num_expiries, app.state.num_strikes,
                    app.state.current_time, app.state.asset_data, app.state.strikes, app.state.asset_price_drift, app.state.expiry_times,
                    app.state.recent_volume_sums, app.state.expiry_overviews
            )
        
        
        if args[0]:

            # return True, i, j, c, current_time, vol, buy, price
            expiry_idx, strike_idx, type_idx, trade_time, vol, buy, price = args[1:]
            
            # def place_order(expiry_idx, strike_idx, time, volume, buy, call, price, contract_obs, expiries, strikes):
            contract_obs = await loop.run_in_executor(app.state.pool, place_order,
                    expiry_idx, strike_idx, trade_time, vol, buy, type_idx == 0, price, app.state.contract_obs, app.state.expiry_times, app.state.strikes)
            
            async with app.state.contract_obs_lock:
                app.state.contract_obs = contract_obs

        else:
            await asyncio.sleep(args[1])

        await asyncio.sleep(app.state.market_data.update_rate)

        """
        return True, i, j, c, current_time, vol, buy, not c, price

    else:
        return False, ex"""







