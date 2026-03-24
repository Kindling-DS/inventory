import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from sqlalchemy import create_engine
from zoneinfo import ZoneInfo

# ---------- MySQL Configuration ----------
mysql_user = "kindling1"
mysql_password = ""
mysql_host = "192.168.88.193"
mysql_port = 3306
mysql_db = "kindling1"
mysql_table = "detailed_product_data"

engine = create_engine(
    f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}",
    pool_pre_ping=True,
    pool_recycle=3600,
)

# ---------- Safe SQL Writer ----------
def safe_to_sql(df, table):
    retries = 3
    for attempt in range(retries):
        try:
            with engine.begin() as conn:
                df.to_sql(table, conn, if_exists="append", index=False)
            return True
        except Exception as e:
            print("MySQL write error:", e)
            if attempt < retries - 1:
                print("Retrying MySQL connection...")
                engine.dispose()
                time.sleep(5)
            else:
                raise e

# ---------- API Configuration ----------
token_url = "https://accounts.iqmetrix.net/v1/oauth2/token"
auth_payload = {
    "grant_type": "password",
    "client_id": "Kindling.SelfIntegration",
    "client_secret": "",
    "username": "SelfIntegration.COVA.APIUser.Kindling",
    "password": "",
}

base_url = "https://api.covasoft.net/dataplatform"
company_id = "287921"
api_url = f"{base_url}/v1/Companies/{company_id}/DetailedProductData"

location_ids = [
    "337565","369139","346750","352270","359751",
    "377354","377353","377352","384462","396146"
]

location_mapping = {
    "369139": "Toronto West (Dundas)",
    "359751": "Milton",
    "346750": "Mississauga",
    "337565": "Hamilton",
    "352270": "Toronto North (Leaside)",
    "377353": "Oshawa",
    "396146": "Mountainside",
    "377352": "Toronto East (Beaches)",
    "384462": "Brampton"
}

page_size = 500
max_records = 1000000

# ---------- Main Loop ----------
while True:
    try:
        # ---------- Get Token ----------
        token_response = requests.post(token_url, data=auth_payload)
        if token_response.status_code != 200:
            print("Token failure:", token_response.text)
            time.sleep(3600)
            continue

        access_token = token_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        all_products = []

        # ---------- Loop Locations ----------
        for loc_id in location_ids:
            skip = 0
            while True:
                payload = {
                    "LocationId": loc_id,
                    "IncludeProductSkusAndUpcs": True,
                    "IncludeAvailability": True,
                    "IncludePricing": True,
                    "InStockOnly": True,
                    "Skip": skip,
                    "Top": page_size
                }

                response = requests.post(api_url, headers=headers, json=payload)
                if response.status_code != 200:
                    print("API failure:", response.text)
                    break

                data = response.json() or {}
                products = data.get("Products") or []

                if not products:
                    break

                for product in products:
                    product_name = product.get("Name", "NA")
                    sku = product.get("CatalogSku", "NA")
                    classification = product.get("ClassificationName", "NA")
                    unit_type = product.get("UnitType", "NA")

                    supplier_list = product.get("SupplierSkus") or []
                    availability_list = product.get("Availability") or [{}]

                    for av in availability_list:
                        location_name = location_mapping.get(str(av.get("LocationId")), "NA")
                        qty = av.get("InStockQuantity", 0)
                        unit_cost = av.get("UnitCost") or 0

                        for s in supplier_list:
                            raw_sku = s.get("SKU", "NA")

                            # DO NOT SPLIT OR JOIN — preserve exact format
                            supplier_sku = str(raw_sku).strip()
                            supplier_name = str(s.get("Supplier", "NA")).strip()

                            all_products.append({
                                "snapshot_date": datetime.now().date(),
                                "location": location_name,
                                "product": product_name,
                                "classification": classification,
                                "sku": sku,
                                "unit_type": unit_type,
                                "supplier": supplier_name,
                                "supplier_sku": supplier_sku,
                                "in_stock_qty": qty,
                                "in_stock_cost": qty * unit_cost
                            })

                skip += page_size
                print(f"{location_name} fetched: {skip}")

                if len(all_products) >= max_records:
                    break

        # ---------- Save to MySQL ----------
        if all_products:
            df = pd.DataFrame(all_products)

            # ---------- FULL GRANULAR AGGREGATION ----------
            agg_df = (
                df.groupby(
                    ["snapshot_date", "location", "product", "supplier", "supplier_sku"],
                    as_index=False
                )
                .agg({
                    "classification": "first",
                    "sku": "first",
                    "unit_type": "first",
                    "in_stock_qty": "sum",
                    "in_stock_cost": "sum"
                })
            )

            # ---------- Weighted Avg Cost ----------
            agg_df["avg_unit_cost_in_stock"] = (
                agg_df["in_stock_cost"] / agg_df["in_stock_qty"]
            ).replace([float("inf"), -float("inf")], 0).fillna(0)

            # ---------- Save ----------
            safe_to_sql(agg_df, mysql_table)

            print(f"{datetime.now()} - Saved {len(agg_df)} rows (FULL SKU GRANULARITY)")

        else:
            print(f"{datetime.now()} - No data retrieved")

    except Exception as e:
        print("Pipeline error:", e)
        engine.dispose()

    # ---------- Sleep Until Next Run ----------
    now = datetime.now(ZoneInfo("America/New_York"))
    next_run = now.replace(hour=12, minute=15, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)

    sleep_seconds = (next_run - now).total_seconds()
    print(f"Sleeping {sleep_seconds/3600:.2f} hours\n")
    time.sleep(sleep_seconds)
