import numpy as np
import pandas as pd


df = pd.DataFrame({
    "price": np.random.uniform(0, 100, 10)
})

df = df.sort_values('price').reset_index(drop=True)

#rp = np.random.uniform(0, 100)
rp = df.iloc[len(df)-1]['price']+0.001

for idx, row in df.iterrows():
    if row['price'] > rp and idx != 0:

        print('p1:'); print(df.loc[:idx, "price"])
        print('p2:'); print(df.loc[idx+1:, "price"])
        newdf = pd.DataFrame({
            "price": df.loc[:idx-1, "price"].values.tolist() + [rp] + df.loc[idx:, "price"].values.tolist()
        })
        print('newdf:')
        print(newdf)
        break


        

        