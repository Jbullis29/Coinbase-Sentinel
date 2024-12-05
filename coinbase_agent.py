import os
import re
import uuid
import json
import time
import subprocess
from openai import OpenAI
from coinbase.rest import RESTClient
from datetime import datetime, timedelta
import requests

def extract_trade_actions(response):
    """
    Extract trade actions JSON from the assistant's response.
    
    Args:
        response (object): The ChatCompletion response object.
    
    Returns:
        list: A list of trade actions extracted from the JSON, or an empty list if none found.
    """
    # Extract the content of the assistant's message
    try:
        content = response.to_dict()['choices'][0]['message']['content']
    except (KeyError, IndexError) as e:
        print(f"Error accessing response content: {e}")
        return []
    
    # Use regex to locate the JSON section
    json_section = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
    if json_section:
        json_data = json_section.group(1)  # Extract the JSON block
        try:
            # Parse the JSON into a Python object
            trade_actions = json.loads(json_data)
            return trade_actions
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            return []
    else:
        print("No JSON section found in the response content.")
        return []


    
        
client = RESTClient(api_key=os.getenv('CDP_API_KEY_NAME'), api_secret=os.getenv('CDP_API_KEY_PRIVATE_KEY'))

def execute_trade_actions(trade_actions):
    """
    Execute trade actions using the provided market_order function.
    """
    # Get fresh balances before each execution cycle
    accounts = client.get_accounts()
    balances = {}
    for account in accounts['accounts']:
        balance = float(account['available_balance']['value'])
        if balance > 0:  # Only include non-zero balances
            balances[account['currency']] = balance
    
    print("Current non-zero balances:", balances)

    for action in trade_actions:
        try:
            # Validate action format
            if not isinstance(action, dict):
                print(f"Error: Invalid trade action format: {action}")
                continue
                
            # Validate required fields
            required_fields = ['product_id', 'side', 'amount_coin']
            if not all(field in action for field in required_fields):
                print(f"Error: Missing required fields in trade action: {action}")
                continue

            # Skip invalid zero amount trades
            if float(action['amount_coin']) <= 0:
                print(f"Skipping zero amount trade: {action}")
                continue

            # Extract details from the trade action
            product_id = str(action['product_id'])
            side = str(action['side'])
            base_currency = product_id.split('-')[0]  # First part (e.g., 'SHIB' from 'SHIB-USD')
            quote_currency = product_id.split('-')[1]  # Second part (e.g., 'USD' from 'SHIB-USD')
            amount_coin = round(float(action['amount_coin']), 6)

            # Debug print
            print(f"Processing trade: {product_id} {side} {amount_coin}")

            # Check if required currencies exist in balances
            if side.upper() == 'SELL':
                # For sells, we need the base currency (e.g., SHIB)
                if base_currency not in balances:
                    print(f"No {base_currency} balance found. Available currencies: {list(balances.keys())}")
                    continue
            else:  # BUY
                # For buys, we only need the quote currency (e.g., USD)
                if quote_currency not in balances:
                    print(f"No {quote_currency} balance found. Available currencies: {list(balances.keys())}")
                    continue

            # Check if we have sufficient balance before trading
            if side.upper() == 'SELL':
                if balances[base_currency] < amount_coin:
                    print(f"Insufficient {base_currency} balance ({balances[base_currency]}) for trade: {action}")
                    continue
            else:  # BUY
                if balances[quote_currency] < amount_coin:
                    print(f"Insufficient {quote_currency} balance ({balances[quote_currency]}) for trade: {action}")
                    continue

            # Generate a unique client_order_id
            client_order_id = str(uuid.uuid4())

            # Execute the trade
            if side.upper() == 'BUY':
                response = client.market_order(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    side=side.upper(),
                    quote_size=str(round(amount_coin, 2)),
                )
            else:  # SELL
                response = client.market_order(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    side=side.upper(),
                    base_size=str(amount_coin),
                )

            print(f"Executed trade: {response}")
            
            # Get fresh balances after each trade
            accounts = client.get_accounts()
            balances = {}
            for account in accounts['accounts']:
                balance = float(account['available_balance']['value'])
                if balance > 0:
                    balances[account['currency']] = balance
            print(f"Updated balances after trade: {balances}")

            # Add delay between trades
            time.sleep(3)
            
        except Exception as e:
            print(f"Failed to execute trade action {action}: {str(e)}")
            print(f"Error type: {type(e)}")

