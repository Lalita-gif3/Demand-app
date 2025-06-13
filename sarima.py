import os
import io
import base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ray
from ray import serve
from fastapi import FastAPI
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from pmdarima import auto_arima
import joblib
import logging
import warnings
from pydantic import BaseModel
from datetime import datetime

# Setup paths
DATA_PATH = "/mnt/c/Users/lalit/OneDrive/Desktop/demand app/cleaned_dataset.csv"
MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=ConvergenceWarning)

# Load and validate data
try:
    df = pd.read_csv(DATA_PATH, parse_dates=["Date"], dtype={"Opening Stock Level": float, "Remaining Stock Level": float})
    PRODUCT_IDS = sorted(df["product_id"].dropna().unique())
    logger.info(f"Dataset loaded. Columns: {df.columns}")
    logger.info(f"Sample data:\n{df.head().to_string()}")
    for pid in PRODUCT_IDS:
        stock_data = df[df["product_id"] == pid][["Date", "Opening Stock Level", "Remaining Stock Level"]].tail(5)
        if stock_data["Opening Stock Level"].isna().any() or (stock_data["Opening Stock Level"] <= 0).any():
            logger.warning(f"Invalid Opening Stock Levels for {pid}:\n{stock_data.to_string()}")
        elif stock_data["Remaining Stock Level"].isna().any() or (stock_data["Remaining Stock Level"] < 0).any():
            logger.warning(f"Invalid remaining stock levels for {pid}:\n{stock_data.to_string()}")
        else:
            logger.info(f"Stock data for {pid}:\n{stock_data.to_string()}")
except Exception as e:
    logger.error(f"Error loading dataset: {e}")
    PRODUCT_IDS = []

# Exogenous variables for SARIMAX
EXOG_VARS = [
    "selling_price", "Seasonality_Score", "Revenue", "Demand_Volatility",
    "Purchase_Frequency", "Customer_Purchase_Frequency", "Sales_Lag_7",
    "Sales_Lag_30", "Sales_Lag_60", "Sales_Lag_90", "Sales_Rolling_Mean_7",
    "Sales_Rolling_Std_7", "Sales_EMA_7", "Profit_Margin", "Discount_Rate",
    "Holiday", "Quarter", "Is_Weekend"
]
EXOG_VARS = [var for var in EXOG_VARS if var in df.columns]

# Pydantic models
class PredictionRequest(BaseModel):
    product_id: str
    start_date: str
    end_date: str

class NewDataRequest(BaseModel):
    product_id: str
    date: str
    sales_volume: float
    opening_stock_level: int
    remaining_stock_level: int
    selling_price: float | None = None
    Seasonality: float | None = None
    Revenue: float | None = None
    Demand_Volatility: float | None = None
    Purchase_Frequency: int | None = None
    Customer_Purchase_Frequency: int | None = None
    Sales_Lag_7: int | None = None
    Sales_Lag_30: int | None = None
    Sales_Lag_60: int | None = None
    Sales_Lag_90: int | None = None
    Sales_Rolling_Mean_7: float | None = None
    Sales_Rolling_Std_7: float | None = None
    Sales_EMA_7: float | None = None
    Profit_Margin: float | None = None
    Discount_Rate: float | None = None
    Holiday: int | None = None
    Quarter: int | None = None
    Is_Weekend: int | None = None


# FastAPI app for Ray Serve
app = FastAPI()

