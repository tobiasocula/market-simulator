from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pydantic import BaseModel
import asyncio
import numpy as np
from datetime import timedelta, datetime
import logging
from scipy.stats import norm
from scipy.optimize import brentq # root finding method
from itertools import product

class Params(BaseModel):

    # generic
    start_time: str
    update_rate: float

    # options trading
    beta: float # decay parameter, for this model, this is constant for all contracts k,j
    gamma_m: float # determines strength between contract's moneynesses
    gamma_t: float # determines strength between contract's expiry dates
    mu_intensity: float # the static intensity per contract (also constant for all contracts here)
    w: float # determines strength of order volume
    contract_volume_mean: float | int # mean for lognormal sampling of option contract size
    contract_volume_std: float | int # std for lognormal sampling of option contract size
    expiry_dts: list[int] # expiry dates (seconds from opening)
    tau: list[list[float]] # relation matrix for call and put options
    volume_base: float # for determining volume of contract orders (base parameter)
    volume_time_decay: float # for determining volume of contract orders (parameter for relation with time)
    volume_moneyness: float # for determining volume of contract orders (parameter for relation with moneyness of contract)
    strike_dist_pcts: list[float] # strike distributions (one for each strike)
    risk_free: float
    dividend_rate: float
    lm_params: list[float] # parameters for limit order probability determination
    bs_params: list[float] # parameters for buy order probability determination
    limit_dist: float # parameter for exponentially distributed distance from ltp (if limit order)
    base_scale_init_orders: int # base price scale (exponential distribution for price; during construction of initial order book)
    moneyness_scale_init_orders: float # parameter for scaling price according to moneyness (init order book)
    time_scale_init_orders: float # parameter for scaling price according to time decay (init order book)
    base_n_orders_init: int # base number of orders per contract (init order book)
    beta_init: float # parameter for base liquidity calculation, with respect to time decay
    gamma_init: float # parameter for base liquidity calculation, with respect to moneyness

    # asset parameters
    init_open_price: float
    init_vola: float
    kappa: float # volatility mean reverting rate
    theta: float # volatility mean
    xi: float # volatility of volatility
    mu: float # asset yearly expected return
    rho: float # correlation volatility and asset price


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


def intensity(args):
    time, exp_idx, strike_idx, cte_type_idx, hist, params, strikes, asset_ltp, expiry_times, num_expiries, num_strikes = args
    lmbda = params.mu_intensity

    for i in range(num_expiries):
        for j in range(num_strikes):
            for c in range(2):

                if hist[i, j, c] is None:
                    rho_self = 1.3 if i == exp_idx and j == strike_idx else 1.0
                    tau = params.tau[c][cte_type_idx]
                    strike_k = strikes[j]
                    strike_curr = strikes[strike_idx]
                    lmbda += np.exp(
                        - params.gamma_t * np.abs(
                            (expiry_times[i] - expiry_times[exp_idx]).total_seconds() / (3600 * 24 * 365)
                        )
                        - params.gamma_m * np.abs(
                            np.log(strike_k / asset_ltp) - np.log(strike_curr / asset_ltp)
                            )
                    ) * rho_self * tau
                else:
                    for p in hist[i, j, c]:
                        cur_vol = p["vol"]
                        cur_time = p["time"]
                        rho_self = 1.3 if i == exp_idx and j == strike_idx else 1.0
                        tau = params.tau[c][cte_type_idx]
                        strike_k = strikes[j]
                        strike_curr = strikes[strike_idx]
                        lmbda += np.exp(
                            params.w * np.log(cur_vol)
                            - params.gamma_t * np.abs(
                                (expiry_times[i] - expiry_times[exp_idx]).total_seconds() / (3600 * 24 * 365)
                                )
                            - params.gamma_m * np.abs(
                                np.log(strike_k / asset_ltp) - np.log(strike_curr / asset_ltp)
                            ) - params.beta * (time - cur_time).total_seconds() / (3600 * 24 * 365)
                            ) * rho_self * tau
                        
    return lmbda



