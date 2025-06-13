import pandas as pd
import numpy as np

# File paths
input_path = "/mnt/c/Users/lalit/OneDrive/Desktop/demand app/Cleaned_Complete_Ecommerce_Data.xlsx"
output_path = "/mnt/c/Users/lalit/OneDrive/Desktop/demand app/cleaned_dataset.csv"

# Reading the Excel file
try:
    df = pd.read_excel(input_path)
except Exception as e:
    print(f"❌ Failed to read Excel file: {e}")
    exit(1)

# Define columns to keep, including additional features
columns_to_keep = [
    "product_id", "Date", "Sales Volume", "Opening Stock Level", "Reorder Point", 
    "Lead Time (Days)", "Stock-out Date", "Remaining Stock Level", "selling_price", 
    "Seasonality", "Revenue", "product_name", "category", "brand", "cost_price", 
    "discount", "product_lifecycle", "supplier_name", "reliability_score", 
    "Delivery_time", "defect_rate", "Purchase Frequency", "Customer_Purchase_Frequency", 
    "Demand_Volatility", "Price_Elasticity", "Sales_Lag_60", "Sales_Lag_90", 
    "Sales_Rolling_Mean_7", "Sales_Rolling_Std_7", "Sales_EMA_7", "Holiday", 
    "Quarter", "shipping_method", "estimated_delivery_days", "delay_days", 
    "On-Time Delivery Rate (%)", "Order Fulfillment Time (Days)"
]
# Filter columns that exist in the dataset
columns_to_keep = [col for col in columns_to_keep if col in df.columns]
df = df[columns_to_keep]

# Debug: Check initial data
print(f"Initial data shape: {df.shape}")
print(f"Initial product IDs: {df['product_id'].unique()}")

# Convert date columns to datetime
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df["Stock-out Date"] = pd.to_datetime(df["Stock-out Date"], errors="coerce")

# Debug: Check for invalid dates
invalid_dates = df[df["Date"].isna()]
if not invalid_dates.empty:
    print(f"⚠️ Found {len(invalid_dates)} rows with invalid dates:")
    print(invalid_dates[["product_id", "Date"]].to_string())

# Impute invalid dates with the earliest date for each product
if not invalid_dates.empty:
    df["Date"] = df.groupby("product_id")["Date"].transform(lambda x: x.fillna(x.min()))
    print(f"Imputed {len(invalid_dates)} invalid dates with product-specific earliest date.")

# Debug: After handling invalid dates
print(f"Data shape after handling invalid dates: {df.shape}")

# Ensure numeric and non-negative values for key columns
numeric_columns = [
    "Sales Volume", "Opening Stock Level", "Remaining Stock Level", "Reorder Point", 
    "Lead Time (Days)", "selling_price", "Revenue", "cost_price", "discount", 
    "reliability_score", "Delivery_time", "defect_rate", "Purchase Frequency", 
    "Customer_Purchase_Frequency", "Demand_Volatility", "Price_Elasticity", 
    "Sales_Lag_60", "Sales_Lag_90", "Sales_Rolling_Mean_7", "Sales_Rolling_Std_7", 
    "Sales_EMA_7", "estimated_delivery_days", "delay_days", "On-Time Delivery Rate (%)", 
    "Order Fulfillment Time (Days)"
]
numeric_columns = [col for col in numeric_columns if col in df.columns]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df[col] = df[col].clip(lower=0)  # Ensure non-negative values without dropping rows

# Debug: After ensuring non-negative values
print(f"Data shape after ensuring non-negative values: {df.shape}")

# Validate Remaining Stock Level <= Opening Stock Level
invalid_stock_rows = df[df["Remaining Stock Level"] > df["Opening Stock Level"]]
if not invalid_stock_rows.empty:
    print(f"⚠️ Warning: Found {len(invalid_stock_rows)} rows where Remaining Stock Level > Opening Stock Level:")
    print(invalid_stock_rows[["product_id", "Date", "Opening Stock Level", "Remaining Stock Level"]].to_string())
    df.loc[df["Remaining Stock Level"] > df["Opening Stock Level"], "Remaining Stock Level"] = df["Opening Stock Level"]

