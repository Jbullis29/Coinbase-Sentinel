from openai import OpenAI
import json
import os


def validate_and_create_actions(buy_analysis, sell_analysis, portfolio_data):
    """
    Financial advisor agent creates specific trade actions based on both buy and sell opportunities,
    managing the USD balance effectively.
    """
    validation_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Get USD balance from portfolio data
    usd_balance = float(portfolio_data.get('USD', {}).get('balance', 0))
    
    validation_data = {
        "buy_opportunities": buy_analysis,
        "sell_opportunities": sell_analysis,
        "portfolio_data": portfolio_data,
        "usd_balance": usd_balance
    }
    
    response = validation_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a cryptocurrency financial advisor and trade validator. Your job is to:
                    1. Review both buy and sell opportunities
                    2. Validate recommendations against current balances
                    3. Create specific trade actions that optimize the portfolio
                    4. Manage USD balance effectively

                    TRADE SIZE REQUIREMENTS:
                    1. Minimum trade size: $25 USD equivalent
                    2. For SELL orders: Specify the USD value you want to sell (e.g., sell $500 worth of BTC)
                    3. For BUY orders: Specify USD amount to spend
                    4. Never create trades smaller than $25 USD equivalent
                    5. When flipping positions, specify the full USD value to sell

                    VALIDATION REQUIREMENTS:
                    1. Ensure sufficient balances exist for each trade
                    2. Verify MOG Coin is never sold
                    3. All trade amounts must be specified in USD value
                    4. Check that sequential trades maintain valid balances
                    
                    STRATEGY REQUIREMENTS:
                    1. Prioritize selling overvalued positions to increase USD balance
                    2. Use available USD for high-conviction buy opportunities
                    3. Maintain some USD balance for future opportunities
                    4. Consider market conditions when sizing trades
                    
                    YOU MUST RESPOND WITH:
                    1. Strategy Analysis (text explanation)
                    2. Trade Actions in this exact JSON format:                    ```json
                    [
                        {
                            "product_id": "BTC-USD",
                            "side": "SELL",
                            "amount": 500.00  // Amount in USD to sell
                        }
                    ]                    ```

                    EXAMPLE TRADES:
                    - SELL: To sell $500 worth of BTC, specify amount: 500.00
                    - BUY: To buy $500 worth of BTC, specify amount: 500.00
                    """
            },
            {
                "role": "user",
                "content": f"Please analyze these opportunities and create trade actions. Remember to manage the USD balance of ${usd_balance}:\n\n{json.dumps(validation_data, indent=2)}"
            }
        ]
    )
    
    content = response.choices[0].message.content
    
    # Extract trade actions JSON from the response
    try:
        # Find JSON content between ```json and ``` markers
        start_marker = content.find("```json")
        if start_marker != -1:
            json_start = content.find("[", start_marker)
            json_end = content.find("]", json_start) + 1
            json_str = content[json_start:json_end]
            
            # Remove comments from JSON string
            json_lines = json_str.split('\n')
            clean_lines = [line.split('//')[0].strip() for line in json_lines]
            clean_json = ' '.join(clean_lines)
            
            # Return both content and parsed JSON
            return content, json.loads(clean_json)
        else:
            # Fallback: try to find any JSON array in the content
            json_start = content.find("[")
            json_end = content.find("]") + 1
            json_str = content[json_start:json_end]
            
            # Remove comments from JSON string
            json_lines = json_str.split('\n')
            clean_lines = [line.split('//')[0].strip() for line in json_lines]
            clean_json = ' '.join(clean_lines)
            
            return content, json.loads(clean_json)
            
    except json.JSONDecodeError as e:
        print(f"Failed to parse trade actions from response: {e}")
        return content, []