def imbalance_spread(contract_obs, exp_idx, strike_idx, type_idx):
    ob_bids = contract_obs[exp_idx, strike_idx, type_idx, 0]
    ob_asks = contract_obs[exp_idx, strike_idx, type_idx, 1]
    if ob_bids is None or ob_asks is None or ob_bids == [] or ob_asks == []:
        return 0, 0
    agg_bids = sum([row[1] for row in ob_bids])
    agg_asks = sum([row[1] for row in ob_asks])
    return (agg_bids - agg_asks) / (agg_bids + agg_asks + 1e-06), ob_bids[0][0] - ob_asks[0][0]

def black_scholes_call(S, K, T, r, q, sigma):
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def black_scholes_put(S, K, T, r, q, sigma):
    call = black_scholes_call(S, K, T, r, q, sigma)
    return call - S * np.exp(-q * T) + K * np.exp(-r * T)

def rev(a):
    n = len(a)
    return [a[n - k][:] for k in range(1, n+1)]
    

def binsort_matrix(arr, new, col=0):
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

    return arr[:m] + [new] + arr[m:]


def place_order(expiry_idx, strike_idx, time, volume, buy, call, price, contract_obs):
    if call:
        if buy:
            if contract_obs[expiry_idx, strike_idx, 0, 0] is None:
                contract_obs[expiry_idx, strike_idx, 0, 0] = [[price, volume, time]]
            else:
                contract_obs[expiry_idx, strike_idx, 0, 0] = rev(binsort_matrix(rev(contract_obs[expiry_idx, strike_idx, 0, 0]), [price, volume, time])) # , rev=True
        else:
            if contract_obs[expiry_idx, strike_idx, 0, 1] is None:
                contract_obs[expiry_idx, strike_idx, 0, 1] = [[price, volume, time]]
            else:
                contract_obs[expiry_idx, strike_idx, 0, 1] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 0, 1], [price, volume, time])
    else:
        if buy:
            if contract_obs[expiry_idx, strike_idx, 1, 0] is None:
                contract_obs[expiry_idx, strike_idx, 1, 0] = [[price, volume, time]]
            else:
                contract_obs[expiry_idx, strike_idx, 1, 0] = rev(binsort_matrix(rev(contract_obs[expiry_idx, strike_idx, 1, 0]), [price, volume, time])) # , rev=True
        else:
            if contract_obs[expiry_idx, strike_idx, 1, 1] is None:
                contract_obs[expiry_idx, strike_idx, 1, 1] = [[price, volume, time]]
            else:
                contract_obs[expiry_idx, strike_idx, 1, 1] = binsort_matrix(contract_obs[expiry_idx, strike_idx, 0, 0], [price, volume, time])

    return contract_obs

def sanitize_option_price(C_mkt, S, K, T, r, q, call=True):
    lower = max(0, S * np.exp(-q * T) - K * np.exp(-r * T)) if call else max(0, K * np.exp(-r * T) - S * np.exp(-q * T))
    upper = S * np.exp(-q * T) if call else K * np.exp(-r * T)
    return np.clip(C_mkt, lower + 1e-8, upper - 1e-8)

