from openai import OpenAI
import json
import os

def get_market_sell_analysis(portfolio_data):
    """
    First agent analyzes the portfolio data to identify profitable sell opportunities
    accounting for 1% transaction fee
    """
    openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a disciplined cryptocurrency portfolio manager focused on securing profits. 
                    Your goal is to identify the best selling opportunities for current positions, accounting for a 1% transaction fee.

                    ANALYSIS REQUIREMENTS:
                    1. MOG Coin is OFF LIMITS - never recommend selling it
                    2. Only recommend selling positions that will result in profit after 1% fee
                    3. Consider both unrealized gains and current market conditions
                    4. Prioritize positions showing signs of potential reversal
                    5. Factor in volatility and market sentiment for timing
                    6. Always include USDC value calculations in analysis
                    7. Check available USDC balance before suggesting trades
                    
                    RESPONSE FORMAT (Respond in JSON):
                    {
                        "portfolio_overview": "Brief analysis of current positions and total portfolio value",
                        "portfolio_total_value": "Sum of all positions in USDC",
                        "available_usdc": "Current USDC balance available for trading",
                        "usdc_per_coin": {
                            "BTC": "USDC value per Bitcoin",
                            "ETH": "USDC value per Ethereum",
                            // etc for each coin
                        },
                        "positions": [
                            {
                                "coin": "Symbol",
                                "usdc_value": "current value in USDC",
                                "percentage_of_portfolio": "what percent of total portfolio this represents"
                            }
                        ],
                        "sell_opportunities": [
                            {
                                "coin": "Symbol",
                                "current_position": {
                                    "quantity": "amount held",
                                    "entry_price": "average entry price in USDC",
                                    "current_price": "current market price in USDC",
                                    "usdc_value": "current value in USDC"
                                },
                                "action": "sell",
                                "target_price": "recommended sell price in USDC",
                                "unrealized_profit_pct": "current profit percentage including 1% fee",
                                "unrealized_profit_usdc": "current profit in USDC including 1% fee",
                                "reasoning": "explanation including technical and sentiment factors",
                                "urgency": "low/medium/high"
                            }
                        ],
                        "market_assessment": "Overall market condition and timing considerations"
                    }
                    
                    Ensure the response is properly formatted JSON and always acknowledge the available USDC balance."""
            },
            {
                "role": "user",
                "content": f"Analyze the following portfolio data for sell opportunities:\n\nPortfolio Data: {json.dumps(portfolio_data, indent=2)}"
            }
        ]
    )
    analysis = response.choices[0].message.content
    return analysis 