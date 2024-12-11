from coinbase_functions.coinbase_functions import *
import time
import os
from datetime import datetime
import numpy as np

def calculate_rsi(candles, periods=14):
    """Calculate RSI using candle data"""
    if not candles or len(candles) < periods + 1:
        return None
        
    # Extract closing prices
    closes = [candle['close'] for candle in candles]
    prices = np.array(closes)
    deltas = np.diff(prices)
    
    gain = [(x if x > 0 else 0) for x in deltas]
    loss = [(-x if x < 0 else 0) for x in deltas]
    
    avg_gain = np.mean(gain[:periods])
    avg_loss = np.mean(loss[:periods])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain/avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_moving_averages(candles):
    """Calculate MAs using candle data"""
    if not candles or len(candles) < 50:
        return None, None
    
    closes = [candle['close'] for candle in candles]
    ma20 = np.mean(closes[-20:])
    ma50 = np.mean(closes[-50:])
    return ma20, ma50

def analyze_volume(candles):
    """Analyze if current volume is significantly higher than average"""
    if not candles or len(candles) < 24:  # Need at least 24 hours of data
        return False
    
    volumes = [candle['volume'] for candle in candles]
    current_volume = volumes[-1]
    avg_volume = np.mean(volumes[-24:])  # 24-hour average
    
    return current_volume > (avg_volume * 1.5)

def analyze_buy_opportunities(market_data, buy_threshold=-5.0):
    """Analyze market data for buy opportunities with USDC balance check"""
    # Get USDC balance first
    accounts = client.get_accounts()
    usdc_balance = 0
    for account in accounts['accounts']:
        if account['currency'] == 'USDC':
            usdc_balance = float(account['available_balance']['value'])
            break
    
    # If USDC balance is too low, return empty list immediately
    if usdc_balance < 25:  # Minimum USDC balance threshold
        print(f"Insufficient USDC balance ({usdc_balance}) for trading. Skipping buy opportunities.")
        return []
        
    all_opportunities = []  # Process opportunities only if we have sufficient balance
    for asset in market_data:
        try:
            symbol = asset['symbol']
            current_price = float(asset['price'])
            change_24h = float(asset['change_24h'])
            candle_data = asset.get('candle_data', [])
            
            # Skip if no candle data
            if not candle_data:
                continue
            
            # Calculate technical indicators
            rsi = calculate_rsi(candle_data)
            ma20, ma50 = calculate_moving_averages(candle_data)
            volume_spike = analyze_volume(candle_data)
            
            # Scoring system (0-100)
            score = 0
            
            # Price drop criterion (max 30 points)
            if change_24h <= buy_threshold:
                score += 30
            
            # RSI criterion (max 25 points)
            if rsi is not None and rsi < 30:
                score += 25
            
            # Moving Average criterion (max 25 points)
            if ma20 and ma50 and current_price:
                if current_price < ma20 < ma50:
                    score += 25
            
            # Volume criterion (max 20 points)
            if volume_spike:
                score += 20
            
            # If score is high enough, add to opportunities list
            if score >= 60:
                rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
                reason = f'Buy score: {score}/100. Change: {change_24h:.2f}%, RSI: {rsi_str}'
                
                all_opportunities.append({
                    'product_id': symbol,
                    'side': 'BUY',
                    'amount': 25,  # Default buy amount in USD
                    'reason': reason,
                    'score': score  # Add score for sorting
                })
                
        except (ValueError, TypeError, KeyError) as e:
            print(f"Error analyzing {asset.get('symbol', 'unknown')}: {str(e)}")
            continue
    
    # Sort by score and take top 5
    buy_opportunities = sorted(all_opportunities, key=lambda x: x['score'], reverse=True)[:5]
    # Remove score from final output
    for opp in buy_opportunities:
        del opp['score']
            
    return buy_opportunities

