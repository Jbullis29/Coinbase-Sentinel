from openai import OpenAI
import json
import os

def get_market_buy_analysis(market_data):
    """
    First agent analyzes the market and provides recommendations and include the market data for opportunities 
    """
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are an extremely aggressive cryptocurrency day-trader focused on exploiting high volatility for maximum gains. 
                    Your goal is to identify the most volatile opportunities that could yield significant returns within 24 hours.

                    ANALYSIS REQUIREMENTS:
                    1. MOG Coin is OFF LIMITS - never recommend selling it
                    2. Prioritize coins showing high volatility patterns
                    3. Focus on coins with recent significant price movements
                    4. Look for potential breakout opportunities
                    5. Consider both technical indicators and market sentiment
                    
                    RESPONSE FORMAT (Respond in JSON):
                    {
                        "market_overview": "Brief market analysis focusing on volatility",
                        "opportunities": [
                            {
                                "coin": "Symbol",
                                "usd_price": "current price in USD",
                                "action": "buy",
                                "entry_price": "suggested entry price",
                                "target_price": "target exit price (aim for 15-30% gains)",
                                "stop_loss": "suggested stop loss (wider ranges acceptable)",
                                "volatility_score": "1-10 rating",
                                "reasoning": "brief explanation including volatility factors",
                                "risk_level": "medium/high/extreme"
                            }
                        ],
                        "risk_assessment": "Overall risk assessment and volatility outlook"
                    }
                    
                    Ensure the response is properly formatted JSON."""
            },
            {
                "role": "user",
                "content": f"Analyze the following market data and provide trading recommendations:\n\n{json.dumps(market_data, indent=2)}"
            }
        ]
    )
    analysis = response.choices[0].message.content
    return analysis 