import pandas as pd
import numpy as np

df = pd.DataFrame([
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
    [10, 11, 12]
], index=[1, 0, 0, 1], columns=list("abc"))
print(df)

df.loc[df.index[0], "a"] = 99

print(df)