# 1. Get account balances
def get_account_balances():
    accounts = client.get_accounts()
    balances = {}
    for account in accounts['accounts']:
        print(account)
        balances[account['currency']] = account['available_balance']['value']
        transactions = get_transaction_history()
        print("\nTransaction:")
        for txn in transactions:
            print(txn)
    return balances, transactions

# 2. Get transaction history for a specific account
def get_transaction_history():
    transactions = client.list_orders()
    latest_orders = {}  # Dictionary to store most recent order for each coin
    
    # Get current non-zero balances first
    accounts = client.get_accounts()
    non_zero_currencies = set()
    for account in accounts['accounts']:
        if float(account['available_balance']['value']) > 0:
            non_zero_currencies.add(account['currency'])
    
    for order in transactions['orders']:
        if order.status != 'CANCELLED':
            try:
                # Extract the base currency from the product_id (e.g., 'BTC' from 'BTC-USDC')
                base_currency = order.product_id.split('-')[0]
                
                # Skip if we don't have a non-zero balance for this currency
                if base_currency not in non_zero_currencies:
                    continue
                
                # Create simplified order info with safer access to configuration
                size = None
                order_config = order.order_configuration
                if order_config:
                    # Handle different order types
                    if hasattr(order_config, 'limit_limit_gtc'):
                        size = order_config.limit_limit_gtc.base_size
                    elif hasattr(order_config, 'market_market_ioc'):
                        market_config = order_config.market_market_ioc
                        size = getattr(market_config, 'base_size', None) or \
                              getattr(market_config, 'quote_size', None)

                simplified_order = {
                    'product_id': order.product_id,
                    'side': order.side,
                    'size': size,
                    'status': order.status,
                    'created_time': order.created_time,
                    'filled_size': order.filled_size,
                    'total_value_after_fees': order.total_value_after_fees,
                    'entry_price': float(order.total_value_after_fees) / float(order.filled_size) if order.filled_size else None
                }

                # Only store if it's more recent than what we have
                if base_currency not in latest_orders or \
                   datetime.fromisoformat(order.created_time) > datetime.fromisoformat(latest_orders[base_currency]['created_time']):
                    latest_orders[base_currency] = simplified_order
                    
            except AttributeError as e:
                print(f"Skipping order due to missing data: {e}")
                continue
                
    return list(latest_orders.values())  # Convert dictionary values to list

# 3. Get market data
def get_market_data():
    # Retrieve all products
    products = client.get_products()
    
    # Initialize a list to store market data
    filtered_market_data = []
    all_candle_data = {}  # Changed to dictionary for easier lookup
    
    # Iterate through each product to fetch market data
    for product_data in products.to_dict()['products']:
        # Only process USD pairs (avoid duplicate USDC pairs)
        if product_data['product_id'].endswith("-USD"):
            
            # Skip products with missing or invalid data
            if not all([product_data['price'], 
                       product_data['price_percentage_change_24h'],
                       product_data['volume_24h']]):
                continue
                
            product_info = {
                'symbol': product_data['product_id'],
                'price': float(product_data['price']),
                'change_24h': float(product_data['price_percentage_change_24h']),
                'volume_24h': float(product_data['volume_24h']),
                'status': product_data['status']
            }
            
            # Include products that meet any of these criteria:
            # 1. High volume (> $1M in 24h)
            # 2. Significant price movement (>5% in 24h)
            if (product_info['status'] == 'online' and 
                not product_data['is_disabled'] and 
                (product_info['volume_24h'] > 1000000 or  # High volume
                 abs(product_info['change_24h']) > 5)):   # Significant price movement
                
                filtered_market_data.append(product_info)
    
    # Sort by volume first to get top 25
    filtered_market_data.sort(key=lambda x: x['volume_24h'], reverse=True)
    filtered_market_data = filtered_market_data[:10]  # Limit to top 25
    
    # Now get candle data and append it to market data
    for product in filtered_market_data:
        candle_data = get_candles_public(product['symbol'])
        product['candle_data'] = candle_data  # Add candle data directly to the product info
    
    # Finally sort by price change for display
    filtered_market_data.sort(key=lambda x: abs(x['change_24h']), reverse=True)
    
    return filtered_market_data, all_candle_data  # You can keep returning both or just filtered_market_data

