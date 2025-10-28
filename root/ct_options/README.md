I wanted to expand upon my last simulation engine by improving the price generation process, as well as add a custom option order generator.  
### Frequency of trades   
In my last engine, described in the "continuous_trading_with_ui/clientImplementation2" folder, I used a Poisson distribution with a variable $\lambda$ parameter for determining the frequency of trades. Although this doesn't preserve the memorylessness property of the Poisson distribution, since the $\lambda$ parameter is not constant, this was fine for simulating order quantities since there was a single instrument to be traded. However, since now my simulation should include multiple different "instruments", being the different option contracts, I needed a different approach.  
For the option order generation algorithm, I first thought to use a simple model, where a time interval $\Delta t$ gets sampled from an exponential distribution.  
However, realising that the buying and selling of option contracts are correlated between contracts and orders within the same contract, I did some research for a different approach, and decided to use a Hawkes proces: https://en.wikipedia.org/wiki/Hawkes_process.  
This can be used to model a so called self-exciting process, which means it's perfect for events that influence each other, for example the buying and selling of option contracts.
The Hawkes model uses the general formula  
$\lambda(t|m)=\mu+\sum_{t_i\lt t}\phi(t-t_i,m_i)$  
This function computes the intensity of a certain event that happened. In my case, this is a contract being exchanged. $\mu$ is the baseline intensity, and the sum thereafter determines the "extra" intensity of the event, dependent on the time that has passed and the "mark" $m$ of the event, being the characteristic of the event that will influence the intensity of the event.  
In the file "testing_options_order_flow" I expand on these experiments and determine a general formula to use within the simulation engine for option contracts, as well as expand on this formula for including it for every contract and also letting the contract type (call / put contract) and type (buy / sell) having an impact on the total intensity per contract.  
### Volume determination for each event  
There are a few possibilities for determining the volume of an exchanged contract. One option is like I did in the previous engine for buying and selling assets, which is to sample it from a lognormal distribution with parameters a certain mean and std value. However, in this case, I want the volume to be influenced by factors like the moneyness and time decay, which makes it more realistic (more volume at ATM then far away from it, and more volume for short-term expiry options). My first idea is to use the following:  
$\text{Volume}=b\cdot\text{exp}(-a\cdot\text{ln}(S/K)-c\cdot T)$  
where $a$, $b$ and $c$ are parameters, $S$ is the asset price, $K$ is the strike and $T$ is the time until expiry (years).  
After seeking to improve this formula, by introducing randomness (I realised my formula was completely deterministic) and using log-moneyness instead, to make sure that distances from either side of ATM were treated equally (I read about this at https://en.wikipedia.org/wiki/Moneyness, and https://quant.stackexchange.com/questions/59421/why-use-moneyness-as-an-axis-on-a-volatility-surface), I'm now using  
$\text{Volume}=X\cdot b\cdot\text{exp}(-a\cdot |\text{log}(S/K)|-c\cdot T)$  
I've now added $X\sim\text{lognormal}(\mu_X,\sigma_X)$.

### Determining market vs. limit order, buy vs. sell order

Every time an order is accepted from the Hawkes process, we also have to determine whether this will be a buy or sell order and whether the simulation places a limit or market order.    
For this, I decided to use a generalized linear model, where we use the general formula

$\eta=\beta_0+\sum_i\beta_ix_i$

and then determine the final probability as

$\text{logit}(\eta)=1/(1+e^{-\eta})$

The coefficients $\beta_i$ can both be positive or negative, depending on whether a certain metric would increase or decrease the probability of one of the two possibilities happening.

For the probability of a buy order, we will only use one factor for now:
-$\x_1$: the imbalance between bids and asks, calculated as $(\text{bids}-\text{asks})/(\text{bids}+\text{asks})$, where $\text{asks}$ and $\text{bids}$ are the aggregate sum over all asks and bids of respectively all current orders in the orderbook.  
This is because one generally wants more buy orders when buy volume is relatively low, to counteract the surge in sell demand, and vice versa.

For the probability of a limit order, we use the following factors as terms in the linear model:

-$\x_1$: the same imbalance we used in the buy probability calculation  
-$\x_2$: the current spread of the contract (difference between best bid and ask)  
-$\x_3$: the recent volume of the contract (over the span of a predetermined time period)  
This choice comes down to the fact that one wants fewer limit orders when there is a relative balance in the market (meaning not much spread + imbalance).
The recent volume will negatively impact the probability for a limit order, because  a surge in recent trading volume would increase activity and therefor active participation in the form of more market orders.

### Choosing a limit price

I decided to use a simple model, where I'm just sampling  
$\text{Limit price}\sim\text{Exp}(\lambda)$
