from openai import OpenAI
import json
import os

def get_market_sell_analysis(portfolio_data):
    """
    First screens portfolio for profitable positions before calling OpenAI
    """
    # Pre-screen for profitable positions (accounting for 1% fee)
    profitable_positions = {}
    has_profitable_positions = False
    
    for currency, data in portfolio_data.items():
        # Skip USDC and MOG
        if currency in ['USDC', 'MOG']:
            continue
            
        # Check if we have all necessary data
        if (data.get('entry_price') and data.get('current_price') and 
            data.get('coin_amount') and data.get('usd_value')):
            
            entry_price = float(data['entry_price'])
            current_price = float(data['current_price'])
            
            # Calculate profit percentage after 1% fee
            profit_pct = ((current_price - entry_price) / entry_price * 100) - 1
            
            # Only include positions with profit > 1%
            if profit_pct > 1:
                has_profitable_positions = True
                profitable_positions[currency] = data
    
    # Only call OpenAI if we have profitable positions
    if has_profitable_positions:
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a disciplined cryptocurrency portfolio manager..."""
                },
                {
                    "role": "user",
                    "content": f"Analyze the following profitable positions for sell opportunities:\n\nPortfolio Data: {json.dumps(profitable_positions, indent=2)}"
                }
            ]
        )
        return response.choices[0].message.content
    else:
        return json.dumps({
            "portfolio_overview": "No profitable positions found after accounting for 1% fee",
            "portfolio_total_value": sum(data.get('usd_value', 0) for data in portfolio_data.values()),
            "available_usdc": portfolio_data.get('USDC', {}).get('coin_amount', 0),
            "sell_opportunities": []
        }) 