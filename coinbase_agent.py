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
    Extract trade actions JSON and explanation from the assistant's response.
    
    Args:
        response (object): The ChatCompletion response object.
    
    Returns:
        tuple: (list of trade actions, explanation string)
    """
    try:
        content = response.choices[0].message.content
        print("\nRaw AI Response:")
        print(content)  # Debug print to see full response
        
    except (KeyError, IndexError) as e:
        print(f"Error accessing response content: {e}")
        return [], ""
    
    # Extract the JSON section
    json_section = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
    
    # Get the explanation (everything before the JSON)
    explanation = content.split("```json")[0].strip() if "```json" in content else ""
    
    if json_section:
        json_data = json_section.group(1)
        try:
            trade_actions = json.loads(json_data)
            print("\nExtracted Trade Actions:")
            print(json.dumps(trade_actions, indent=2))  # Debug print
            return trade_actions, explanation
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print("Problematic JSON data:", json_data)  # Debug print
            return [], explanation
    else:
        print("No JSON section found in the response content.")
        # Try alternative JSON format without code blocks
        try:
            # Look for array of trade actions in the content
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                trade_actions = json.loads(json_match.group(0))
                print("\nExtracted Trade Actions (alternative format):")
                print(json.dumps(trade_actions, indent=2))  # Debug print
                return trade_actions, explanation
        except Exception as e:
            print(f"Failed to parse alternative JSON format: {e}")
        
        return [], explanation


    
        
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
            # Skip MOG Coin sells
            if 'MOG-' in action['product_id'] and action['side'].upper() == 'SELL':
                print("Skipping MOG Coin sell - protected asset")
                continue

            # Validate action format
            if not isinstance(action, dict):
                print(f"Error: Invalid trade action format: {action}")
                continue
                
            # Validate required fields
            required_fields = ['product_id', 'side', 'amount']
            if not all(field in action for field in required_fields):
                print(f"Error: Missing required fields in trade action: {action}")
                continue

            # Skip invalid zero amount trades
            if float(action['amount']) <= 0:
                print(f"Skipping zero amount trade: {action}")
                continue

            # Get current price for the trading pair
            product_info = client.get_product(action['product_id']).to_dict()
            current_price = float(product_info['price'])
            
            # Extract details from the trade action
            product_id = str(action['product_id'])
            side = str(action['side'])
            base_currency = product_id.split('-')[0]
            quote_currency = product_id.split('-')[1]
            
            # For SELL orders, amount is in coin units
            # For BUY orders, amount is in USD
            amount = float(action['amount'])

            # Debug print
            print(f"Processing trade: {product_id} {side} {amount} {'coins' if side.upper() == 'SELL' else 'USD'} (Price: {current_price})")

            # Check balances and execute trade
            if side.upper() == 'SELL':
                if base_currency not in balances:
                    print(f"No {base_currency} balance found. Available currencies: {list(balances.keys())}")
                    continue
                if balances[base_currency] < amount:
                    print(f"Insufficient {base_currency} balance ({balances[base_currency]}) for trade: {action}")
                    continue
                response = client.market_order(
                    client_order_id=str(uuid.uuid4()),
                    product_id=product_id,
                    side='SELL',
                    base_size=str(amount)
                )
            else:  # BUY
                if quote_currency not in balances:
                    print(f"No {quote_currency} balance found. Available currencies: {list(balances.keys())}")
                    continue
                if balances[quote_currency] < amount:
                    print(f"Insufficient {quote_currency} balance ({balances[quote_currency]}) for trade: {action}")
                    continue
                response = client.market_order(
                    client_order_id=str(uuid.uuid4()),
                    product_id=product_id,
                    side='BUY',
                    quote_size=str(amount)
                )

            print(f"Executed trade: {response}")
            
            # Update balances after trade
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
        balances[account['currency']] = account['available_balance']['value']
        transactions = get_transaction_history()
    print('collected balances and transactions')         
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

                # Fix: Remove the 'Z' from timestamp before parsing
                created_time = order.created_time.replace('Z', '+00:00')
                
                # Only store if it's more recent than what we have
                if base_currency not in latest_orders or \
                   datetime.fromisoformat(created_time) > datetime.fromisoformat(latest_orders[base_currency]['created_time'].replace('Z', '+00:00')):
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
        # Change to look for USDC pairs instead of USD
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

def get_market_analysis(data_package):
    """
    First agent analyzes the market and provides recommendations without JSON
    """
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are an aggressive day-trading cryptocurrency analyst focused on maximizing 24-hour profits. 
                    Your goal is to analyze market conditions and recommend trading opportunities.

                    ANALYSIS REQUIREMENTS:
                    1. MOG Coin is OFF LIMITS - never recommend selling it
                    2. Analyze current market conditions
                    3. Compare current prices against entry prices
                    4. Consider 1% trading fees in recommendations
                    5. Look for both selling and buying opportunities
                    
                    RESPONSE FORMAT:
                    1. Market Overview
                    2. Specific Trading Recommendations
                    3. Profit/Loss Analysis for each recommendation
                    4. Risk Assessment
                    
                    DO NOT include any JSON or code blocks. Simply explain your analysis and recommendations in clear text."""
            },
            {
                "role": "user",
                "content": f"Analyze the following market data and provide trading recommendations:\n\n{json.dumps(data_package, indent=2)}"
            }
        ]
    )
    
    try:
        analysis = response.choices[0].message.content
        print("\nMarket Analysis:")
        print(analysis)
        return analysis
    except Exception as e:
        print(f"Error getting market analysis: {e}")
        return ""

