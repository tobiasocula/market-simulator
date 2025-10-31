This engine implements an option contract order simulation.

### Order generation method

In my last engine, described in the "continuous_trading_with_ui/clientImplementation2" folder, I used a Poisson distribution with a variable $\lambda$ parameter for determining the frequency of trades. Although this doesn't preserve the memorylessness property of the Poisson distribution, since the $\lambda$ parameter is not constant, this was fine for simulating order quantities since there was a single instrument to be traded. However, since now my simulation should include multiple different "instruments", being the different option contracts, I needed a different approach.  
For the option order generation algorithm, I first thought to use a simple model, where a time interval $\Delta t$ gets sampled from an exponential distribution.

However, realising that the buying and selling of option contracts are correlated between contracts and orders within the same contract, I did some research for a different approach, and decided to use a Hawkes proces: https://en.wikipedia.org/wiki/Hawkes_process.

This can be used to model a so called self-exciting process, which means it's perfect for events that influence each other, for example the buying and selling of option contracts.
The Hawkes model uses the general formula

$\lambda(t|m)=\mu+\sum_{t_i\lt t}\phi(t-t_i,m_i)$

This function computes the intensity of a certain event that happened. In my case, this is a contract being exchanged. $\mu$ is the baseline intensity, and the sum thereafter determines the "extra" intensity of the event, dependent on the time that has passed and the "mark" $m$ of the event, being the characteristic of the event that will influence the intensity of the event.

The point is that, for a contract defined by (expiry, strike, type) (we denote this as the tuple ($i$, $j$, $c$)), we iterate over all contracts in the simulation, denoted ($\hat{i}, \hat{j}, \hat{c}$) and compute the sum of a certain function, defining the intensity relation between contracts ($\hat{i}, \hat{j}, \hat{c}$) and ($i$, $j$, $c$), over all these contracts. We then obtain a certain intensity value $\lambda_{(\hat{i}, \hat{j}, \hat{c})}$ for this contract. This factor determines how likely it is to get chosen for the next order coming into the system.

The formula inside of the sum I'm using is, for contract $k$, mark $m$ and current time $t$:

$\lambda_k(t|m)=\mu+\sum_{\hat{i}\in I}\sum_{\hat{j}\in J}\sum_{\hat{c}\in C}\sum_{t_i\lt t}\text{exp}(w\text{log}(V_{\hat{i},\hat{j},\hat{k}})-\gamma_t|T_i{\hat{i}}-T_i|-\gamma_m|\text{log}(K_{\hat{i}}/S)-\text{log}(K_i/S)|-\beta(t-t_{i,j,c}))\cdot\rho_{\text{self}}\cdot\tau_{c,\hat{c}}$

This is a very long expression, and I will explain each term step-by-step.

First, the sum;

$\sum_{\hat{i}\in I}\sum_{\hat{j}\in J}\sum_{\hat{c}\in C}\sum_{t_i\lt t}$

Simply sums over all contracts, with expiry $i$, strike price $j$ and type (call or put) $c$. One may also write this as

$\sum_{c\in\text{Contracts}}$

Then we discuss every factor in the sum.

-$w\cdot\text{log}(V_{\hat{i},\hat{j},\hat{k}})$: the log of the volume of order $(\hat{i}, \hat{j}, \hat{k})$ multiplied by its weight factor $w$.

-$-\gamma_t|T_i{\hat{i}}-T_i|$: the difference between expiry durations of the current contracts $\hat{i}$ and the contracts receiving the order, multiplied by its weight factor $\gamma_t$.

$-\gamma_m|\text{log}(K_{\hat{i}}/S)-\text{log}(K_i/S)|$: the difference in (log-)moneynesses between contracts $\hat{i}$ and $i$ multiplied by its weight factor $\gamma_m$.

-$-\beta(t-t_{i,j,c})$: $t-t_{i,j,c}$ is the amount of time left (in seconds) for expiry of the current contract. $\beta$ is the time-decay weight factor.

-$\rho_{\text{self}}$: this represents the factor defining the relationship between the expiry dates of current iteration contract and the contract receiving the order. The thought here is that this factor will be greater whenever two contracts have the same expiry date, resulting in a larger intensity on average between orders on the same expiry date.

-$\tau_{c,\hat{c}}$: this represents the factor defining the relationship between the contract types of current iteration contract and the contract receiving the order. $\tau$ is a $2\times 2$ matrix that defines, per pair (contract type, contract type), the impact an order request will have from one type to another. For example, $\tau_{0,0}$ defines the scaling factor where the current iterated contract is a call contract and the one receiving an order another call contract.

After having obtained this intensity value $\lambda$, we compute $\Lambda=\sum_i\lambda_i$, and a candidate time $t_c=t_{\text{current}}+\Delta t$, where $\Delta t\sim\text{exp}(M)$, with $M$ a well chosen upper bound on $\Lambda$.

We can then compute a candidate intensity for each contract, $\lambda_{k}^{\text{cand}}(t+\Delta t)$. Using this method, we can simulate clusters of orders coming in. If $\lambda_k(t)$ is large, then $M$ will be large and $\Delta t$ is small, and the quantity $\lambda_k(t+\Delta t)$ will be greater on average, therefor increasing the probability that a next order will come in.

We then accept an order coming in with probability $\Lambda_{k}^{\text{cand}}/M=\sum_i\lambda_{k}^{\text{cand}}/M$

### Volume sampling for each order

We simply use the formula;

$\text{Volume}_{i,j,c}=\text{Lognormal}(\mu,\sigma)\cdot V_0\cdot\text{exp}(-\gamma_m|\text{log}(S/K_j)-\beta(t-t_i))$

Where $\mu$ and $\sigma$ are parameters for lognormal sampling, $V_0$ is the baseline volume per order, $\gamma_m$ is the moneyness scalar, $\beta$ the time decay scalar, $\text{log}(S/K_j)$ the log-moneyness and $t-t_i$ the time until expiry.

### Buy vs sell order, limit vs market order

We also need to determine, for each order coming in, whether this will buy/sell the market or go for a limit order placement or rather trade at LTP.

For deciding this, I decided to implement a generalized linear model (GLM). This is just implementing a standard linear model, and then transforming its output in a meaningful way. We first compute the standard regression output as $\eta=\sum_i\alpha_ix_i$, where the $\alpha_i$ are scalar parameters we need to tune and the $x_i$ are the input parameters for each order, and then transform it into $p=1/(1+\text{exp}(\eta))$, which will be the probability of a limit order (or buy vs sell order).

For determining the probability for a limit order, I use the following features to determine this probability: the imbalance in the order book (which is equal to the quantity (buy volume - sell volume) / (buy volume + sell volume)), the current spread (best bid - best ask) and the recent volume of the contract. So here I use three parameters, $\alpha_1$, $\alpha_2$ and $\alpha_3$, and also a baseline parameter (zero here), $\alpha_0$.

For the buy/sell order determination I only use one parameter here (for now), being the imbalance in the order book. So here I have the parameters $\beta_0$ and $\beta_1$.