# Resample data to daily frequency for each product
df_list = []
for product_id in df["product_id"].unique():
    product_df = df[df["product_id"] == product_id].set_index("Date")
    product_df = product_df.resample("D").asfreq().fillna(method="ffill").reset_index()
    df_list.append(product_df)

# Concatenate resampled data
df = pd.concat(df_list, ignore_index=True)

# Debug: After resampling
print(f"Data shape after resampling: {df.shape}")

# Sort by product_id and Date
df = df.sort_values(by=["product_id", "Date"])

# Add demand and inventory-related features
df["Sales_Lag_7"] = df.groupby("product_id")["Sales Volume"].shift(7)
df["Sales_Lag_30"] = df.groupby("product_id")["Sales Volume"].shift(30)
df["Rolling_Sales_7"] = df.groupby("product_id")["Sales Volume"].transform(lambda x: x.shift(1).rolling(7).mean())
df["Rolling_Sales_30"] = df.groupby("product_id")["Sales Volume"].transform(lambda x: x.shift(1).rolling(30).mean())
df["Sales_Diff_1"] = df.groupby("product_id")["Sales Volume"].diff(1)

# Avoid division by zero
df["Stock_Turnover"] = df["Sales Volume"] / df["Opening Stock Level"].replace(0, np.nan)
df["Stock_Turnover"] = df["Stock_Turnover"].fillna(0)

# Days until stockout
df["Days_Until_Stockout"] = df["Remaining Stock Level"] / df["Sales Volume"].replace(0, np.nan)
df["Days_Until_Stockout"] = df["Days_Until_Stockout"].fillna(np.inf)

# Flags
df["Is_Stockout"] = (df["Remaining Stock Level"] == 0).astype(int)
df["Is_Reorder_Triggered"] = (df["Opening Stock Level"] <= df["Reorder Point"]).astype(int)

# Calendar features
df["Day_of_Week"] = df["Date"].dt.dayofweek
df["Week_of_Year"] = df["Date"].dt.isocalendar().week
df["Month"] = df["Date"].dt.month
df["Is_Weekend"] = df["Day_of_Week"].isin([5, 6]).astype(int)

# Product-level feature: total popularity
product_popularity = df.groupby("product_id")["Sales Volume"].sum().rename("Product_Popularity")
df = df.merge(product_popularity, on="product_id", how="left")

# Compute average sales per weekday per product (weekly seasonality)
seasonality = df.groupby(["product_id", "Day_of_Week"])["Sales Volume"].mean().reset_index()
seasonality.columns = ["product_id", "Day_of_Week", "Seasonality_Score"]
df = df.merge(seasonality, on=["product_id", "Day_of_Week"], how="left")

# Additional feature: Profit margin
if "selling_price" in df.columns and "cost_price" in df.columns:
    df["Profit_Margin"] = (df["selling_price"] - df["cost_price"]) / df["selling_price"].replace(0, np.nan)
    df["Profit_Margin"] = df["Profit_Margin"].fillna(0)

# Additional feature: Discount rate
if "discount" in df.columns and "selling_price" in df.columns:
    df["Discount_Rate"] = df["discount"] / df["selling_price"].replace(0, np.nan)
    df["Discount_Rate"] = df["Discount_Rate"].fillna(0)

# --- Handle NaN and Inf Values ---

# 1. Identify columns with NaN or Inf
print("Columns with NaN values before imputation:")
print(df.isna().sum())
print("\nColumns with Inf values before imputation:")
print(df.select_dtypes(include=[np.number]).apply(lambda x: np.isinf(x)).sum())