def validate_and_create_actions(market_analysis, balances, market_data):
    """
    Second agent validates analysis and creates specific trade actions
    """
    validation_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    validation_data = {
        "market_analysis": market_analysis,
        "current_balances": balances,
        "market_data": market_data
    }
    
    response = validation_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a cryptocurrency trade validator and action creator. Your job is to:
                    1. Review the market analysis
                    2. Validate recommendations against current balances
                    3. Create specific trade actions in the correct format

                    TRADE SIZE REQUIREMENTS:
                    1. Minimum trade size: $25 USD equivalent
                    2. For SELL orders: Use a significant portion (50-100%) of available coins
                    3. For BUY orders: Use at least $25 USD, up to available balance
                    4. Never create trades smaller than $25 USD equivalent
                    5. When flipping positions, sell entire position (100%) to maximize efficiency

                    VALIDATION REQUIREMENTS:
                    1. Ensure sufficient balances exist for each trade
                    2. Verify MOG Coin is never sold
                    3. Calculate USD value of all trades before approving
                    4. Check that sequential trades maintain valid balances
                    5. For SELL orders: amount must be in coin units (use most of available balance)
                    6. For BUY orders: amount must be in USD (minimum $25)
                    
                    YOU MUST RESPOND WITH:
                    1. Validation Analysis (text explanation)
                    2. Trade Actions in this exact JSON format:                    ```json
                    [
                        {
                            "product_id": "BTC-USD",
                            "side": "SELL",
                            "amount": 0.05
                        }
                    ]                    ```

                    EXAMPLE TRADES:
                    - SELL: If balance is 100 DOGE, sell 95-100 DOGE
                    - Never create trades worth less than $25 USD equivalent
                    """
            },
            {
                "role": "user",
                "content": f"Please validate this analysis and create trade actions. Remember to use significant portions of available balance for trades:\n\n{json.dumps(validation_data, indent=2)}"
            }
        ]
    )
    
    try:
        content = response.choices[0].message.content
        print("\nValidation Response:")
        print(content)
        
        # Extract JSON section
        json_section = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
        if not json_section:
            print("No trade actions found in validation response")
            return [], content
            
        trade_actions = json.loads(json_section.group(1))
        explanation = content.split("```json")[0].strip()
        
        # Validate minimum trade sizes
        validated_actions = []
        for action in trade_actions:
            try:
                # Get current price for the trading pair
                product_info = client.get_product(action['product_id']).to_dict()
                current_price = float(product_info['price'])
                
                # Calculate USD value of trade
                if action['side'].upper() == 'SELL':
                    usd_value = float(action['amount']) * current_price
                else:
                    usd_value = float(action['amount'])
                
                # Only include trades worth at least $25
                if usd_value >= 25:
                    validated_actions.append(action)
                else:
                    print(f"Skipping small trade worth ${usd_value:.2f} USD")
            except Exception as e:
                print(f"Error validating trade size: {e}")
                continue
        
        return validated_actions, explanation
        
    except Exception as e:
        print(f"Error in validation: {e}")
        return [], f"Validation failed: {str(e)}"

def main():
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get market data and balances
        balances, transactions = get_account_balances()
        market_data, _ = get_market_data()
        available_coins = extract_available_coins(market_data)
        
        data_package = {
            'balances': balances,
            'transactions': transactions,
            'market_data': market_data,
            'available_coins': available_coins
        }

        # Get market analysis from first agent
        market_analysis = get_market_analysis(data_package)
        
        # Get trade actions from second agent
        if market_analysis:
            trade_actions, validation_explanation = validate_and_create_actions(
                market_analysis,
                balances,
                market_data
            )
            
            print("\nValidation Explanation:")
            print(validation_explanation)
            
            if trade_actions:
                print("\nExecuting Validated Trades:")
                execute_trade_actions(trade_actions)
            else:
                print("\nNo trades to execute")
        else:
            print("\nNo market analysis available")
            
        time.sleep(3600)

# Run the script
if __name__ == '__main__':
    main()
