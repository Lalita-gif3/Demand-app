import pandas as pd
raw_df = pd.read_csv("/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/extended_ecommerce_dataset.csv")
print("Raw Opening Stock Level Summary:")
print(raw_df["Opening Stock Level"].describe())
print("\nNon-numeric values:")
print(raw_df[~raw_df["Opening Stock Level"].apply(lambda x: isinstance(x, (int, float)))]["Opening Stock Level"].value_counts())
print("\nMissing values:", raw_df["Opening Stock Level"].isna().sum())
print("\nZero values count:", (raw_df["Opening Stock Level"] == 0).sum())