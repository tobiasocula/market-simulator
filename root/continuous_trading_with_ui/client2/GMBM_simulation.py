
import numpy as np
import matplotlib.pyplot as plt

N_PRICES = 10_000
FIRST_PRICE = 100.0

# Annualized parameters
mu = 0.1 # pct per year
sigma = 0.1
steps_per_year = 252

# Convert to per-step parameters
dt = 1 / steps_per_year
prices = np.empty(N_PRICES)
prices[0] = FIRST_PRICE

for i in range(1, N_PRICES):
    Z = np.random.standard_normal()
    prices[i] = prices[i-1] * np.exp(
        (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z
    )


fig, ax = plt.subplots()
ax.plot(prices)
plt.show()