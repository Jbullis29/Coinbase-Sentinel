from coinbase_functions.coinbase_functions import *
from openAI_agents.market_buy_op_agent import get_market_buy_analysis
from openAI_agents.sell_op_agent import get_market_sell_analysis
from openAI_agents.financial_advisory_agent import validate_and_create_actions
import time
import os
from datetime import datetime

def main():
    while True:
    # # Get all market data
    market_data = get_market_data()[0]
    all_buy_analyses = []  # List to store all analysis responses
    
    # Process market data in batches of 15
    batch_size = 9

    for i in range(0, len(market_data), batch_size):
        batch = market_data[i:i + batch_size]
        print(f"\nProcessing batch {i//batch_size + 1} of {(len(market_data) + batch_size - 1)//batch_size}")
        
        # Get analysis for current batch
        analysis = get_market_buy_analysis(batch)
        if analysis:  # Only append if we got a valid response
            all_buy_analyses.append(analysis)
        print(f"Buy Batch {i//batch_size + 1} analysis complete")
        
        # Optional: Add a delay between batches to avoid rate limits
        time.sleep(2)

    data = get_account_balances()
    sell_op_analysis = get_market_sell_analysis(data)
    financial_advisory, trade_actions = validate_and_create_actions(all_buy_analyses, sell_op_analysis, data)
    
    # Create logs directory if it doesn't exist
    os.makedirs('ai_logs', exist_ok=True)
    
    # Get current timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # Save financial advisory to log file
    with open(f'ai_logs/financial_advisory_log.txt', 'a') as f:
        f.write(f"\n\n=== {timestamp} ===\n")
        f.write(json.dumps(financial_advisory))
    
    execute_trade_actions(trade_actions)
    time.sleep(3600)
      
    # Run the script
if __name__ == '__main__':
    analyses = main()
