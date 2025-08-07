import numpy as np
import pandas as pd


# df = pd.DataFrame({
#     "price": np.random.uniform(0, 100, 10)
# })

# df = df.sort_values('price').reset_index(drop=True)

# rp = np.random.uniform(0, 100)


# if rp < df.loc[0, 'price']:
#     df = pd.DataFrame({'price': [rp] + df['price'].values.tolist()})
# elif rp > df.loc[len(df)-1, 'price']:
#     df = pd.DataFrame({'price': df['price'].values.tolist() + [rp]})
# else:
#     for idx, row in df.iterrows():
#         if row['price'] > rp:
#             df = pd.DataFrame({
#             "price": df.loc[:idx-1, "price"].values.tolist() + [rp] + df.loc[idx:, "price"].values.tolist()
#         })
#             break

# print(df)

s1 = pd.Series([0, 1, 2, 3])
df = pd.DataFrame({'a': s1})
print(df)
