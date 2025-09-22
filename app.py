import os
import requests
from flask import Flask, render_template, jsonify, request
from datetime import datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash

load_dotenv()
app = Flask(__name__)

# Shopify credentials
SHOPIFY_STORE_URL = os.getenv('SHOPIFY_STORE_URL')
SHOPIFY_ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')
SHOPIFY_API_VERSION = os.getenv('SHOPIFY_API_VERSION', "2024-07")

# Login credentials
app.secret_key = os.getenv('app.secret_key')
HARDCODED_USERNAME = os.getenv('HARDCODED_USERNAME')
HARDCODED_PASSWORD = os.getenv('HARDCODED_PASSWORD')

print(f"DEBUG: Shopify token loaded (last 8 chars): {SHOPIFY_ACCESS_TOKEN[-8:]}")

@app.route('/')
def home():
    return render_template('dashboard.html')
    
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get form data
        username = request.form['username']
        password = request.form['password']

        # Check if credentials are correct
        if username == HARDCODED_USERNAME and password == HARDCODED_PASSWORD:
            # If correct, "log the user in" by storing their username in the session
            session['username'] = username
            flash('You were successfully logged in!', 'success')
            return redirect(url_for('index'))
        else:
            # If incorrect, show an error message
            flash('Invalid credentials. Please try again.', 'danger')
            return redirect(url_for('login'))

    # If it's a GET request, just show the login form
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Remove the username from the session to "log the user out"
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/scanpack')
def index():

    if 'username' not in session:
        # If not, flash a message and redirect to the login page
        flash('You must be logged in to access the Scanpack app.', 'danger')
        return redirect(url_for('login'))
    
    return render_template('index.html')

