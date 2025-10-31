### 1. Price modeling

The price direction bias does not decide the course of the actual asset price (in this case the last traded price), in the way that it automatically steers the market direction, but makes it such that the incoming orders will get placed higher or lower.  
The method I'm using here is Geometric Brownian Motion: https://en.wikipedia.org/wiki/Geometric_Brownian_motion  
The next target price gets calculated using  
$S_{t+\Delta t} = S_t\cdot\text{exp}((\mu-\frac{1}{2}\sigma^2)\Delta t+\sigma\sqrt{\Delta t}Z)$  
Where  
$Z\sim\mathcal{N}(0,1)$  
$\mu$ is the general market direction (positive means upsloping)  
$\sigma$ is the average market volatility  
$S_t$ is the price at timestamp $t$
This formula aims to simulate realictic market movements. The first term in the formula indicates general price direction, and the second one adds noise.

### 2. Volume modeling

The volume for each trade gets sampled from a lognormal distribution, so $\text{Vol}=\text{exp}(\mu+\sigma x)$ where $x\sim\mathcal{N}(0,1)$
This results in larger tails than usual, and aims to simulate things like iceberg orders and occasionally very large trades.

### 3. Order frequency modeling

I decided to implement two (slightly) different approaches here:
My first idea was to use an exponential distribution to sample waiting times between each order. The waiting period $\Delta t$ gets sampled using $\Delta t=\frac{-\text{ln}(u)}{\lambda_i}$, where $\lambda_i$ is specific for participant $i$ and $u\sim\mathcal{U}(0,1)$.
The second option here is to sample the amount of orders coming in, during a fixed time interval $\Delta t$. This amount $N_t$ follows a poisson distribution with parameter $\lambda_i$. However, here I used a variant $\lambda$ parameter for each participant, with it being time-dependent. I used the formula $\lambda(t)=\lambda_i+A\cdot\text{sin}(\frac{2\pi}{\text{CT}-\text{OT}}(t-\text{OT}-\text{Offset}))$, with OT and CT being market open time and market close time (in minutes here), respectively, and $A$ and Offset being tunable parameters. This makes the frequency of incoming orders dependent on daily activity (more activity during market open and close).
For both methods, the $\lambda_i$ parameter for each participant gets sampled from a normal distribution, with the mean and stdev being tunable.