# 2. Impute NaN in lag and rolling features with product-specific mean
lag_rolling_cols = ["Sales_Lag_7", "Sales_Lag_30", "Rolling_Sales_7", "Rolling_Sales_30", "Sales_Diff_1"]
for col in lag_rolling_cols:
    if col in df.columns:
        df[col] = df.groupby("product_id")[col].transform(lambda x: x.fillna(x.mean()))
        # If mean is still NaN (e.g., all values are NaN), fill with 0
        df[col] = df[col].fillna(0)

# 3. Handle NaN and Inf in Stock_Turnover and Days_Until_Stockout
df["Stock_Turnover"] = df["Stock_Turnover"].replace([np.inf, -np.inf], 0).fillna(0)
df["Days_Until_Stockout"] = df["Days_Until_Stockout"].replace([np.inf, -np.inf], 1e6).fillna(1e6)

# 4. Handle NaN in Profit_Margin and Discount_Rate
if "Profit_Margin" in df.columns:
    df["Profit_Margin"] = df["Profit_Margin"].replace([np.inf, -np.inf], 0).fillna(0)
if "Discount_Rate" in df.columns:
    df["Discount_Rate"] = df["Discount_Rate"].replace([np.inf, -np.inf], 0).fillna(0)

# 5. Impute NaN in other numeric features with product-specific median
numeric_cols = [
    "Demand_Volatility", "Price_Elasticity", "Sales_Lag_60", "Sales_Lag_90", 
    "Sales_Rolling_Mean_7", "Sales_Rolling_Std_7", "Sales_EMA_7", 
    "estimated_delivery_days", "delay_days", "On-Time Delivery Rate (%)", 
    "Order Fulfillment Time (Days)"
]
numeric_cols = [col for col in numeric_cols if col in df.columns]
for col in numeric_cols:
    df[col] = df.groupby("product_id")[col].transform(lambda x: x.fillna(x.median()))
    df[col] = df[col].fillna(0)  # Fallback to 0 if median is NaN

# 6. Forward-fill and backward-fill for time-series features like Seasonality_Score
if "Seasonality_Score" in df.columns:
    df["Seasonality_Score"] = df.groupby("product_id")["Seasonality_Score"].fillna(method="ffill").fillna(method="bfill")
    df["Seasonality_Score"] = df["Seasonality_Score"].fillna(0)  # Fallback if all values are NaN

# 7. Handle categorical columns
categorical_cols = ["category", "brand", "supplier_name", "shipping_method", "product_name", "product_lifecycle"]
categorical_cols = [col for col in categorical_cols if col in df.columns]
for col in categorical_cols:
    df[col] = df[col].fillna("Unknown")

# 8. Verify no NaN or Inf remains
print("\nColumns with NaN values after imputation:")
print(df.isna().sum())
print("\nColumns with Inf values after imputation:")
print(df.select_dtypes(include=[np.number]).apply(lambda x: np.isinf(x)).sum())

# Validate data sufficiency per product
min_data_points = 365  # Ensure exactly 365 days per product
product_counts = df.groupby("product_id").size()
valid_products = product_counts[product_counts == min_data_points].index
df = df[df["product_id"].isin(valid_products)]

# Debug: Check data for specific date range
date_range_data = df[(df["Date"] >= "2024-04-22") & (df["Date"] <= "2024-04-29")]
if date_range_data.empty:
    print("⚠️ No data found in the range 2024-04-22 to 2024-04-29.")
else:
    print(f"Data in range 2024-04-22 to 2024-04-29:\n{date_range_data.head().to_string()}")

if df.empty:
    print("❌ No products have sufficient data points (exactly 365).")
    exit(1)

# Save the cleaned dataset
df.to_csv(output_path, index=False)
print(f"✅ Cleaned data with additional features saved as '{output_path}'")
print(f"Number of valid products: {len(valid_products)}")
print(f"Sample data:\n{df.head().to_string()}")