@serve.deployment(name="ForecastingService", num_replicas=1)
@serve.ingress(app)
class ForecastingService:
    def __init__(self):
        self.df = df
        self.product_ids = PRODUCT_IDS
        self.fitted_models = {}

    def load_or_train_model(self, product_id):
        model_path = os.path.join(MODEL_DIR, f"sarima_{product_id}.pkl")

        if os.path.exists(model_path):
            logger.info(f"Loading cached model for {product_id}")
            return joblib.load(model_path)

        logger.info(f"Training new SARIMAX model for {product_id}")
        data = self.df[self.df["product_id"] == product_id]
        ts = data[["Date", "Sales Volume"]].set_index("Date").resample("D").sum().asfreq("D").fillna(method="ffill")["Sales Volume"]
        exog = data[EXOG_VARS].set_index(data["Date"]).resample("D").asfreq().fillna(method="ffill")

        if ts[ts > 0].count() < 14:
            raise ValueError(f"Insufficient data to train SARIMAX for {product_id}")

        auto_model = auto_arima(ts, exog=exog, seasonal=True, m=7, start_p=0, max_p=1, start_q=0, max_q=1,
                                start_P=0, max_P=1, start_Q=0, max_Q=1, d=1, D=1,
                                stepwise=True, suppress_warnings=True, trace=False)

        model = SARIMAX(ts, exog=exog, order=auto_model.order, seasonal_order=auto_model.seasonal_order,
                        enforce_stationarity=True, enforce_invertibility=True)
        fitted = model.fit(disp=False)
        joblib.dump(fitted, model_path)
        self.fitted_models[product_id] = fitted
        return fitted

    def forecast(self, product_id, start_date, end_date):
        if product_id not in self.product_ids:
            raise ValueError("Invalid product_id")

        if product_id not in self.fitted_models:
            self.fitted_models[product_id] = self.load_or_train_model(product_id)

        forecast_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
        dates = pd.date_range(start=start_date, end=end_date)
        
        # Prepare exogenous variables for forecasting
        data = self.df[self.df["product_id"] == product_id]
        exog_future = data[EXOG_VARS].set_index(data["Date"]).resample("D").asfreq().fillna(method="ffill")
        exog_future = exog_future.reindex(dates, method="ffill")
        
        forecast_vals = self.fitted_models[product_id].forecast(steps=forecast_days, exog=exog_future)
        forecast_vals = np.clip(forecast_vals,0, None)
        forecast_vals = np.round(forecast_vals).astype(int)  # Round forecasted demand to integers

        return pd.DataFrame({
            "product_id": product_id,
            "Date": dates,
            "Forecasted Demand": forecast_vals
        })

    def detect_stockout(self, product_id, forecast_df):
        history = self.df[self.df["product_id"] == product_id]
        if history.empty:
            raise ValueError(f"No historical data for {product_id}")

        start_date = forecast_df["Date"].min()
        end_date = forecast_df["Date"].max()
        
        inventory = history[["Date", "Opening Stock Level", "Remaining Stock Level"]].set_index("Date")
        inventory = inventory.resample("D").asfreq().fillna(method="ffill").reset_index()
        inventory = inventory[(inventory["Date"] >= start_date) & (inventory["Date"] <= end_date)]

        if inventory.empty:
            latest_stock = history["Opening Stock Level"].iloc[-1] if not history["Opening Stock Level"].empty else 0
            latest_remaining = history["Remaining Stock Level"].iloc[-1] if not history["Remaining Stock Level"].empty else 0
            dates = pd.date_range(start=start_date, end=end_date)
            inventory = pd.DataFrame({
                "Date": dates,
                "Opening Stock Level": latest_stock,
                "Remaining Stock Level": latest_remaining
            })
            logger.warning(f"No stock data for {product_id} in the range {start_date} to {end_date}. Using latest available stock levels.")

        merged = forecast_df.merge(inventory, on="Date", how="left")

        latest_stock = history["Opening Stock Level"].iloc[-1] if not history["Opening Stock Level"].empty else 0
        latest_remaining = history["Remaining Stock Level"].iloc[-1] if not history["Remaining Stock Level"].empty else 0
        merged["Opening Stock Level"] = merged["Opening Stock Level"].fillna(latest_stock)
        merged["Remaining Stock Level"] = merged["Remaining Stock Level"].fillna(latest_remaining)

        if merged["Opening Stock Level"].isna().any() or (merged["Opening Stock Level"] <= 0).all():
            logger.warning(f"Invalid Opening Stock Levels for {product_id}: {merged['Opening Stock Level'].tolist()}")
            return {
                "error": f"Invalid or zero Opening Stock Levels for {product_id}. Please update the dataset.",
                "dates": [], "forecasted_demand": [],
                "current_stock_level": [], "remaining_stock_level": [],
                "stockout": []
            }, ""

        if merged["Remaining Stock Level"].isna().any() or (merged["Remaining Stock Level"] < 0).any():
            logger.warning(f"Invalid remaining stock levels for {product_id}: {merged['Remaining Stock Level'].tolist()}")
            return {
                "error": f"Invalid remaining stock levels for {product_id}. Please update the dataset.",
                "dates": [], "forecasted_demand": [],
                "current_stock_level": [], "remaining_stock_level": [],
                "stockout": []
            }, ""

        simulated_remaining_stock = []
        stockout_flags = []
        remaining = merged["Remaining Stock Level"].iloc[0]

        for demand in merged["Forecasted Demand"]:
            stockout_flags.append(remaining - demand < 0)
            remaining = max(0, remaining - demand)
            remaining = round(remaining)  # Round remaining stock to integer
            simulated_remaining_stock.append(remaining)

        merged["Remaining Stock Level"] = simulated_remaining_stock
        merged["Stockout"] = stockout_flags
        merged["Date"] = merged["Date"].dt.strftime("%Y-%m-%d")

        logger.info(f"Merged DataFrame for {product_id}:\n{merged[['Date', 'Opening Stock Level', 'Remaining Stock Level', 'Forecasted Demand', 'Stockout']].to_string()}")

        return {
            "dates": merged["Date"].tolist(),
            "forecasted_demand": merged["Forecasted Demand"].tolist(),
            "current_stock_level": merged["Opening Stock Level"].astype(int).tolist(),
            "remaining_stock_level": merged["Remaining Stock Level"].astype(int).tolist(),
            "stockout": merged["Stockout"].tolist()
        }, self.plot_graph(merged, product_id)

    def plot_graph(self, df, product_id):
        plt.figure(figsize=(10, 4))
        plt.plot(df["Date"], df["Forecasted Demand"], label="Forecasted Demand", marker="o")
        plt.plot(df["Date"], df["Opening Stock Level"], label="Opening Stock Level", marker="x")
        plt.plot(df["Date"], df["Remaining Stock Level"], label="Remaining Stock Level", marker="s")
        plt.fill_between(df["Date"], 0, df["Forecasted Demand"], where=df["Stockout"], color="red", alpha=0.3, label="Stock-out Risk")
        plt.title(f"Demand vs Stock - {product_id}")
        plt.xlabel("Date")
        plt.ylabel("Units")
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    def calc_mae(self, product_id, forecast_df, start_date, end_date):
        actual = self.df[(self.df["product_id"] == product_id) & (self.df["Date"] >= start_date) & (self.df["Date"] <= end_date)][["Date", "Sales Volume"]]
        actual["Date"] = pd.to_datetime(actual["Date"])
        merged = forecast_df.merge(actual, on="Date", how="inner")
        if merged.empty:
            return None
        merged["abs_error"] = (merged["Forecasted Demand"] - merged["Sales Volume"]).abs()
        return round(merged["abs_error"].mean(), 2)

    @app.post("/predict")
    async def predict(self, req: PredictionRequest):
        try:
            start, end = pd.to_datetime(req.start_date), pd.to_datetime(req.end_date)
            if start >= end:
                raise ValueError("Start date must be before end date")

            forecast_df = self.forecast(req.product_id, req.start_date, req.end_date)
            forecast_result, plot = self.detect_stockout(req.product_id, forecast_df)

            if "error" in forecast_result:
                return {
                    "product_id": req.product_id,
                    "dates": [],
                    "forecasted_demand": [],
                    "current_stock_level": [],
                    "remaining_stock_level": [],
                    "stockout": [],
                    "plot_url": "",
                    "mae": None,
                    "product_ids": self.product_ids,
                    "error": forecast_result["error"]
                }

            mae = self.calc_mae(req.product_id, forecast_df, req.start_date, req.end_date)

            return {
                "product_id": req.product_id,
                "dates": forecast_result["dates"],
                "forecasted_demand": forecast_result["forecasted_demand"],
                "current_stock_level": forecast_result["current_stock_level"],
                "remaining_stock_level": forecast_result["remaining_stock_level"],
                "stockout": forecast_result["stockout"],
                "plot_url": f"data:image/png;base64,{plot}",
                "mae": mae,
                "product_ids": self.product_ids
            }
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {"error": str(e), "product_ids": self.product_ids}

    @app.post("/add_data")
    async def add_data(self, req: NewDataRequest):
        try:
            prev_data = self.df[self.df["product_id"] == req.product_id]
            reorder = prev_data["Reorder Point"].iloc[-1] if not prev_data.empty else 0
            lead_time = prev_data["Lead Time (Days)"].iloc[-1] if not prev_data.empty else 0

            new_row = {
                "product_id": req.product_id,
                "Date": pd.to_datetime(req.date),
                "Sales Volume": req.sales_volume,
                "Opening Stock Level": req.current_stock_level,
                "Remaining Stock Level": req.remaining_stock_level,
                "Reorder Point": reorder,
                "Lead Time (Days)": lead_time
            }
            for var in EXOG_VARS:
                new_row[var] = getattr(req, var, prev_data[var].iloc[-1] if var in prev_data and not prev_data.empty else 0)

            new_row = pd.DataFrame([new_row])
            self.df = pd.concat([self.df, new_row], ignore_index=True)
            self.df.to_csv(DATA_PATH, index=False)

            # Remove cached model to force retraining
            model_path = os.path.join(MODEL_DIR, f"sarima_{req.product_id}.pkl")
            if os.path.exists(model_path):
                os.remove(model_path)
            if req.product_id in self.fitted_models:
                del self.fitted_models[req.product_id]

            return {"message": "Data added successfully. Model will be updated lazily."}
        except Exception as e:
            logger.error(f"Add data error: {e}")
            return {"error": str(e)}

    @app.get("/products")
    async def get_products(self):
        return {"product_ids": self.product_ids}

if __name__ == "__main__":
    ray.init(address="auto")  # Connect to existing Ray cluster
    # Start Serve with HTTP options
    serve.start(http_options={"host": "0.0.0.0", "port": 8000})
    # Run the deployment
    serve.run(ForecastingService.bind())
    