# 4. Get candles
def get_candles_public(product):
    """
    Get candle data using Coinbase's public API endpoint.
    """
    try:
        # Use the public endpoint
        url = f"https://api.exchange.coinbase.com/products/{product}/candles"
        
        # Parameters for the request
        params = {
            'granularity': 3600,  # 1 hour in seconds
            'start': (datetime.now() - timedelta(days=7)).isoformat(),
            'end': datetime.now().isoformat()
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        candles = response.json()
        
        # Format the response
        # Each candle is [timestamp, open, high, low, close, volume]
        candle_list = []
        for candle in candles:
            candle_list.append({
                'symbol': product,
                'time': candle[0],
                'open': candle[1],
                'high': candle[2],
                'low': candle[3],
                'close': candle[4],
                'volume': candle[5]
            })
        print(f'candles collected for {product}')
        return candle_list
        
    except Exception as e:
        print(f"Error fetching candles for {product}: {e}")
        return []

def extract_available_coins(market_data):
    """
    Extract unique coin symbols from market data product IDs.
    """
    available_coins = set()
    for product in market_data:
        base_currency = product['symbol'].split('-')[0]  # Get the coin part before the hyphen
        available_coins.add(base_currency)
    return list(available_coins)

# Main function to gather all the data
def main():
    while True:
        # Create timestamp first
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get balances and transaction history with entry prices
        balances, transactions = get_account_balances()
        
        # Get market data and extract available coins
        market_data, _ = get_market_data()
        available_coins = extract_available_coins(market_data)
        
        # Enhance data package with entry prices
        data_package = {
            'balances': balances,
            'transactions': transactions,  # Now includes entry prices
            'market_data': market_data,
            'available_coins': available_coins
        }

        # Send data to OpenAI
        openai_client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"))
        response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a sophisticated cryptocurrency trading assistant that can ONLY:
                    1. BUY cryptocurrencies using available USDC balance
                    2. SELL cryptocurrencies back to USDC ONLY when profitable after fees
                    3. Take no action when conditions aren't favorable
                    
                    Available trading pairs are limited to these base currencies: """ + ', '.join(available_coins) + """
                    
                    CRITICAL TRADING REQUIREMENTS:
                    - You can ONLY BUY using existing USDC balance
                    - You can ONLY SELL cryptocurrencies back to USDC when there's a clear profit after fees
                    - All trades must end in '-USDC' (e.g., BTC-USDC, ETH-USDC)
                    - Consider 1% total trading fees (0.5% buy + 0.5% sell)
                    - Do NOT suggest buying a coin if it already has a non-zero balance
                    
                    Trading Strategy:
                    1. Review transaction history to identify entry prices
                    2. Compare current market prices against entry prices
                    3. Only suggest SELL orders when profitable after fees
                    4. Look for good entry points for BUY orders
                    5. It's okay to suggest no trades if conditions aren't favorable
                    
                    Order Format:
                    - BUY Example: {"product_id": "BTC-USDC", "side": "BUY", "amount_coin": 50.00}
                    - SELL Example: {"product_id": "BTC-USDC", "side": "SELL", "amount_coin": 0.001234}"""
            },
            {
                "role": "user",
                "content": "Analyze the following data and return a JSON array of trade actions ONLY if you see favorable opportunities. "
                    "Remember: The balances shown only include non-zero amounts.\n\n"
                    f"Current portfolio and market data: {json.dumps(data_package)}"
            }
        ]
    )
        trade_actions = extract_trade_actions(response)
        print(trade_actions)
        
        execute_trade_actions(trade_actions)
        time.sleep(1800)
        
    
# Run the script
if __name__ == '__main__':
    main()