@app.post("/init")
async def init(data: Params):

    logging.info(f"init; received {data.model_dump()}")
    print(f"init; received {data.model_dump()}")

    logging.basicConfig(
        filename='log.log',    # Log file name
        level=logging.INFO,        # Log level
        format='%(asctime)s - %(levelname)s - %(message)s'  # Log message format
    )

    app.state.pauzed = False
    app.state.asset_price_drift = None
    app.state.asset_vola_drift = None

    # events
    app.state.ws_connected = asyncio.Event()
    app.state.asset_price_drift_set = asyncio.Event()

    # locks
    app.state.expiry_overviews_lock = asyncio.Lock()
    app.state.contract_obs_lock = asyncio.Lock()
    app.state.recent_vol_lock = asyncio.Lock()

    app.state.recent_vol_delta = timedelta(seconds=50) # "recent volume" time window

    app.state.strikes = np.array(
        sorted(list(set(
            [round(data.init_open_price * (1 + a)) for a in data.strike_dist_pcts]
            +
            [round(data.init_open_price * (1 - a)) for a in data.strike_dist_pcts]
            )))
        )
    
    

    N = len(app.state.strikes)
    M = len(data.expiry_dts)
    app.state.num_strikes = N
    app.state.num_expiries = M

    # track statistics
    app.state.recent_volume_sums = [[[0, 0] for _ in range(N)] for _ in range(M)]
    app.state.buy_sell_counts = [[[0, 0] for _ in range(N)] for _ in range(M)]
    app.state.limit_market_counts = [[[0, 0] for _ in range(N)] for _ in range(M)]
    app.state.total_orders = [[[0, 0] for _ in range(N)] for _ in range(M)]

    app.state.current_time = datetime.strptime(data.start_time, "%Y-%m-%d %H:%M:%S")
    app.state.params = data

    app.state.recent_volume = np.empty((M, N, 2), dtype=object) # list of dicts: [{"time": time, "value": value}, ...]
    

    app.state.expiry_times = [
        app.state.current_time + timedelta(seconds=t)
        for t in data.expiry_dts
    ]

    # each item is a list with the values [best_bid, best_ask, spread, volume, ltp, moneyness, iv]
    app.state.expiry_overviews = np.empty((M, N, 2), dtype=object)

    # each item is a list with entries [price, volume, time]
    app.state.contract_obs = np.empty((M, N, 2, 2), dtype=object)

    # prefill order book
    for i in range(M):
        for j in range(N):

            

            # print('creating order with price', contract_ltp, 'from the parameters; C_mrkt:', data.init_open_price,
            #       'strike:', app.state.strikes[j], 'T:', (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365),
            # 'volatility:', data.init_vola)

            T = (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365)
            moneyness = np.log(app.state.strikes[j] / data.init_open_price)
            rel_liq = np.exp(
                -app.state.params.gamma_init * moneyness
                -app.state.params.beta_init * T
                )
            
            scale_price = app.state.params.base_scale_init_orders * (
                1 + moneyness * app.state.params.moneyness_scale_init_orders
                + T * app.state.params.time_scale_init_orders)
            print('scaling price with', scale_price, 'used params: moneyness', moneyness, 'and T:', T)

            n_orders = max(1, np.random.poisson(rel_liq * app.state.params.base_n_orders_init))

            for k in range(2):

                if k == 0: # call
                    contract_ltp = black_scholes_call(
                        data.init_open_price,
                        app.state.strikes[j],
                        (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365),
                        app.state.params.risk_free,
                        app.state.params.dividend_rate,
                        data.init_vola
                    )
                else: # put
                    contract_ltp = black_scholes_put(
                        data.init_open_price,
                        app.state.strikes[j],
                        (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365),
                        app.state.params.risk_free,
                        app.state.params.dividend_rate,
                        data.init_vola
                    )

                for l in range(2):

                    d = np.random.exponential(scale_price, n_orders)
                    if l == 0: # buy order
                        prices = np.maximum(contract_ltp - d, 0.01)
                    else: # sell order
                        prices = contract_ltp + d

                    #print('gotten prices:', prices)

                    days = np.random.randint(1, 30, size=n_orders)
                    months = np.random.randint(1, 12, size=n_orders)
                    hours = np.random.randint(1, 23, size=n_orders)
                    times = [datetime(year=2024, month=m, day=d, hour=h) for d, m, h in zip(days, months, hours)]

                    vols = [max(1, int(k)) for k in np.random.lognormal(
                        app.state.params.contract_volume_mean,
                        app.state.params.contract_volume_std,
                        size=n_orders
                    ) * app.state.params.volume_base * np.exp(
                        -app.state.params.volume_moneyness * np.abs(np.log(
                            data.init_open_price / app.state.strikes[j]
                        )) - app.state.params.volume_time_decay * (
                            (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365)
                    ))]

                    for v, t, p in zip(vols, times, prices):
                        app.state.contract_obs = place_order(i, j, t, v, l == 0, k == 0, p, app.state.contract_obs)
                        print('returned from place order:', app.state.contract_obs)

                app.state.expiry_overviews[i, j, k] = [
                    app.state.contract_obs[i, j, k, 0][0][0], # best bid
                    app.state.contract_obs[i, j, k, 1][0][0], # best ask
                    app.state.contract_obs[i, j, k, 0][0][0] - app.state.contract_obs[i, j, k, 1][0][0], # spread
                    0.0, # volume (since not traded yet)
                    contract_ltp, # ltp
                    moneyness, # speaks for itself
                    app.state.params.init_vola # iv (starting out as just asset volatility)
                ]

                #print('fixed expiry overviews')

    #print('final contract obs:')
    #print([k[0] for k in app.state.contract_obs[0, 0, 0, 0]])

    app.state.tasks = []
    app.state.tasks.append(asyncio.create_task(price_drift()))
    app.state.tasks.append(asyncio.create_task(market_clock()))

    app.state.tasks.append(asyncio.create_task(recent_volume_checking_coro()))
    app.state.tasks.append(asyncio.create_task(trade_checking_coro()))
    app.state.tasks.append(asyncio.create_task(option_trade_cycle_coro()))

