import pandas as pd
import numpy as np

# Loading the dataset
input_path = "/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/Cleaned_Complete_Ecommerce_Data (1).xlsx"
output_path = "/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/cleaned_dataset.csv"

# Reading the CSV file
try:
    df = pd.read_excel(input_path)
except Exception as e:
    print(f"❌ Failed to read CSV file: {e}")
    exit(1)

# Keeping only the required columns
columns_to_keep = [
    "product_id", "Date", "Sales Volume", "Opening Stock Level",
    "Reorder Point", "Lead Time (Days)", "Stock-out Date", "Remaining Stock Level"
]
df = df[columns_to_keep]

# Debug: Check initial data
print(f"Initial data shape: {df.shape}")
print(f"Initial product IDs: {df['product_id'].unique()}")

# Converting date columns to datetime, handling invalid formats
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df["Stock-out Date"] = pd.to_datetime(df["Stock-out Date"], errors="coerce")

# Debug: Check for invalid dates
invalid_dates = df[df["Date"].isna()]
if not invalid_dates.empty:
    print(f"⚠️ Found {len(invalid_dates)} rows with invalid dates:")
    print(invalid_dates[["product_id", "Date"]].to_string())

# Dropping rows with invalid dates
df = df.dropna(subset=["Date"])

# Debug: After dropping invalid dates
print(f"Data shape after dropping invalid dates: {df.shape}")

# Ensuring numeric and non-negative values for key columns
df["Sales Volume"] = pd.to_numeric(df["Sales Volume"], errors="coerce").fillna(0)
df["Opening Stock Level"] = pd.to_numeric(df["Opening Stock Level"], errors="coerce").fillna(0)
df["Remaining Stock Level"] = pd.to_numeric(df["Remaining Stock Level"], errors="coerce").fillna(0)
df["Reorder Point"] = pd.to_numeric(df["Reorder Point"], errors="coerce").fillna(0)
df["Lead Time (Days)"] = pd.to_numeric(df["Lead Time (Days)"], errors="coerce").fillna(0)

# Filtering out rows with negative values (keep Sales Volume >= 0 to retain zero sales)
df = df[df["Sales Volume"] >= 0]  # Changed from > 0 to >= 0
df = df[df["Opening Stock Level"] >= 0]
df = df[df["Remaining Stock Level"] >= 0]
df = df[df["Reorder Point"] >= 0]
df = df[df["Lead Time (Days)"] >= 0]

# Debug: After filtering non-negative values
print(f"Data shape after filtering non-negative values: {df.shape}")

# Validate that Remaining Stock Level is less than or equal to Opening Stock Level
invalid_stock_rows = df[df["Remaining Stock Level"] > df["Opening Stock Level"]]
if not invalid_stock_rows.empty:
    print(f"⚠️ Warning: Found {len(invalid_stock_rows)} rows where Remaining Stock Level > Opening Stock Level:")
    print(invalid_stock_rows[["product_id", "Date", "Opening Stock Level", "Remaining Stock Level"]].to_string())
    df.loc[df["Remaining Stock Level"] > df["Opening Stock Level"], "Remaining Stock Level"] = df["Opening Stock Level"]

# Resample data to daily frequency for each product to ensure no gaps
df_list = []
for product_id in df["product_id"].unique():
    product_df = df[df["product_id"] == product_id].set_index("Date")
    # Resample to daily frequency and forward-fill missing values
    product_df = product_df.resample("D").asfreq().fillna(method="ffill").reset_index()
    df_list.append(product_df)

# Concatenate the resampled data
df = pd.concat(df_list, ignore_index=True)

# Debug: After resampling
print(f"Data shape after resampling: {df.shape}")

# Sorting by product_id and Date
df = df.sort_values(by=["product_id", "Date"])

# Validating data sufficiency per product
min_data_points = 30  # Minimum number of data points for SARIMA
product_counts = df.groupby("product_id").size()
valid_products = product_counts[product_counts >= min_data_points].index
df = df[df["product_id"].isin(valid_products)]

# Debug: Check data for the specific date range (2024-04-22 to 2024-04-29)
date_range_data = df[(df["Date"] >= "2024-04-22") & (df["Date"] <= "2024-04-29")]
if date_range_data.empty:
    print("⚠️ No data found in the range 2024-04-22 to 2024-04-29. Check the date range in your dataset.")
else:
    print(f"Data in range 2024-04-22 to 2024-04-29:\n{date_range_data.to_string()}")

if df.empty:
    print("❌ No products have sufficient data points (minimum 30).")
    exit(1)

# Saving the cleaned dataset
df.to_csv(output_path, index=False)
print(f"✅ Cleaned data saved as '{output_path}'")
print(f"Number of valid products: {len(valid_products)}")
print(f"Sample data:\n{df.head().to_string()}")