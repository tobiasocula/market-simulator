I wanted to expand upon my last simulation engine by improving the price generation process and fix some mistakes I've made, as well as add a custom option order generator.  
In my last engine, described in the "continuous_trading_with_ui/clientImplementation2" folder, I used a Poisson distribution with a variable $\lambda$ parameter.  
However, this was a crucial mistake, since this violates the memorylessness attribute of the distribution, by using a variable and not a constant parameter.  
Therefor, my aim was to improve upon this design and fix these mistakes.  
For the option order generation algorithm, I first thought to use a simple model, where a time interval $\Delta t$ gets sampled from an exponential distribution.  
However, realising that the buying and selling of option contracts are correlated between contracts and orders within the same contract, I did some research for a different approach,
and decided to use a Hawkes proces: https://en.wikipedia.org/wiki/Hawkes_process.  
This can be used to model a so called self-exciting process, which means it's perfect for events that influence each other, for example the buying and selling of option contracts.
The Hawkes model uses the general formula  
$\lambda(t|m)=\mu+\sum_{t_i\lt t}\phi(t-t_i,m_i)$  
This function computes the intensity of a certain event that happened. In my case, this is a contract being exchanged. $\mu$ is the baseline intensity, and the sum thereafter determines the "extra" intensity of the event, dependent on the time that has passed and the "mark" $m$ of the event, being the characteristic of the event that will influence the intensity of the event.  
In the file "testing_options_order_flow" I expand on these experiments and determine a general formula to use within the simulation engine for option contracts.