@app.get("/pauze")
async def pauze():
    if app.state.pauzed:
        app.state.tasks = []
        app.state.tasks.append(asyncio.create_task(price_drift()))
        app.state.tasks.append(asyncio.create_task(recent_volume_checking_coro()))
        app.state.tasks.append(asyncio.create_task(market_clock()))
        app.state.tasks.append(asyncio.create_task(trade_checking_coro()))
        app.state.tasks.append(asyncio.create_task(option_trade_cycle_coro()))
        app.state.pauzed = False
    else:
        for t in app.state.tasks:
            t.cancel()
        app.state.pauzed = True

def option_trade_cycle(params, num_expiries, num_strikes, current_time, strikes, asset_ltp, expiry_times, M):
    hist = np.empty((num_expiries, num_strikes, 2), dtype=object)
    args = []
    for i in range(num_expiries):
        for j in range(num_strikes):
            args.append((current_time, i, j, 0, hist, params, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))
            args.append((current_time, i, j, 1, hist, params, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

    with ThreadPoolExecutor(max_workers=4) as thread_pool:
        lambdas = list(thread_pool.map(intensity, args))
    Lambda = sum(lambdas)

    ex = -np.log(np.random.uniform()) / M
    args = []
    cand_time = current_time + timedelta(seconds=ex)
    for i in range(num_expiries):
        for j in range(num_strikes):
            args.append((cand_time, i, j, 0, hist, params, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))
            args.append((cand_time, i, j, 1, hist, params, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

    with ThreadPoolExecutor(max_workers=4) as thread_pool:
        lambdas_prime = list(thread_pool.map(intensity, args))
    Lambda_prime = sum(lambdas_prime)

    #print('ratio:', Lambda_prime / M, 'with Lambda prime:', Lambda_prime, 'and M:', M)

    if np.random.uniform() <= Lambda_prime / M:
        return True, Lambda, lambdas
    else:
        return False, M, cand_time.seconds
    

@app.get("/stop_sim")
async def stop_sim():
    for t in app.state.tasks:
        t.cancel()


async def recent_volume_checking_coro():
    loop = asyncio.get_event_loop()

    while True:

        new_vol_arr, new_vol_sums = await loop.run_in_executor(app.state.pool, recent_volume_checking,
            app.state.num_expiries, app.state.num_strikes, app.state.recent_volume, app.state.current_time, app.state.recent_vol_delta)
    
        app.state.recent_volume = new_vol_arr
        app.state.recent_volume_sums = new_vol_sums

        await asyncio.sleep(app.state.params.update_rate)

def recent_volume_checking(num_expiries, num_strikes, recent_volume, current_time, recent_vol_delta):

    new_vol_arr = np.full((num_expiries, num_strikes, 2), None)
    new_vol_arr_sum = [[[0, 0] for _ in range(num_strikes)] for _ in range(num_expiries)]
    for i in range(num_expiries):
        for j in range(num_strikes):
            for k in range(2):
                if recent_volume[i, j, k] is None:
                    continue
                for entry in recent_volume[i, j, k]:
                    print('entry time:', entry["time"])
                    if current_time - entry["time"] <= recent_vol_delta:
                        new_vol_arr_sum[i][j][k] += entry["value"]
                        if new_vol_arr[i, j, k] is None:
                            new_vol_arr[i, j, k] = [entry]
                        else:
                            new_vol_arr[i, j, k].append(entry)
                        

        return new_vol_arr, new_vol_arr_sum

async def option_trade_cycle_coro():
    print('called option trade cycle coro')

    hist = np.empty((app.state.num_expiries, app.state.num_strikes, 2), dtype=object)

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

    loop = asyncio.get_event_loop()
    M = 1

    order_counter = 0

    while True:
        #print('in while loop')
        args = await loop.run_in_executor(app.state.pool, option_trade_cycle, 
                    app.state.params, app.state.num_expiries, app.state.num_strikes,
                    app.state.current_time, app.state.strikes, app.state.asset_price_drift, app.state.expiry_times, M
        )
        
        if args[0]:

            #print('ACCEPTING ORDER')

            M, lambdas = args[1:]
            rel_probs = lambdas / np.sum(lambdas)
            p = np.cumsum(rel_probs)
            chosen_prob = np.random.uniform()

            for param_arr, p_idx in unpack([
                app.state.num_expiries, app.state.num_strikes, 2
            ]):
                i, j, c = [int(k) for k in param_arr]
                if p[p_idx] >= chosen_prob:
                   
                    vol = int(np.random.lognormal(
                        app.state.params.contract_volume_mean,
                        app.state.params.contract_volume_std
                    ) * app.state.params.volume_base * np.exp(
                        -app.state.params.volume_moneyness * np.abs(np.log(
                            app.state.asset_price_drift / app.state.strikes[j]
                        )) - app.state.params.volume_time_decay * (
                            (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365)
                    )))

                    
                    if vol == 0: # round to nearest non-zero integer
                        vol = 1

                    #print('caulculating imb spread with contract obs', app.state.contract_obs)
                    imb, spread = imbalance_spread(app.state.contract_obs, i, j, c)
                    eta_lm = (
                        app.state.params.lm_params[0]
                        + app.state.params.lm_params[1] * imb
                        + app.state.params.lm_params[2] * spread
                        + app.state.params.lm_params[3] * app.state.recent_volume_sums[i][j][c] # recent volume
                    )
                    p_market = 1 / (1 + np.exp(-eta_lm)) # prob for market order

                    eta_bs = (
                        app.state.params.bs_params[0] # base parameter
                        + app.state.params.bs_params[1] * imb # imbalance
                    )
                    p_buy = 1 / (1 + np.exp(-eta_bs)) # prob for buy

                    buy = np.random.uniform() <= p_buy
                    entry = {
                        "vol": vol,
                        "side": 0 if buy else 1,
                        "time": app.state.current_time
                    }
                    if hist[i, j, c] is None:
                        hist[i, j, c] = [entry]
                    else:
                        hist[i, j, c].append(entry)

                    #app.state.buy_sell_counts[i][j][c] = round(float(app.state.buy_sell_counts[i][j][c] * order_counter + p_buy) / (order_counter + 1), ndigits=2)
                    #app.state.limit_market_counts[i][j][c] = round(float(app.state.limit_market_counts[i][j][c] * order_counter + p_market) / (order_counter + 1), ndigits=2)
                    app.state.buy_sell_counts[i][j][c] = round(p_buy, ndigits=2)
                    app.state.limit_market_counts[i][j][c] = round(p_market, ndigits=2)

                    order_counter += 1

                    # determine price
                    T = (app.state.expiry_times[i] - app.state.current_time).total_seconds() / (3600 * 24 * 365)
                    if c == 0:  # call
                        theo = black_scholes_call(app.state.asset_price_drift, app.state.strikes[j], T,
                                                app.state.params.risk_free, app.state.params.dividend_rate,
                                                app.state.params.init_vola)
                    else:  # put
                        theo = black_scholes_put(app.state.asset_price_drift, app.state.strikes[j], T,
                                                app.state.params.risk_free, app.state.params.dividend_rate,
                                                app.state.params.init_vola)
                        
                    #print('chosen price', theo, 'for market order; with params; C_mrkt:', app.state.asset_price_drift,
                            #'strike:', app.state.strikes[j], 'T:', T, 'volatility:', app.state.params.init_vola)
                            
                    if np.random.uniform() <= p_market:
                        # market order
                        
                        #price = app.state.contract_obs[i, j, c, 0 if buy else 1][0][0]
                        price = theo
                        
                        # except:
                        #     print('except, shape of obs:', app.state.contract_obs.shape, 'and i,j,c:', i, j, c)
                    else:
                        # limit order
                        # distance from ltp is exponentially distributed
                        dist = -np.log(np.random.uniform()) / app.state.params.limit_dist
                        # price = app.state.asset_price_drift + dist if not buy else app.state.asset_price_drift - dist
                        
                        price = theo + dist if not buy else max(theo - dist, 0.001)
                        #price = theo * (1 + dist) if not buy else max(theo * (1 - dist), 0.01)
                        print('dist:', dist, 'and buy:', buy)


                    #print('PLACING ORDER')
                    # def place_order(expiry_idx, strike_idx, time, volume, buy, call, price, contract_obs):
                    contract_obs = await loop.run_in_executor(app.state.pool, place_order,
                            i, j, app.state.current_time, vol, buy, c == 0, price, app.state.contract_obs)
                    
                    async with app.state.contract_obs_lock:
                        app.state.contract_obs = contract_obs

                    break

        else:
            print('DENYING ORDER')
            M, cand_time = args[1:]
            await asyncio.sleep((cand_time - app.state.current_time).total_seconds())

        await asyncio.sleep(app.state.params.update_rate)

async def market_clock():
    while True:
        app.state.current_time += timedelta(seconds=app.state.params.update_rate)
        await asyncio.sleep(app.state.params.update_rate)

async def price_drift():
    logging.info('called price_drift')
    print('called price drift')

    # get update rate in years
    dt = app.state.params.update_rate / (365 * 24 * 3600)
    app.state.asset_price_drift = app.state.params.init_open_price
    app.state.asset_vola_drift = app.state.params.init_vola

    while True:

        # update price and vola using Heston model
        z1 = np.random.normal()
        z2 = np.random.normal()
        dw_s = np.sqrt(dt) * z1
        dw_v = np.sqrt(dt) * (app.state.params.rho * z1 + np.sqrt(1 - app.state.params.rho**2) * z2)

        # update volatility
        app.state.asset_vola_drift = app.state.asset_vola_drift + app.state.params.kappa * (app.state.params.theta - app.state.asset_vola_drift) * dt + app.state.params.xi * np.sqrt(app.state.asset_vola_drift) * dw_v
        # update price
        app.state.asset_price_drift = app.state.asset_price_drift * np.exp((app.state.params.mu - 0.5 * app.state.asset_vola_drift**2) * dt + np.sqrt(app.state.asset_vola_drift) * dw_s)
        app.state.asset_price_drift_set.set()
        await asyncio.sleep(app.state.params.update_rate)
    

@app.get("/assert_connection")
async def assert_connection():
    while not app.state.ws_connected.is_set():
        await asyncio.sleep(app.state.params.update_rate)




@app.websocket("/ws/subscribe_data")
async def subscribe_data(websocket: WebSocket):
    await websocket.accept()
    while True:
        #print(app.state.recent_volume[0, 4, 0])
        try:
            await websocket.send_json({
                "overview": format_overview(app.state.expiry_overviews),
                "obs": format_obs(app.state.contract_obs),
                "time": app.state.current_time.isoformat(),
                "expiries": [a.isoformat() for a in app.state.expiry_times],
                "strikes": app.state.strikes.tolist(),
                "assetPriceDrift": app.state.asset_price_drift,
                "assetVolaDrift": app.state.asset_vola_drift,
                "limit_market_probs": app.state.limit_market_counts,
                "buy_sell_probs": app.state.buy_sell_counts,
                "recent_volume": app.state.recent_volume_sums,
                "total_orders": app.state.total_orders
            })
            app.state.ws_connected.set()
            await asyncio.sleep(app.state.params.update_rate)
        except asyncio.CancelledError:
            print("Marketdata websocket handler cancelled")
            await websocket.close()
            raise
        except Exception as e:
            print(f"Unexpected error in websocket handler: {e}")
            await websocket.close()
            raise

def format_overview(struct):
    res = []
    for i in range(struct.shape[0]):
        data = [
            [round(float(k), ndigits=2) for k in struct[i,j,0]]
            +
            [round(float(app.state.strikes[j]), ndigits=2)]
            +
            [round(float(k), ndigits=2) for k in struct[i,j,1][::-1]]
            for j in range(struct.shape[1])
        ]
        res.append({"expiry": app.state.expiry_times[i].isoformat(),
                    "data": data})
    return res

def format_obs(struct):

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

    return res


def implied_vol_call(C_mkt, S, K, T, r, q):
    #print('called implied vol call with params', C_mkt, S, K, T, r, q)
    try:
        return brentq(
            lambda sigma: black_scholes_call(S, K, T, r, q, sigma) - C_mkt,
            1e-6, 10.0
        )
    except Exception as e:
        print('FAILED TO USE IMPLIED VOL CALL:', e)
        print('WITH VALUES:')
        print('Cmrkt:', C_mkt); print('S:', S); print('K:', K); print('T:', T); print('r and q:', r, q)
        raise


def trade_checking(contract_obs, current_time, expiry_overviews, recent_volume, strikes, expiries, asset_price_drift, total_volume):
    logging.info("trade checking called")
    s = contract_obs.shape
    for i in range(s[0]):
        for j in range(s[1]):
            for k in range(s[2]):
                if contract_obs[i, j, k, 0] is None or contract_obs[i, j, k, 1] is None:
                    logging.info("trade checking; returning because None")
                    continue
                if contract_obs[i, j, k, 0] == [] or contract_obs[i, j, k, 1] == []:
                    logging.info("trade checking; returning because empty lists")
                    continue
                if contract_obs[i, j, k, 0][0][0] < contract_obs[i, j, k, 1][0][0]:
                    logging.info("trade checking; returning because no matching orders")
                    continue
                logging.info("trade checking; continuing")
                if (current_time - contract_obs[i, j, k, 0][0][2] > current_time - contract_obs[i, j, k, 1][0][2]):
                    price = contract_obs[i, j, k, 0][0][0]
                else:
                    price = contract_obs[i, j, k, 1][0][0]

                # compute iv
                #print('computing iv with parameters:', price, asset_price_drift, 'and T:', (expiries[i] - current_time).total_seconds() / (3600 * 24 * 365))
                T = (expiries[i] - current_time).total_seconds() / (3600 * 24 * 365)
                C_mrkt = sanitize_option_price(price, asset_price_drift, strikes[j], T, 0.01, 0.0)
                iv = implied_vol_call(
                    C_mrkt, asset_price_drift, strikes[j], T, 0.01, 0.0
                    )
                

                if contract_obs[i, j, k, 0][0][1] > contract_obs[i, j, k, 1][0][1]:
                    logging.info("trade checking; greater buy than sell volume")
                    print("trade checking; greater buy than sell volume")

                    # greater buy volume than sell volume
                    best_ask = contract_obs[i, j, k, 1][0][0]
                    expiry_overviews[i, j, k][1] = best_ask
                    expiry_overviews[i, j, k][2] = best_ask - expiry_overviews[i, j, k][5]
                    expiry_overviews[i, j, k][3] += contract_obs[i, j, k, 1][0][1]
                    expiry_overviews[i, j, k][4] = price
                    expiry_overviews[i, j, k][5] = np.log(strikes[j] / price)
                    expiry_overviews[i, j, k][6] = iv
                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 1][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 1][0][1]})

                    total_volume[i][j][k] += contract_obs[i, j, k, 1][0][1]

                    # subtract trade vol
                    contract_obs[i, j, k, 0][0][1] -= contract_obs[i, j, k, 1][0][1]
                    # remove best ask
                    contract_obs[i, j, k, 1] = contract_obs[i, j, k, 1][1:]

                elif contract_obs[i, j, k, 0][0][1] < contract_obs[i, j, k, 1][0][1]:
                    logging.info("trade checking; greater sell than buy volume")
                    print("trade checking; greater sell than buy volume")

                    # greater sell volume than buy volume
                    best_bid = contract_obs[i, j, k, 0][0][0]
                    expiry_overviews[i, j, k][0] = best_bid
                    expiry_overviews[i, j, k][2] = expiry_overviews[i, j, k][1] - best_bid
                    expiry_overviews[i, j, k][3] += contract_obs[i, j, k, 0][0][1]
                    expiry_overviews[i, j, k][4] = price
                    expiry_overviews[i, j, k][5] = np.log(strikes[j] / price)
                    expiry_overviews[i, j, k][6] = iv
                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 0][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 0][0][1]})

                    total_volume[i][j][k] += contract_obs[i, j, k, 0][0][1]
                    
                    # subtract trade vol
                    contract_obs[i, j, k, 1][0][1] -= contract_obs[i, j, k, 0][0][1]
                    # remove best bid
                    contract_obs[i, j, k, 0] = contract_obs[i, j, k, 0][1:]

                else: # equal volume
                    logging.info("trade checking; equal volume")
                    print("trade checking; equal volume")

                    best_bid = contract_obs[i, j, k, 0][0][0]
                    best_ask = contract_obs[i, j, k, 1][0][0]
                    expiry_overviews[i, j, k][0] = best_bid
                    expiry_overviews[i, j, k][1] = best_ask
                    expiry_overviews[i, j, k][2] = best_bid - best_ask
                    expiry_overviews[i, j, k][3] += contract_obs[i, j, k, 1][0][1]
                    expiry_overviews[i, j, k][4] = price
                    expiry_overviews[i, j, k][5] = np.log(strikes[j] / price)
                    expiry_overviews[i, j, k][6] = iv
                    if recent_volume[i, j, k] is None:
                        recent_volume[i, j, k] = [{"time": current_time, "value": contract_obs[i, j, k, 0][0][1]}]
                    else:
                        recent_volume[i, j, k].append({"time": current_time, "value": contract_obs[i, j, k, 0][0][1]})

                    total_volume[i][j][k] += contract_obs[i, j, k, 0][0][1]

                    # remove best bid
                    contract_obs[i, j, k, 0] = contract_obs[i, j, k, 0][1:]
                    # remove best ask
                    contract_obs[i, j, k, 1] = contract_obs[i, j, k, 1][1:]

    return contract_obs, expiry_overviews, recent_volume, total_volume

async def trade_checking_coro():
    loop = asyncio.get_event_loop()
    logging.info("trade checking coro called")
    while True:
        contract_obs, expiry_overviews, recent_volume, total_volume = await loop.run_in_executor(app.state.pool, trade_checking, 
                app.state.contract_obs, app.state.current_time, app.state.expiry_overviews, app.state.recent_volume, app.state.strikes,
                app.state.expiry_times, app.state.asset_price_drift, app.state.total_orders
            )
        logging.info("trade checking coro; info returned")
        async with app.state.contract_obs_lock:
            app.state.contract_obs = contract_obs
        async with app.state.expiry_overviews_lock:
            app.state.expiry_overviews = expiry_overviews
        async with app.state.recent_vol_lock:
            app.state.recent_volume = recent_volume
        app.state.total_orders = total_volume
        logging.info("trade checking coro; updated params")
        await asyncio.sleep(app.state.params.update_rate)