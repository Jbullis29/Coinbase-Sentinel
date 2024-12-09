from openai import OpenAI
import json
import os

def get_market_buy_analysis(market_data):
    """
    First agent analyzes the market and provides recommendations and include the market data for opportunities 
    """
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an extremely aggressive cryptocurrency day-trader focused on exploiting high volatility for maximum gains using USDC funds. 
                        Your goal is to identify the most volatile USDC trading pairs that could yield significant returns within 24 hours.

                        ANALYSIS REQUIREMENTS:
                        1. MOG Coin is OFF LIMITS - never recommend selling it
                        2. Prioritize USDC trading pairs showing high volatility patterns
                        3. Focus on coins with recent significant price movements against USDC
                        4. Look for potential breakout opportunities
                        5. Consider both technical indicators and market sentiment
                        6. Check available USDC balance before suggesting trades
                        7. Only suggest trades that can be executed with current USDC balance
                        
                        RESPONSE FORMAT (Respond in JSON):
                        {
                            "market_overview": "Brief market analysis focusing on volatility",
                            "available_usdc": "Current USDC balance available for trading",
                            "opportunities": [
                                {
                                    "coin": "Symbol",
                                    "usdc_price": "current price in USDC",
                                    "action": "buy",
                                    "entry_price": "suggested entry price in USDC",
                                    "quantity": "amount that can be bought with available USDC",
                                    "target_price": "target exit price in USDC (aim for 15-30% gains)",
                                    "stop_loss": "suggested stop loss in USDC (wider ranges acceptable)",
                                    "volatility_score": "1-10 rating",
                                    "reasoning": "brief explanation including volatility factors",
                                    "risk_level": "medium/high/extreme"
                                }
                            ],
                            "risk_assessment": "Overall risk assessment and volatility outlook"
                        }
                        
                        Ensure the response is properly formatted JSON and always acknowledge the available USDC balance."""
                },
                {
                    "role": "user",
                    "content": f"Analyze the following market data and provide trading recommendations:\n\n{json.dumps(market_data, indent=2)}"
                }
            ]
        )
        analysis = response.choices[0].message.content
        return analysis
    except Exception as e:
        error_response = {
            "market_overview": f"Error analyzing market data: {str(e)}",
            "opportunities": [],
            "risk_assessment": "Unable to complete analysis due to technical error"
        }
        return json.dumps(error_response) 