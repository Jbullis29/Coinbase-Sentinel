from openai import OpenAI
import json
import os

def get_market_buy_analysis(market_data):
    """
    Pre-screens market data for significant volatility before calling OpenAI
    """
    # Pre-screen for volatile opportunities
    volatile_opportunities = []
    
    for coin_data in market_data:
        # Skip if missing essential data
        if not all(key in coin_data for key in ['change_24h', 'volume_24h', 'price']):
            continue
            
        # Look for coins with significant movement or volume
        if (abs(coin_data['change_24h']) > 5 or  # More than 5% price change
            coin_data['volume_24h'] > 1000000):  # More than $1M volume
            volatile_opportunities.append(coin_data)
    
    # Only call OpenAI if we have volatile opportunities
    if volatile_opportunities:
        openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an extremely aggressive cryptocurrency day-trader..."""
                },
                {
                    "role": "user",
                    "content": f"Analyze these volatile opportunities:\n\n{json.dumps(volatile_opportunities, indent=2)}"
                }
            ]
        )
        return response.choices[0].message.content
    else:
        return json.dumps({
            "market_overview": "No significant volatility detected in current market conditions",
            "opportunities": [],
            "risk_assessment": "Market conditions do not meet volatility thresholds for trading"
        }) 