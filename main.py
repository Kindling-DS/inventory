import requests
import pandas as pd
from datetime import datetime
import time
from sqlalchemy import create_engine

# ---------- MySQL Configuration ----------
mysql_user = "kindling1"
mysql_password = ""
mysql_host = "192.168.88.193"  # or your MySQL host
mysql_port = 3306
mysql_db = "kindling1"
mysql_table = "detailed_product_data"

engine = create_engine(f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}")

from sqlalchemy import create_engine, text

engine = create_engine(f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}")

  
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

location_ids = ["337565", "369139", "346750", "352270", "359751","377354","377353","377352","384462"]

location_mapping = {
    "369139": "Toronto West (Dundas)",
    "359751": "Milton",
    "346750": "Mississauga",
    "337565": "Hamilton",
    "352270": "Toronto North (Leaside)",
    "377353": "Oshawa",
    "377354": "Burlington",
    "377352": "Toronto East (Beaches)",
    "384462": "Brampton"
}

page_size = 500
max_records = 1000000

# ---------- Main Loop ----------
while True:

    # ---------- Get Access Token ----------
    token_response = requests.post(token_url, data=auth_payload)

    if token_response.status_code != 200:
        print("Failed to retrieve access token:", token_response.text)
        time.sleep(3600)
        continue

    access_token = token_response.json().get("access_token")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

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
                print(f"API failure for location {loc_id}: {response.text}")
                break

            data = response.json() or {}
            products = data.get("Products") or []

            if not products:
                break

            # ---------- Extract Product Data ----------
            for product in products:

                product_name = product.get("Name")
                sku = product.get("CatalogSku")

                classification = product.get("ClassificationName")

                supplier = (product.get("PrimaryVendor") or {}).get("Name")
                supplier_sku = (product.get("PrimaryVendor") or {}).get("VendorSku")

                availability_list = product.get("Availability") or []

                for av in availability_list:

                    if not av:
                        continue

                    location_name = location_mapping.get(
                        str(av.get("LocationId")), "Unknown"
                    )

                    qty = av.get("InStockQuantity", 0)
                    unit_cost = av.get("UnitCost") or 0

                    all_products.append({

                        "snapshot_date": datetime.now().date(),
                        "location": location_name,
                        "product": product_name,
                        "classification": classification,
                        "sku": sku,
                        "in_stock_qty": qty,
                        "unit_type": product.get("UnitType"),
                        "in_stock_cost": qty * unit_cost,
                        "avg_unit_cost_in_stock": unit_cost,
                        "supplier": supplier,
                        "supplier_sku": supplier_sku
                    })

            skip += page_size
            print("Fetched records:", skip)

            if len(all_products) >= max_records:
                break

    # ---------- Save to MySQL ----------
    if all_products:

        df = pd.DataFrame(all_products)
        # Add daily snapshot date
        df["snapshot_date"] = datetime.now().date()

        df.to_sql(
            mysql_table,
            con=engine,
            if_exists="append",
            index=False
        )

        print(
            f"{datetime.now()} - Saved {len(df)} rows to MySQL"
        )

    else:
        print(f"{datetime.now()} - No data retrieved")

    # ---------- Run Every 24 Hours ----------
    time.sleep(86400)