@app.route('/api/get_order/<order_identifier>', methods=['GET'])
def get_order(order_identifier):
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }

    shopify_url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
    params = {"status": "any"}
    is_tracking_search = not (order_identifier.isdigit() or order_identifier.startswith("#"))
    if not is_tracking_search:
        params["name"] = f"#{order_identifier}" if not str(order_identifier).startswith("#") else order_identifier

    try:
        print(f"[API CALL] Fetching orders with params: {params}")
        response = requests.get(shopify_url, headers=headers, params=params)
        response.raise_for_status()
        orders = response.json().get("orders", [])

        order = None
        if is_tracking_search:
            for o in orders:
                if any(order_identifier == f.get("tracking_number") for f in o.get("fulfillments", [])):
                    order = o
                    break
        elif orders:
            order = orders[0]

        if not order:
            return jsonify({"error": "Order not found"}), 404

        line_items = []
        # Caches to avoid re-fetching data for the same product/variant in one order
        image_cache = {}
        variant_cache = {}

        for item in order.get('line_items', []):
            product_id = item.get('product_id')
            variant_id = item.get('variant_id')
            
            # Default values
            inventory_item_id = None
            available_quantity = 0
            in_stock = False

            if variant_id:
                # Check if we already fetched details for this variant
                if variant_id in variant_cache:
                    inventory_item_id = variant_cache[variant_id]
                    print(f"[CACHE HIT] Using cached inventory_item_id for variant {variant_id}")
                else:
                    # STEP 1: Fetch full variant details to get the inventory_item_id
                    print(f"[DEBUG] Fetching variant details for variant_id: {variant_id}...")
                    variant_url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
                    variant_resp = requests.get(variant_url, headers=headers)

                    if variant_resp.status_code == 200:
                        variant_data = variant_resp.json().get("variant", {})
                        inventory_item_id = variant_data.get("inventory_item_id")
                        # Cache the result for future use
                        variant_cache[variant_id] = inventory_item_id
                        print(f"[DEBUG] Found inventory_item_id: {inventory_item_id}")
                    else:
                        print(f"[ERROR] Failed to fetch variant details for {variant_id}. Status: {variant_resp.status_code}")
            
            if inventory_item_id:

                print("\n" + "="*50)
                print(f"[DEBUG] CHECKING INVENTORY FOR: '{item.get('title')}'")
                
                inventory_url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/inventory_levels.json"
                inv_params = {"inventory_item_ids": [str(inventory_item_id)]}
                
                try:
                    inv_resp = requests.get(inventory_url, headers=headers, params=inv_params)
                    inv_resp.raise_for_status() 

                    levels = inv_resp.json().get("inventory_levels", [])
                    if levels:
                        available_quantity = sum(level.get("available", 0) for level in levels if level.get("available") is not None)
                        in_stock = available_quantity > 0
                        print(f"[OK] {item.get('title')} | Total Available: {available_quantity}")
                    else:
                        print(f"[NO LEVELS FOUND] {item.get('title')} — API returned an empty list.")
                except requests.exceptions.HTTPError as e:
                    print(f"[API ERROR] Inventory check failed. Details: {e.response.text}")
                
                print("="*50 + "\n")
            else:

                print(f"[SKIPPED] Could not find inventory_item_id for variant {variant_id}.")


            # Fetch product image logic...
            if product_id and product_id not in image_cache:
                product_url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{product_id}.json?fields=images"
                prod_resp = requests.get(product_url, headers=headers)
                if prod_resp.status_code == 200:
                    product_data = prod_resp.json().get("product")
                    if product_data and product_data.get("images"):
                        image_url = next((img["src"] for img in product_data["images"] if variant_id in img.get("variant_ids", [])), None)
                        if not image_url: image_url = product_data["images"][0].get("src")
                image_cache[product_id] = image_url
            
            final_image_url = image_cache.get(product_id)

            # Extract Customized Name if present
            customized_name = ""
            for prop in item.get("properties", []):
                if prop.get("name") == "Customized Name":
                    customized_name = prop.get("value")
                    break

            line_items.append({
                "product_id": product_id,
                "variant_id": variant_id,
                "title": item.get('title'),
                "quantity": item.get('quantity'),
                "sku": item.get('sku'),
                "size": item.get('variant_title'),
                "product_image": final_image_url,
                "in_stock": in_stock,
                "available_quantity": available_quantity,
                "customized_name": customized_name  # <- NEW
            })

        return jsonify({
            "order_id": order.get('id'),
            "order_name": order.get('name'),
            "line_items": line_items,
            "fulfillment_status": order.get('fulfillment_status'),
            "tags": order.get('tags', '')
        })

    except requests.exceptions.HTTPError as e:
        return jsonify({"error": "Shopify API error", "details": e.response.text}), e.response.status_code
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# The tag_order_as_packed function remains the same

@app.route('/api/fulfill_order/<order_id>', methods=['POST'])
def tag_order_as_packed(order_id):
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    order_url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/orders/{order_id}.json"

    try:
        # Get existing tags
        response = requests.get(order_url, headers=headers, params={"fields": "tags"})
        response.raise_for_status()
        order = response.json().get('order')
        existing_tags = order.get("tags", "")

        # ✅ Daily tag only (Pakistan timezone)
        today_tag = datetime.now(ZoneInfo("Asia/Karachi")).strftime("Packed-%Y-%m-%d")

        # Avoid duplicate tags
        tag_list = [tag.strip() for tag in existing_tags.split(",") if tag.strip()]
        if today_tag not in tag_list:
            tag_list.append(today_tag)

        updated_tags = ", ".join(tag_list)

        # Update order with new tags
        update_payload = {"order": {"id": order_id, "tags": updated_tags}}
        update_response = requests.put(order_url, headers=headers, json=update_payload)
        update_response.raise_for_status()

        return jsonify({"message": "Order tagged successfully", "tag": today_tag})

    except requests.exceptions.HTTPError as e:
        return jsonify({"error": "Shopify API error", "details": e.response.text}), e.response.status_code
    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500
if __name__ == '__main__':
    app.run(debug=True)