def analyze_sell_opportunities(account_data, sell_threshold=5.0):
    """Analyze holdings for sell opportunities using multiple indicators"""
    all_opportunities = []
    print(f"\nAnalyzing {len(account_data)} holdings for sell opportunities...")
    
    for currency, details in account_data.items():
        try:
            if not details['coin_amount'] or not details['current_price']:
                continue
                
            entry_price = details['entry_price']
            current_price = details['current_price']
            candle_data = details['candle_data']
            
            if not entry_price or not current_price:
                continue
            
            # Calculate profit percentage
            profit_percentage = ((current_price - entry_price) / entry_price) * 100
            
            print(f"\nAnalyzing {currency}:")
            print(f"Entry Price: {entry_price}")
            print(f"Current Price: {current_price}")
            print(f"Profit: {profit_percentage:.2f}%")
            
            # Calculate technical indicators
            rsi = calculate_rsi(candle_data)
            ma20, ma50 = calculate_moving_averages(candle_data)
            
            # Safe printing of technical indicators
            if rsi is not None:
                print(f"RSI: {rsi:.1f}")
            else:
                print("RSI: N/A")
                
            if ma20 is not None:
                print(f"MA20: {ma20:.2f}")
            else:
                print("MA20: N/A")
                
            if ma50 is not None:
                print(f"MA50: {ma50:.2f}")
            else:
                print("MA50: N/A")
            
            # Scoring system (0-100)
            score = 0
            
            # Log scoring details
            if profit_percentage >= sell_threshold:
                score += 30
                print("✓ Profit threshold met (+30 points)")
            
            if rsi is not None and rsi > 70:
                score += 25
                print("RSI overbought condition met (+25 points)")
            
            if ma20 and ma50 and current_price > ma20 > ma50:
                score += 25
                print("Moving average trend met (+25 points)")
            
            if candle_data and len(candle_data) > 1:
                prev_price = candle_data[-2]['close']
                price_momentum = (current_price - prev_price) / prev_price * 100
                if price_momentum > 2:
                    score += 20
                    print("Price momentum criterion met (+20 points)")
            
            print(f"Final Score: {score}/100")
            
            # If score is high enough, add to opportunities list
            if score >= 60:
                # Create reason string with safer formatting
                reason = f'Sell score: {score}/100. Profit: {profit_percentage:.1f}%'
                if rsi is not None:
                    reason += f', RSI: {rsi:.1f}'
                else:
                    reason += ', RSI: N/A'
                    
                all_opportunities.append({
                    'product_id': f"{currency}-USD",
                    'side': 'SELL',
                    'reason': reason,
                    'score': score
                })
                print("→ Added to sell opportunities!")
                
        except (ValueError, TypeError, KeyError) as e:
            print(f"Error analyzing {currency}: {str(e)}")
            continue
    
    # Sort by score and take top 5
    sell_opportunities = sorted(all_opportunities, key=lambda x: x['score'], reverse=True)[:5]
    # Remove score from final output
    for opp in sell_opportunities:
        del opp['score']
    
    print(f"\nFound {len(sell_opportunities)} qualified sell opportunities out of {len(account_data)} holdings")
    return sell_opportunities

def main():
    while True:
        try:
            print("\nFetching market data...")
            market_data = get_market_data()[0]
            
            print("Fetching account data...")
            account_data = get_account_balances()
            
            print("Analyzing buy opportunities...")
            buy_actions = analyze_buy_opportunities(market_data)
            
            print("Analyzing sell opportunities...")
            sell_actions = analyze_sell_opportunities(account_data)
            
            # Combine all trade actions
            trade_actions = buy_actions + sell_actions
            
            # Log the actions
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            os.makedirs('trade_logs', exist_ok=True)
            
            with open(f'trade_logs/trading_log.txt', 'a') as f:
                f.write(f"\n\n=== {timestamp} ===\n")
                f.write(json.dumps(trade_actions, indent=2))
            
            if trade_actions:
                print(f"\nExecuting {len(trade_actions)} trade actions...")
                execute_trade_actions(trade_actions)
            else:
                print("\nNo trade actions to execute.")
            
        except Exception as e:
            print(f"Error in main loop: {str(e)}")
            
        print("\nWaiting for next iteration...")
        time.sleep(60)  # Wait for 1 hour

if __name__ == '__main__':
    main()
