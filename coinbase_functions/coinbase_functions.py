import os
import re
import uuid
import json
import time
from coinbase.rest import RESTClient
from datetime import datetime, timedelta
import requests


client = RESTClient(api_key=os.getenv('CDP_API_KEY_NAME'), api_secret=os.getenv('CDP_API_KEY_PRIVATE_KEY'))

# 1. Get account balances
def get_account_balances():
    accounts = client.get_accounts()
    balances = {}
    
    # Get transactions first
    transactions = get_transaction_history()
    
    # Get market data for portfolio coins
    market_data, _ = get_portfolio_market_data()
    market_data_by_currency = {
        product['symbol'].split('-')[0]: product 
        for product in market_data
    }
    
    # Create a mapping of transactions by currency
    transactions_by_currency = {}
    for transaction in transactions:
        base_currency = transaction['product_id'].split('-')[0]
        if base_currency not in transactions_by_currency:
            transactions_by_currency[base_currency] = []
        transactions_by_currency[base_currency].append(transaction)
    
    # Build balances with transactions and market data
    for account in accounts['accounts']:
        currency = account['currency']
        balance = account['available_balance']['value']
        if float(balance) > 0:  # Only include non-zero balances
            # Get latest transaction for entry price
            currency_transactions = transactions_by_currency.get(currency, [])
            latest_transaction = currency_transactions[0] if currency_transactions else None
            entry_price = latest_transaction.get('entry_price') if latest_transaction else None
            
            # Get current market data
            market_info = market_data_by_currency.get(currency, {})
            current_price = market_info.get('price')
            
            # Calculate USD value
            usd_value = float(balance) * current_price if current_price else None
            
            balances[currency] = {
                'coin_amount': balance,
                'usd_value': usd_value,
                'entry_price': entry_price,
                'current_price': current_price,
                'market_data': market_info,
                'transactions': currency_transactions
            }
            
    print('collected balances, transactions, and market data')         
    return balances

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

                # Calculate entry price only if we have valid filled_size and total_value
                entry_price = None
                if order.filled_size and order.total_value_after_fees:
                    try:
                        entry_price = float(order.total_value_after_fees) / float(order.filled_size)
                    except (ValueError, ZeroDivisionError):
                        entry_price = None

                simplified_order = {
                    'product_id': order.product_id,
                    'side': order.side,
                    'size': size,
                    'status': order.status,
                    'created_time': order.created_time,
                    'filled_size': order.filled_size,
                    'total_value_after_fees': order.total_value_after_fees,
                    'entry_price': entry_price
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
def get_market_data(portfolio_only=False):
    """
    Get market data for all coins or just portfolio coins.
    Args:
        portfolio_only (bool): If True, only return data for coins in portfolio
    """
    products = client.get_products()
    filtered_market_data = []
    all_candle_data = {}
    
    # Get portfolio balances if needed
    portfolio_balances = {}
    if portfolio_only:
        accounts = client.get_accounts()
        portfolio_balances = {
            account['currency']: float(account['available_balance']['value'])
            for account in accounts['accounts'] 
            if float(account['available_balance']['value']) > 0
        }
        portfolio_coins = set(portfolio_balances.keys())
    
    for product_data in products.to_dict()['products']:
        base_currency = product_data['product_id'].split('-')[0]
        
        # Skip if portfolio_only is True and coin isn't in portfolio
        if portfolio_only and base_currency not in portfolio_coins:
            continue
            
        if product_data['product_id'].endswith("-USD"):
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
            
            # Add USD value calculation for portfolio coins
            if portfolio_only:
                if base_currency in portfolio_balances:
                    product_info['usd_value'] = portfolio_balances[base_currency] * float(product_data['price'])
            
            # Apply filters only for non-portfolio coins
            if portfolio_only:
                if product_info['status'] == 'online' and not product_data['is_disabled']:
                    filtered_market_data.append(product_info)
            else:
                if (product_info['status'] == 'online' and 
                    not product_data['is_disabled'] and 
                    (product_info['volume_24h'] > 100000 or 
                     abs(product_info['change_24h']) > 2)):
                    filtered_market_data.append(product_info)
    
    # Sort and limit only for non-portfolio data
    if not portfolio_only:
        filtered_market_data.sort(key=lambda x: x['volume_24h'], reverse=True)
        filtered_market_data = filtered_market_data[:30]
    
    # Get candle data
    for product in filtered_market_data:
        candle_data = get_candles_public(product['symbol'])
        product['candle_data'] = candle_data
    
    if not portfolio_only:
        filtered_market_data.sort(key=lambda x: abs(x['change_24h']), reverse=True)
    
    return filtered_market_data, all_candle_data

def get_portfolio_market_data():
    """
    Convenience function to get market data only for portfolio coins.
    """
    return get_market_data(portfolio_only=True)

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


def execute_trade_actions(trade_actions):
    """
    Execute trade actions using the provided market_order function.
    All amounts from the agent are in USD:
        - For SELL: Convert USD amount to base_size (crypto amount)
        - For BUY: Use USD amount directly as quote_size
    """
    for action in trade_actions:
        try:
            product_id = str(action['product_id'])
            side = str(action['side'])
            usd_amount = float(action['amount'])

            if side.upper() == 'SELL':
                # For SELL: Need to convert USD amount to crypto amount
                product = client.get_product(product_id)
                current_price = float(product.price)
                crypto_amount = usd_amount / current_price
                
                # Get base_increment and determine decimal places
                base_increment = float(product.base_increment)
                
                # Round to the nearest increment
                crypto_amount = round(crypto_amount / base_increment) * base_increment
                
                # Convert to string with appropriate precision
                crypto_amount_str = '{:.10f}'.format(crypto_amount).rstrip('0').rstrip('.')
                
                print(f"Debug - Product: {product_id}")
                print(f"Debug - Base Increment: {base_increment}")
                print(f"Debug - Original Amount: {crypto_amount}")
                print(f"Debug - Formatted Amount: {crypto_amount_str}")
                
                response = client.market_order(
                    client_order_id=str(uuid.uuid4()),
                    product_id=product_id,
                    side='SELL',
                    base_size=crypto_amount_str  # Amount in crypto
                )
            else:  # BUY
                # For BUY: Use USD amount directly, rounded to 2 decimal places
                usd_amount = round(usd_amount, 2)
                response = client.market_order(
                    client_order_id=str(uuid.uuid4()),
                    product_id=product_id,
                    side='BUY',
                    quote_size=str(usd_amount)  # Amount in USD
                )

            print(f"Executed trade: {response}")
            time.sleep(3)
            
        except Exception as e:
            print(f"Failed to execute trade action {action}: {str(e)}")
            print(f"Debug - Full error: {str(e)}")



