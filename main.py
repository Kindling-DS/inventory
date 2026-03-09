import requests
import pandas as pd
from datetime import datetime
import time
from sqlalchemy import create_engine

# ---------- MySQL Configuration ----------
mysql_user = "your_mysql_user"
mysql_password = "your_mysql_password"
mysql_host = "localhost"  # or your MySQL host
mysql_port = 3306
mysql_db = "your_database"
mysql_table = "detailed_product_data"

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
    "377354" : "Burlington",
    "377352": "Toronto East (Beaches)",
    "384462": "Brampton"
}

page_size = 500
max_records = 100_000_000

# ---------- Main Loop ----------
while True:
    # Get access token
    token_response = requests.post(token_url, data=auth_payload)
    if token_response.status_code != 200:
        print(f"Failed to retrieve access token: {token_response.text}")
        time.sleep(3600)  # retry in 1 hour
        continue

    access_token = token_response.json().get("access_token")
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    all_products = []

    # Loop over locations
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
                print(f"Failed for Location {loc_id}: {response.text}")
                break

            data = response.json()
            products = data.get("Products", [])
            if not products:
                break

            for product in products:
                product_id = product.get("ProductId", "N/A")
                master_product_name = product.get("MasterProductName", "N/A")
                name = product.get("Name", "N/A")
                sku = product.get("CatalogSku", "N/A")
                price = product.get("CompanyLevelRegularPrice", {}).get("Price", "N/A")
                short_description = product.get("ShortDescription", "N/A")

                for av in product.get("Availability", []):
                    location_name = location_mapping.get(str(av.get("LocationId", "")), "Unknown")
                    all_products.append({
                        "Product ID": product_id,
                        "Master Product Name": master_product_name,
                        "Name": name,
                        "SKU": sku,
                        "Price": price,
                        "Short Description": short_description,
                        "Location": location_name,
                        "In Stock Qty": av.get("InStockQuantity", 0),
                        "Unit Cost": av.get("UnitCost", "N/A"),
                        "Last Updated": av.get("UpdatedDateUtc", "N/A"),
                    })

            skip += page_size
            if len(all_products) >= max_records:
                break

    # Save to MySQL
    if all_products:
        df = pd.DataFrame(all_products)
        df.to_sql(mysql_table, con=engine, if_exists='replace', index=False)
        print(f"{datetime.now()} - Saved {len(df)} records to MySQL table '{mysql_table}'")
    else:
        print(f"{datetime.now()} - No product data retrieved.")

    # Sleep for 24 hours
    time.sleep(86400)
