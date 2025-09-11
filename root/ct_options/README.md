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
$\text{Volume}=b\cdot\text{exp}(-a\text{ln}(S/K)-cT)$  
where $a$, $b$ and $c$ are parameters, $S$ is the asset price, $K$ is the strike and $T$ is the time until expiry (years).  
After seeking to improve this formula, by introducing randomness (I realised my formula was completely deterministic) and using log-moneyness instead, to make sure that distances from either side of ATM were treated equally (I read about this at https://en.wikipedia.org/wiki/Moneyness, and https://quant.stackexchange.com/questions/59421/why-use-moneyness-as-an-axis-on-a-volatility-surface), I'm now using  
$\text{Volume}=X\cdot b\cdot\text{exp}(-a\cdot |\text{log}(S/K)|-c\cdot T)$  
I've now added $X\sim\text{lognormal}(\mu_X,\sigma_X)$.  
### Determining market vs. limit order  
$\eta=\alpha_0+\sum_i\alpha_ix_i$  
### Choosing a limit price  
I decided to use a simple model, where I'm just sampling  
$\text{Limit price}\sim\text{Exp}(\lambda)$
