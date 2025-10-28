
def option_trade_cycle(option_data, num_expiries, num_strikes, current_time, asset_data, strikes, asset_ltp, expiry_times, recent_volume_sums, expiry_overviews, M):
    logging.info('CALLED OPTION TRADE CYCLE')

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

    # max_order_size_sigma = 3
    # M = option_data.w * (max_order_size_sigma * option_data.contract_volume_std + option_data.contract_volume_mean)

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

    logging.info(f'LAMBDAS: {lambdas}')

    Lambda = sum(lambdas)

    logging.info(f"VALUES OF LAMBDA AND M: lambda {Lambda} and M: {M}")

    ex = -np.log(np.random.uniform()) / M
    print('ODDS:', Lambda / M)

    args = []
    cand_time = current_time + ex
    for i in range(num_expiries):

        for j in range(num_strikes):

            args.append((cand_time, i, j, 0, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))

            args.append((cand_time, i, j, 1, hist, option_data, strikes, asset_ltp, expiry_times, num_expiries, num_strikes))


    with ThreadPoolExecutor(max_workers=4) as thread_pool:
        lambdas_prime = list(thread_pool.map(intensity, args))

    Lambda_prime = sum(lambdas_prime)

    if np.random.uniform() <= Lambda_prime / M:

        # accept event

        rel_probs = lambdas_prime / Lambda_prime

        p = np.cumsum(np.sort(rel_probs))
        chosen_prob = np.random.uniform()

        for param_arr, p_idx in unpack([
            num_expiries, num_strikes, 2
        ]):

            i, j, c = [int(k) for k in param_arr]

            if p[p_idx] >= chosen_prob:
                # choose this contract for an order
                #print("new order for contract", p_idx)
                #logging.info(f"CHOOSING CONTRACT {p_idx}")

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

                imb, spread = imbalance_spread(i, j, c)

                eta_lm = (

                    option_data.lm_params[0]

                    + option_data.lm_params[1] * imb

                    + option_data.lm_params[2] * spread

                    + option_data.lm_params[3] * recent_volume_sums[i, j, c] # recent volume

                )

                p_market = 1 / (1 + np.exp(-eta_lm)) # prob for market order
                #p_market = 0.5

                #logging.info(f"PROB FOR MARKET ORDER: {p_market}")


                # determine probability for buy or sell
                # features of this GLM (feature vector):
                # -imbalance between buys and sells
                # -spread
                # -recent trading volume
                # -log of trade size
                # -moneyness

                

                eta_bs = (

                    option_data.bs_params[0] # base parameter

                    + option_data.bs_params[1] * imb # imbalance

                )

                p_buy = 1 / (1 + np.exp(-eta_bs)) # prob for buy
                #p_buy = 0.5
                #logging.info(f"PROB FOR buy ORDER: {p_buy}")



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

                    price = expiry_overviews[i, j, c][4] #!!!

                else:

                    # limit order

                    # distance from ltp is exponentially distributed

                    dist = -np.log(np.random.uniform()) / option_data.limit_dist
                    #logging.info(f"LIMIT ORDER DIST: {dist}")

                    price = asset_ltp + dist if not buy else asset_ltp - dist

                #logging.info("RETURNING!!")

                logging.info(f"RETURNING Lambda {Lambda}")
                return True, i, j, c, cand_time, vol, buy, price, Lambda
            
    else:
        return False, M
    



"""
# accept event

        rel_probs = lambdas_prime / Lambda_prime

        p = np.cumsum(np.sort(rel_probs))
        chosen_prob = np.random.uniform()

        for param_arr, p_idx in unpack([
            num_expiries, num_strikes, 2
        ]):

            i, j, c = [int(k) for k in param_arr]

            if p[p_idx] >= chosen_prob:
                # choose this contract for an order
                #print("new order for contract", p_idx)
                #logging.info(f"CHOOSING CONTRACT {p_idx}")

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

                imb, spread = imbalance_spread(i, j, c)

                eta_lm = (

                    option_data.lm_params[0]

                    + option_data.lm_params[1] * imb

                    + option_data.lm_params[2] * spread

                    + option_data.lm_params[3] * recent_volume_sums[i, j, c] # recent volume

                )

                p_market = 1 / (1 + np.exp(-eta_lm)) # prob for market order
                #p_market = 0.5

                #logging.info(f"PROB FOR MARKET ORDER: {p_market}")


                # determine probability for buy or sell
                # features of this GLM (feature vector):
                # -imbalance between buys and sells
                # -spread
                # -recent trading volume
                # -log of trade size
                # -moneyness

                

                eta_bs = (

                    option_data.bs_params[0] # base parameter

                    + option_data.bs_params[1] * imb # imbalance

                )

                p_buy = 1 / (1 + np.exp(-eta_bs)) # prob for buy
                #p_buy = 0.5
                #logging.info(f"PROB FOR buy ORDER: {p_buy}")



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

                    price = expiry_overviews[i, j, c][4] #!!!

                else:

                    # limit order

                    # distance from ltp is exponentially distributed

                    dist = -np.log(np.random.uniform()) / option_data.limit_dist
                    #logging.info(f"LIMIT ORDER DIST: {dist}")

                    price = asset_ltp + dist if not buy else asset_ltp - dist

                #logging.info("RETURNING!!")

                logging.info(f"RETURNING Lambda {Lambda}")
                return True, i, j, c, cand_time, vol, buy, price, Lambda
"""