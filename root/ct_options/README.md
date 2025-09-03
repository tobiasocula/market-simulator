I wanted to expand upon my last simulation engine by improving the price generation process and fix some mistakes I've made, as well as add a custom option order generator.  
### Frequency of trades   
In my last engine, described in the "continuous_trading_with_ui/clientImplementation2" folder, I used a Poisson distribution with a variable $\lambda$ parameter for determining the frequency of trades.    
However, this was a crucial mistake, since this violates the memorylessness attribute of the distribution, by using a variable and not a constant parameter.  
Therefor, my aim was to improve upon this design and fix these mistakes.  
For the option order generation algorithm, I first thought to use a simple model, where a time interval $\Delta t$ gets sampled from an exponential distribution.  
However, realising that the buying and selling of option contracts are correlated between contracts and orders within the same contract, I did some research for a different approach, and decided to use a Hawkes proces: https://en.wikipedia.org/wiki/Hawkes_process.  
This can be used to model a so called self-exciting process, which means it's perfect for events that influence each other, for example the buying and selling of option contracts.
The Hawkes model uses the general formula  
$\lambda(t|m)=\mu+\sum_{t_i\lt t}\phi(t-t_i,m_i)$  
This function computes the intensity of a certain event that happened. In my case, this is a contract being exchanged. $\mu$ is the baseline intensity, and the sum thereafter determines the "extra" intensity of the event, dependent on the time that has passed and the "mark" $m$ of the event, being the characteristic of the event that will influence the intensity of the event.  
In the file "testing_options_order_flow" I expand on these experiments and determine a general formula to use within the simulation engine for option contracts.
### Volume determination for each event  
There are a few possibilities for determining the volume of an exchanged contract. One option is like I did in the previous engine for buying and selling assets, which is to sample it from a lognormal distribution with parameters a certain mean and std value. However, in this case, I want the volume to be influenced by factors like the moneyness and time decay, which makes it more realistic (more volume at ATM then far away from it, and more volume for short-term expiry options). My first idea is to use the following:  
$\text{Volume}=b\cdot\text{exp}(-a\cdot (S/K-1)-c\cdot T)$  
where $a$, $b$ and $c$ are parameters, $S$ is the asset price, $K$ is the strike and $T$ is the time until expiry (years).  
After seeking to improve this formula, by introducing randomness (I realised my formula was completely deterministic) and using log-moneyness instead, to make sure that distances from either side of ATM were treated equally (I read about this at https://en.wikipedia.org/wiki/Moneyness, and https://quant.stackexchange.com/questions/59421/why-use-moneyness-as-an-axis-on-a-volatility-surface), I'm now using  
$\text{Volume}=X\cdot b\cdot L_k\cdot\text{exp}(-a\cdot |\text{log}(S/K)|-c\cdot T)$  
I've now added $X\sim\text{lognormal}(\mu_X,\sigma_X)$ and $L_k$, the contract-specific liquidity.
