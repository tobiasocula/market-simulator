Financial market simulation engine.
There are currently three simulation enginges:
1. Periodic call auction
This market principle allows market participants to send orders before the market opens, and during the "trading" session these orders are executed when price matches.
At market open, the open price is calculated by calculating the cumulative bid and ask volume. Then trades are executed.
My implementation uses a very simple matching algorithm, which just compares prices directly.
Reference: https://www.icicidirect.com/faqs/stocks/what-is-periodic-call-auction-pca-and-how-does-it-work
2. Continuous market trading environment
Market participants can continuously send orders and trades are exected continuously.
Traders can send orders before market open, and when the market opens these trades are executed. Participants can then send orders when they want.
The market is represented as a FastAPI backend. The open price gets calculated in a similar way as the PCA environment.
3. Same as above, but with GUI + much better implementation
This uses a React frontend application alongside with the FastAPI backend, meaning one can see the order book get updated in real time. There are also two order generation algorithms being used.
